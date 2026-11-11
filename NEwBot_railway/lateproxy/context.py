"""The service container: everything a handler needs, built once at startup and reached through `svc(context)`."""
from __future__ import annotations

from dataclasses import dataclass

from telegram import User as TgUser
from telegram.ext import ContextTypes

from .config import Settings
from .db import KV, Database, ListingRepo, UserRepo
from .services.discord import DiscordLookup
from .services.notifier import Notifier
from .services.publisher import Publisher
from .services.userbot import Userbot


@dataclass
class Services:
    settings: Settings
    db: Database
    listings: ListingRepo
    users: UserRepo
    kv: KV
    userbot: Userbot
    publisher: Publisher
    notifier: Notifier
    discord: DiscordLookup

    # ---------- who is who ----------
    def admin_chat_id(self) -> int:
        """The main reviewer's chat: ADMIN_ID, or the ID remembered when @ADMIN_USERNAME first talked to the bot."""
        if self.settings.admin_id:
            return self.settings.admin_id
        return int(self.kv.get("admin_id") or 0)

    def is_admin(self, user: TgUser) -> bool:
        s = self.settings
        return user.id == self.admin_chat_id() or (user.username or "").lower() == s.admin_username

    def is_approver(self, user: TgUser) -> bool:
        s = self.settings
        return (self.is_admin(user) or user.id in s.approver_ids
                or (user.username or "").lower() in s.approver_usernames)

    def review_chat(self) -> int | str | None:
        """Where new listings are sent for review: the approval chat if set, else the admin's DM."""
        return self.settings.approval_chat or self.admin_chat_id() or None


def svc(context: ContextTypes.DEFAULT_TYPE) -> Services:
    return context.application.bot_data["svc"]
