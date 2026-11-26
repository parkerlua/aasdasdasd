import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CATEGORIES = {"discord_username", "discord_badges"}


class ProfileError(Exception):
    pass


def image_url(folder, user_id, image_hash):
    extension = "gif" if image_hash.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/{folder}/{user_id}/{image_hash}.{extension}?size=512"


def returned_avatar_url(value, user_id):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        rf"https://(?:cdn\.discordapp\.com|media\.discordapp\.net)/avatars/{user_id}/"
        r"((?:a_)?[A-Za-z0-9]+)\.(?:png|gif|webp|jpe?g)(?:\?[^#\s]*)?",
        value,
    )
    if match:
        return f"https://cdn.discordapp.com/avatars/{user_id}/{match[1]}.png?size=256"
    return None


def lookup(user_id):
    if not re.fullmatch(r"[1-9][0-9]{16,19}", user_id) or int(user_id) >= 2**64:
        raise ProfileError("Enter a numeric Discord user ID.")
    token = os.environ.get("DISCORD_BOT_TOKEN")
    headers = {"User-Agent": "DiscordBot (https://t.me/Evaluate, 1.0)"}
    if token:
        url = f"https://discord.com/api/v10/users/{user_id}"
        headers["Authorization"] = f"Bot {token}"
    else:
        url = f"https://discord-lookup.lookupbotdc.workers.dev/search/{user_id}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
            user = payload if token else payload.get("user")
            if not isinstance(user, dict) or user.get("id") != user_id or not user.get("username"):
                raise ValueError("Invalid profile response")
    except HTTPError as error:
        if error.code == 404:
            raise ProfileError("Discord could not find that user ID.") from None
        raise ProfileError("Discord profile lookup is unavailable. Try again later.") from None
    except (URLError, TimeoutError, OSError, ValueError, AttributeError):
        raise ProfileError("Discord profile lookup is unavailable. Try again later.") from None

    if user.get("bot"):
        raise ProfileError("Enter the ID of a Discord user account.")
    avatar = user.get("avatar")
    provided_avatar = returned_avatar_url(payload.get("avatar_url"), user_id) if not token else None
    if provided_avatar:
        avatar_url = provided_avatar
    elif avatar:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=256"
    else:
        discriminator = int(user.get("discriminator") or 0)
        index = discriminator % 5 if discriminator else (int(user_id) >> 22) % 6
        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{index}.png"
    banner = user.get("banner")
    banner_url = image_url("banners", user_id, banner) if banner else "None"
    created = datetime.fromtimestamp(((int(user_id) >> 22) + 1420070400000) / 1000, timezone.utc)
    username = " ".join(user["username"].splitlines())
    display_name = " ".join((user.get("global_name") or username).splitlines())
    return (
        f"{username}\nDiscord ID: {user_id}\nDisplay name: {display_name}\n"
        f"Created: {created:%Y-%m-%d}\nProfile picture: {avatar_url}\nBanner: {banner_url}"
    )
