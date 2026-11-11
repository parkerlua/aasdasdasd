"""Messages to the private logs / alerts chats. Never raises: a broken log chat must not break the bot."""
from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ParseMode

from ..config import Settings

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, settings: Settings):
        self.bot, self.settings = bot, settings

    async def _send(self, chat, text: str) -> None:
        if chat is None:
            return
        try:
            await self.bot.send_message(chat, text[:4000], parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001
            log.warning("couldn't send to chat %s: %s", chat, e)

    async def log(self, text: str) -> None:
        await self._send(self.settings.logs_chat, text)

    async def alert(self, text: str) -> None:
        await self._send(self.settings.alerts_chat, text)
