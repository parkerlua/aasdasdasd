"""The public post for a listing, as Telegram HTML."""
from __future__ import annotations

import html
import re

from ..config import Settings
from ..services.emoji import STAR, emoji_html
from .flows import BADGE_GROUPS, Flow

POST_TITLES = {
    "discord_vanity": "NEW DISCORD VANITY", "discord_username": "NEW DISCORD USERNAME",
    "discord_badge": "NEW DISCORD BADGE", "telegram_username": "NEW TELEGRAM USERNAME",
    "telegram_gift": "NEW TELEGRAM GIFT", "other_usernames": "NEW HANDLE", "other_stock": "NEW ITEM",
    "tiktok_username": "NEW TIKTOK USERNAME",
}
PLURAL_TITLES = {"telegram_username": "NEW TELEGRAM USERNAMES", "discord_vanity": "NEW DISCORD VANITIES"}
DISCORD_ACCOUNTS = ("discord_username", "discord_badge")
POST_PAD = 28  # invisible characters added to text-only posts; raise it to make them wider, lower to narrow them
NO_NOTES_IN_POST = ("discord_username",)  # sellers can still write notes; only the reviewers see them

SHORT_BADGES = {  # shorter names for the post, e.g. "- Moderator, Staff, ES"
    "Early Supporter": "ES", "Discord Staff": "Staff", "Early Verified Dev": "Early Dev",
}


def vanity(item: str) -> str:
    """discord.gg/vcs, https://discord.gg/vcs, gg/vcs -> .gg/vcs  (shown without "discord.gg" so Telegram doesn't link it)"""
    item = item.strip()
    item = re.sub(r"^(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/", ".gg/", item, flags=re.I)
    return "." + item if item.lower().startswith("gg/") else item


def badge_line(badges) -> str:
    return ", ".join(html.escape(SHORT_BADGES.get(b, b)) for b in badges or [])


def all_badges(data: dict) -> list[str]:
    """Badges the seller picked plus the ones Discord itself reported for the account (no duplicates)."""
    picked = data.get("rare_badges") or data.get("badges") or []
    return list(dict.fromkeys([*picked, *(data.get("verified_badges") or [])]))


def at(name: str, contact_username: str) -> str:
    name = name.strip()
    text = html.escape(name if name.startswith("@") else f"@{name}")
    return f'<a href="https://t.me/{contact_username}">{text}</a>'  # tapping a name opens a chat with the middleman


def platform_emoji(flow_key: str) -> str:
    """Custom emoji in front of the post title: Discord, TikTok or Telegram (nothing for other listings)."""
    for prefix in ("discord", "tiktok", "telegram"):
        if flow_key.startswith(prefix):
            return emoji_html(f"post_{prefix}", STAR) + " "
    return ""


def contact_footer(settings: Settings) -> str:
    """'DM me' lines at the bottom of a post, in place of contact buttons."""
    return (f"{emoji_html('contact_line', STAR)} @{settings.contact_username}\n"
            f"{emoji_html('submit_line', STAR)} Submit Via: @{settings.submit_username}")


def build_post(flow: Flow, data: dict, settings: Settings) -> str:
    names: list[str] = []
    bullets: list[str] = []
    contact = settings.contact_username
    if flow.key == "discord_username":
        names = [at(data.get("username", ""), contact)]
    elif flow.key == "telegram_username":
        names = [at(n, contact) for n in str(data.get("usernames", "")).splitlines() if n.strip()]
    elif flow.key == "tiktok_username":
        names = [at(data.get("username", ""), contact)]
        access = data.get("tt_access")
        bullets.append("Passkey" if access in ("Passkey", "Both") else "No Passkey")
        bullets.append("Number" if access in ("Number", "Both") else "No Number")
        if data.get("tt_type"):
            bullets.append(html.escape(data["tt_type"]))
    elif flow.key == "telegram_gift":
        names = [html.escape(data.get("gift", ""))]  # plain link, so Telegram shows the gift preview
    elif flow.key == "discord_badge":
        if all_badges(data):
            bullets.append(badge_line(all_badges(data)))
    else:
        show = vanity if flow.key == "discord_vanity" else (lambda line: line)
        bullets += [html.escape(show(line)) for line in str(data.get("item", "")).splitlines() if line.strip()]
    if flow.key == "discord_username":
        rare = [b for b in all_badges(data) if b in BADGE_GROUPS["Rare"]]
        if rare:
            bullets.append(badge_line(rare))
    if flow.key in DISCORD_ACCOUNTS:
        if data.get("oge") == "OGE":
            domain = data.get("email_domain")
            if domain == "Other":
                domain = data.get("email_domain_other") or domain  # the domain they typed
            bullets.append(f"OGE ({html.escape(domain)})" if domain else "OGE")
            if data.get("pb_test") == "Accepted":
                bullets.append("Pullback Test Accepted")
        if data.get("standing"):
            bullets.append(f"Standing {html.escape(data['standing'])}")
    several = len(names) > 1 or (flow.key == "discord_vanity" and len(bullets) > 1)
    title = PLURAL_TITLES[flow.key] if several and flow.key in PLURAL_TITLES else POST_TITLES[flow.key]
    # text-only posts are narrower than photo posts; invisible blanks after the title widen the bubble to match
    head = f"{platform_emoji(flow.key)}<b>{title}</b>" + ("" if data.get("account_image") else "⠀" * POST_PAD)
    if data.get("notes") and flow.key not in NO_NOTES_IN_POST:
        bullets.append(html.escape(data["notes"]))
    co = data.get("co_amount")
    parts = [head]
    if names:
        parts.append("\n".join(names))
    if bullets:
        parts.append("\n".join(f"- {b}" for b in bullets))
    parts.append(f"BIN: {data.get('price')}\nC/O: {'none' if co is None else co}")
    body = "\n\n".join(parts) if not names else f"{head}\n" + "\n\n".join(parts[1:])
    return f"{body}\n\n{contact_footer(settings)}"
