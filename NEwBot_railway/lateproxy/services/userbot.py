"""The Premium userbot: a real Telegram account (via Telethon) that posts to the channel.

Why it exists: a bot can't send custom emojis into a channel unless it owns a Fragment username, but a Premium
*user* account can. So listings are posted by this account, and the regular bot only does the rest.

The login is a StringSession kept in the USERBOT_SESSION variable (create it once with scripts/userbot_login.py),
so it works on hosts like Railway where files don't survive a redeploy. Treat that string like a password.
"""
from __future__ import annotations

import io
import logging

from ..config import Settings
from .entities import html_to_telethon

log = logging.getLogger(__name__)


class Userbot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self.username: str | None = None

    @property
    def ready(self) -> bool:
        return self._client is not None

    async def start(self) -> None:
        s = self.settings
        if not s.userbot_enabled:
            log.info("Userbot not configured: posts will use plain emoji (set USERBOT_API_ID/HASH/SESSION to enable).")
            return
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            client = TelegramClient(StringSession(s.userbot_session), s.userbot_api_id, s.userbot_api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                log.error("Userbot session is not logged in. Create a new one with scripts/userbot_login.py.")
                await client.disconnect()
                return
            me = await client.get_me()
            try:
                await client.get_dialogs()  # a fresh session knows no chats; Telethon needs to have seen the channel
            except Exception as e:  # noqa: BLE001
                log.warning("Userbot: couldn't load its chat list: %s", e)
            self._client, self.username = client, me.username
            log.info("Userbot started as @%s (Premium: %s)", me.username, getattr(me, "premium", False))
            if not getattr(me, "premium", False):
                log.warning("That account has no Telegram Premium, so custom emojis won't show in posts.")
            if s.channel is not None:
                try:
                    await client.get_input_entity(s.channel)
                except Exception:  # noqa: BLE001
                    log.error("Userbot @%s can't see the channel %s. Add that account to the channel as an admin "
                              "(post + edit messages), then restart.", me.username, s.channel)
        except Exception as e:  # noqa: BLE001
            log.error("Userbot failed to start: %s", e)
            self._client = None

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def send(self, channel, html_text: str, photo: bytes | None = None, photo_name: str = "photo.png") -> int:
        """Post `html_text` (Telegram HTML, custom emojis included) with an optional photo. Returns the message id."""
        text, entities = html_to_telethon(html_text)
        if photo:
            buf = io.BytesIO(photo)
            buf.name = photo_name
            msg = await self._client.send_file(channel, file=buf, caption=text, formatting_entities=entities,
                                               parse_mode=None)
        else:
            msg = await self._client.send_message(channel, text, formatting_entities=entities, parse_mode=None,
                                                  link_preview=False)
        return msg.id

    async def edit(self, channel, message_id: int, html_text: str) -> None:
        """Replace a post's text (or a photo post's caption). NOTE: this clears any inline buttons on the post."""
        text, entities = html_to_telethon(html_text)
        await self._client.edit_message(channel, message_id, text=text, formatting_entities=entities,
                                        parse_mode=None, link_preview=False)

    async def delete(self, channel, message_id: int) -> None:
        await self._client.delete_messages(channel, [message_id])
