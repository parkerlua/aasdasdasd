"""Inline buttons with optional custom-emoji icons (IDs come from assets/icons.json)."""
from __future__ import annotations

from telegram import InlineKeyboardButton

from ..services.emoji import FALLBACK, IDS

SELECTED = "selected"  # a picked option: always green
GREEN = "green"  # always green
RED = "red"      # always red
USE_COLORS = False  # True = also apply every other style passed to ibtn (primary / success / danger)


# Plain (non-custom) emojis in button text are only used on the category selection page ("What are you selling?").
# Every other button gets its custom emoji if one is set in assets/icons.json, and is otherwise just text.
PLAIN_EMOJI_ICONS = frozenset({"discord", "telegram", "tiktok", "other_usernames", "other_stock"})


def label(text: str, icon: str | None) -> str:
    """Button text. A custom icon is attached separately; a plain emoji is inlined only for the selection page."""
    if icon in PLAIN_EMOJI_ICONS and icon not in IDS:
        return f"{FALLBACK.get(icon, '')} {text}".strip()
    return text


def _extra(icon: str | None, style: str | None) -> dict:
    extra = {}
    if icon in IDS:
        extra["icon_custom_emoji_id"] = IDS[icon]
    if style in (SELECTED, GREEN):
        extra["style"] = "success"
    elif style == RED:
        extra["style"] = "danger"
    elif style and USE_COLORS:
        extra["style"] = style
    return extra


def ibtn(text: str, data: str, icon: str | None = None, style: str | None = None) -> InlineKeyboardButton:
    """A callback button."""
    return InlineKeyboardButton(label(text, icon), callback_data=data, **_extra(icon, style))

