"""Discord account lookup, so the profile card is built from real data instead of typed-in text.

- The creation date comes from the ID itself (a Discord "snowflake" encodes the time), so it needs no token.
- Username, display name, avatar and the public badge flags come from Discord's API, which needs a Discord
  *bot* token (DISCORD_TOKEN). Without one the wizard just asks the seller for those instead.
- Nitro and boost badges aren't public on the API, so sellers still declare those.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

API = "https://discord.com/api/v10"
CDN = "https://cdn.discordapp.com"
DISCORD_EPOCH_MS = 1420070400000

# public_flags bit -> the badge name used by the bot (see listing/flows.py BADGE_GROUPS and services/profile_card.py)
FLAG_BADGES: list[tuple[int, str]] = [
    (1 << 0, "Discord Staff"),
    (1 << 1, "Partner"),
    (1 << 2, "HypeSquad Events"),
    (1 << 3, "Green Bug Hunter"),
    (1 << 6, "HypeSquad Bravery"),
    (1 << 7, "HypeSquad Brilliance"),
    (1 << 8, "HypeSquad Balance"),
    (1 << 9, "Early Supporter"),
    (1 << 14, "Golden Bug Hunter"),
    (1 << 17, "Early Verified Dev"),
    (1 << 18, "Mod Alumni"),
    (1 << 22, "Active Developer"),
]


def snowflake_to_datetime(snowflake: int | str) -> dt.datetime:
    ms = (int(snowflake) >> 22) + DISCORD_EPOCH_MS
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)


def format_created(when: dt.datetime) -> str:
    return f"{when.strftime('%b')} {when.day}, {when.year}"


def badges_from_flags(flags: int) -> list[str]:
    return [name for bit, name in FLAG_BADGES if flags & bit]


@dataclass(frozen=True)
class DiscordProfile:
    id: str
    username: str
    display_name: str | None
    avatar_url: str
    flags: int
    created: dt.datetime

    @property
    def badges(self) -> list[str]:
        return badges_from_flags(self.flags)


def avatar_url(user_id: str, avatar_hash: str | None, size: int = 256) -> str:
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"{CDN}/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"
    return f"{CDN}/embed/avatars/{(int(user_id) >> 22) % 6}.png"


class DiscordLookup:
    def __init__(self, token: str = "", client: httpx.AsyncClient | None = None):
        self.token = token.strip()
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10)
        return self._client

    async def fetch(self, user_id: str) -> DiscordProfile | None:
        """The account's public profile, or None (no token, unknown ID, or Discord unreachable)."""
        if not self.enabled:
            return None
        auth = self.token if self.token.lower().startswith("bot ") else f"Bot {self.token}"
        try:
            r = await self._http().get(f"{API}/users/{user_id}", headers={"Authorization": auth})
        except httpx.HTTPError as e:
            log.warning("discord lookup failed: %s", type(e).__name__)
            return None
        if r.status_code != 200:
            log.info("discord lookup for %s -> HTTP %s", user_id, r.status_code)
            return None
        j = r.json()
        return DiscordProfile(
            id=str(j["id"]), username=j.get("username", ""), display_name=j.get("global_name"),
            avatar_url=avatar_url(str(j["id"]), j.get("avatar")), flags=int(j.get("public_flags") or 0),
            created=snowflake_to_datetime(j["id"]))

    async def download(self, url: str) -> bytes | None:
        try:
            r = await self._http().get(url)
            return r.content if r.status_code == 200 else None
        except httpx.HTTPError:
            return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
