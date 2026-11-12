"""Custom emoji registry. IDs live in assets/icons.json; an empty ID means "use the plain emoji".

Get an ID by running `python scripts/list_emojis.py <PackName>`.
"""
from __future__ import annotations

import json

from ..paths import ICONS_JSON

ITEM = "⚡️"  # plain stand-in for the item_line emoji (a vanity's ".gg", a badge line)
STAR = "⭐️"  # the exact emoji a custom emoji must wrap, or Telegram ignores it

FALLBACK = {
    "start_listing": "➕", "my_listings": "🗃", "mark_sold": "💸", "how_to": "ℹ️",
    "discord": "🎮", "tiktok": "🎵", "telegram": "✈️", "other_usernames": "👤", "other_stock": "📦",
    "oge": "🔑", "not_oge": "🚫", "no_co": "⏭", "offers": "💬", "skip": "⏭",
    "all_good": "🟢", "limited": "🟡", "very_limited": "🟠", "at_risk": "🔴",
    "group_rare": "💎", "group_nitro": "🌀", "group_boosts": "💎", "group_gift": "🎁", "group_other": "⚙️",
    "back": "◀️", "cancel": "🚫", "confirm": "📨", "reject": "🚫", "approve": "👍",
}


def _load() -> dict[str, str]:
    try:
        with open(ICONS_JSON, encoding="utf-8") as f:
            return {k: str(v) for k, v in json.load(f).items() if v}
    except (OSError, ValueError):
        return {}


IDS: dict[str, str] = _load()
ALT_BY_ID: dict[str, str] = {emoji_id: FALLBACK.get(key) or STAR for key, emoji_id in IDS.items()}



def emoji_html(key: str, fallback: str = "") -> str:
    """Telegram-HTML for an emoji: a custom emoji if one is set for `key`, else the plain one."""
    plain = fallback or FALLBACK.get(key, "")
    if key in IDS:
        return f'<tg-emoji emoji-id="{IDS[key]}">{plain}</tg-emoji>'
    return plain
