"""Settings, read once from environment variables (a .env file locally, Railway variables in production).

Every value is stripped, so a stray newline pasted into a Railway variable can't break the bot.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .paths import DATA_DIR


SAVED_MESSAGES = "me"  # CHANNEL_ID=me posts to the userbot account's own Saved Messages (no channel needed)


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


def _str(env: Mapping[str, str], key: str, default: str = "") -> str:
    return (env.get(key) or default).strip()


def _int(env: Mapping[str, str], key: str, default: int = 0) -> int:
    raw = _str(env, key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from None


def _flag(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = _str(env, key)
    if not raw:
        return default
    return raw.lower() not in ("0", "false", "no", "off")


def _chat(env: Mapping[str, str], key: str) -> int | str | None:
    """A chat reference: numeric id (-100123...), or @username. Empty -> None."""
    raw = _str(env, key)
    if not raw:
        return None
    if raw.lower() in ("me", "self", "saved", "saved messages", "savedmessages"):
        return SAVED_MESSAGES
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw if raw.startswith("@") else f"@{raw}"


def _names(env: Mapping[str, str], key: str) -> frozenset[str]:
    return frozenset(p.strip().lstrip("@").lower() for p in _str(env, key).split(",") if p.strip())


def _ids(env: Mapping[str, str], key: str) -> frozenset[int]:
    out = set()
    for p in _str(env, key).split(","):
        p = p.strip()
        if p:
            if not p.lstrip("-").isdigit():
                raise ConfigError(f"{key} must be comma separated numbers, got {p!r}")
            out.add(int(p))
    return frozenset(out)


@dataclass(frozen=True)
class Settings:
    # Telegram bot
    bot_token: str
    # People
    admin_username: str = "late"
    admin_id: int = 0
    approver_usernames: frozenset[str] = frozenset()
    approver_ids: frozenset[int] = frozenset()
    # Chats
    channel: int | str | None = None        # public channel listings are posted to (empty = DM the admin instead)
    approval_chat: int | str | None = None  # private chat where approvers see new listings (empty = DM the admin)
    logs_chat: int | str | None = None
    alerts_chat: int | str | None = None
    backup_chat: int | str | None = None
    backup_hour_utc: int = 4
    # Text shown on posts
    contact_username: str = "floral"
    submit_username: str = "LateProxyApp"
    card_tag: str = ""
    sold_text: str = "✅ SOLD"
    post_button_text: str = ""
    post_button_url: str = ""
    # Premium userbot (posts to the channel with custom emojis)
    userbot_api_id: int = 0
    userbot_api_hash: str = ""
    userbot_session: str = ""
    # Discord lookup (fills the profile card from the account's ID)
    discord_token: str = ""
    card_blur_avatar: bool = True
    # Runtime
    db_path: Path = DATA_DIR / "listings.db"
    rich_ui: bool = True
    selection_only: bool = False  # test mode: nothing is submitted, reviewed or posted
    test_flows: frozenset[str] = frozenset()  # in test mode, these categories still get the full question flow

    @property
    def posts_to_saved(self) -> bool:
        return self.channel == SAVED_MESSAGES

    @property
    def userbot_enabled(self) -> bool:
        return bool(self.userbot_api_id and self.userbot_api_hash and self.userbot_session)

    @property
    def card_tag_text(self) -> str:
        return self.card_tag or "t.me/late"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    token = _str(env, "BOT_TOKEN")
    if not token:
        raise ConfigError("Set BOT_TOKEN (get one from @BotFather).")
    contact = _str(env, "CONTACT_USERNAME", "floral").lstrip("@")
    return Settings(
        bot_token=token,
        admin_username=_str(env, "ADMIN_USERNAME", "late").lstrip("@").lower(),
        admin_id=_int(env, "ADMIN_ID"),
        approver_usernames=_names(env, "APPROVER_USERNAMES"),
        approver_ids=_ids(env, "APPROVER_IDS"),
        channel=_chat(env, "CHANNEL_ID"),
        approval_chat=_chat(env, "APPROVAL_CHAT_ID"),
        logs_chat=_chat(env, "LOGS_CHAT_ID"),
        alerts_chat=_chat(env, "ALERTS_CHAT_ID"),
        backup_chat=_chat(env, "BACKUP_CHAT_ID"),
        backup_hour_utc=_int(env, "BACKUP_HOUR_UTC", 4) % 24,
        contact_username=contact,
        submit_username=_str(env, "SUBMIT_USERNAME", "LateProxyApp").lstrip("@"),
        card_tag=_str(env, "CARD_TAG"),
        sold_text=_str(env, "SOLD_TEXT", "✅ SOLD"),
        post_button_text=_str(env, "POST_BUTTON_TEXT"),
        post_button_url=_str(env, "POST_BUTTON_URL"),
        userbot_api_id=_int(env, "USERBOT_API_ID"),
        userbot_api_hash=_str(env, "USERBOT_API_HASH"),
        userbot_session=_str(env, "USERBOT_SESSION"),
        discord_token=_str(env, "DISCORD_TOKEN"),
        card_blur_avatar=_flag(env, "CARD_BLUR_AVATAR", True),
        db_path=Path(_str(env, "DB_PATH") or DATA_DIR / "listings.db"),
        rich_ui=_flag(env, "RICH_UI", True),
        selection_only=_flag(env, "SELECTION_ONLY", False),
        test_flows=frozenset(p.strip().lower() for p in _str(env, "TEST_FLOWS").split(",") if p.strip()),
    )
