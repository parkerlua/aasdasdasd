"""Puts approved listings in front of buyers, and keeps those posts up to date.

It picks the best way available:
  userbot  a Premium account posts to the channel (real custom emojis)
  saved    CHANNEL_ID=me: the Premium account posts to its own Saved Messages (needs the userbot, no channel)
  bot      the bot posts to the channel (custom emojis fall back to plain ones)
  dm       no channel configured: the finished post is sent to the reviewer, who posts it themselves
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from ..config import SAVED_MESSAGES, Settings
from ..db import Listing
from ..listing import Flow, build_post
from .userbot import Userbot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishResult:
    mode: str  # userbot | saved | bot | dm
    message_id: int | None = None


class Publisher:
    def __init__(self, bot: Bot, settings: Settings, userbot: Userbot):
        self.bot, self.settings, self.userbot = bot, settings, userbot

    # ---------- helpers ----------
    def _text(self, flow: Flow, listing: Listing) -> str:
        return build_post(flow, listing.data, self.settings)

    async def _photo_bytes(self, file_id: str) -> bytes:
        file = await self.bot.get_file(file_id)
        return bytes(await file.download_as_bytearray())

    async def _attach_button(self, message_id: int) -> None:
        """Optional single button under a post. Only a bot can attach inline buttons, even to a userbot's post."""
        s = self.settings
        if not (s.channel and s.post_button_text and s.post_button_url) or s.channel == SAVED_MESSAGES:
            return  # (a bot can't reach the userbot's Saved Messages)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(s.post_button_text, url=s.post_button_url)]])
        try:
            await self.bot.edit_message_reply_markup(s.channel, message_id, reply_markup=kb)
        except TelegramError as e:
            log.warning("couldn't attach the post button to message %s: %s", message_id, e)

    # ---------- publish ----------
    async def publish(self, listing: Listing, flow: Flow, *, dm_chat_id: int | None = None) -> PublishResult:
        """Raises if nothing could be posted, so the approval can be retried."""
        if self.settings.selection_only:
            raise RuntimeError("Posting is switched off (SELECTION_ONLY).")
        text, image = self._text(flow, listing), listing.data.get("account_image")
        channel = self.settings.channel
        saved = channel == SAVED_MESSAGES

        if channel is not None and self.userbot.ready:
            photo = await self._photo_bytes(image) if image else None
            message_id = await self.userbot.send(channel, text, photo)
            await self._attach_button(message_id)
            return PublishResult("saved" if saved else "userbot", message_id)

        if channel is not None and not saved:
            if image:
                msg = await self.bot.send_photo(channel, image, caption=text, parse_mode=ParseMode.HTML)
            else:
                msg = await self.bot.send_message(channel, text, parse_mode=ParseMode.HTML,
                                                  disable_web_page_preview=flow.key != "telegram_gift")
            await self._attach_button(msg.message_id)
            return PublishResult("bot", msg.message_id)

        if dm_chat_id is None:
            raise RuntimeError("Nothing to post to (no channel, or the userbot isn't connected) and the reviewer's chat isn't known yet.")
        await self.send_to_chat(dm_chat_id, flow, listing.data,
                                f"📋 Listing #{listing.id} approved. Post the message below:")
        return PublishResult("dm")

    async def send_preview(self, chat_id, flow: Flow, data: dict, header: str) -> str:
        """A finished post for checking, nothing posted. To Saved Messages if that's where posts go and the userbot is
        connected (so custom emojis show), otherwise to `chat_id`. Returns "saved" or "dm"."""
        if self.settings.posts_to_saved and self.userbot.ready:
            image = data.get("account_image")
            photo = await self._photo_bytes(image) if image else None
            await self.userbot.send(SAVED_MESSAGES, html.escape(header))
            await self.userbot.send(SAVED_MESSAGES, build_post(flow, data, self.settings), photo)
            return "saved"
        await self.send_to_chat(chat_id, flow, data, header)
        return "dm"

    async def send_to_chat(self, chat_id, flow: Flow, data: dict, header: str) -> None:
        """DM a finished post: a short header, then the post exactly as it would appear in the channel."""
        text, image = build_post(flow, data, self.settings), data.get("account_image")
        await self.bot.send_message(chat_id, header)
        if image and len(text) <= 1000:  # a photo caption holds at most 1024 characters
            await self.bot.send_photo(chat_id, image, caption=text, parse_mode=ParseMode.HTML)
            return
        if image:
            await self.bot.send_photo(chat_id, image)
        await self.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=flow.key != "telegram_gift")

    # ---------- keep the post in sync ----------
    async def _rewrite(self, listing: Listing, text: str, *, buttons: bool) -> bool:
        channel, mid = self.settings.channel, listing.channel_msg_id
        if channel is None or not mid or self.settings.selection_only:
            return False
        if channel == SAVED_MESSAGES and not self.userbot.ready:
            return False  # only the userbot can reach Saved Messages
        try:
            if self.userbot.ready:
                await self.userbot.edit(channel, mid, text)
                if buttons:
                    await self._attach_button(mid)  # a userbot edit wipes the button, so put it back
            else:
                if listing.data.get("account_image"):
                    await self.bot.edit_message_caption(channel, mid, caption=text, parse_mode=ParseMode.HTML)
                else:
                    await self.bot.edit_message_text(text, channel, mid, parse_mode=ParseMode.HTML,
                                                     disable_web_page_preview=True)
                if buttons:
                    await self._attach_button(mid)
            return True
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return True
            log.warning("couldn't edit channel post %s: %s", mid, e)
        except Exception as e:  # noqa: BLE001
            log.warning("couldn't edit channel post %s: %s", mid, e)
        return False

    async def refresh(self, listing: Listing, flow: Flow) -> bool:
        return await self._rewrite(listing, self._text(flow, listing), buttons=True)

    async def mark_sold(self, listing: Listing) -> bool:
        return await self._rewrite(listing, self.settings.sold_text, buttons=False)

    async def remove(self, listing: Listing) -> bool:
        channel, mid = self.settings.channel, listing.channel_msg_id
        if channel is None or not mid or self.settings.selection_only:
            return False
        if channel == SAVED_MESSAGES and not self.userbot.ready:
            return False
        try:
            if self.userbot.ready:
                await self.userbot.delete(channel, mid)
            else:
                await self.bot.delete_message(channel, mid)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("couldn't delete channel post %s: %s", mid, e)
        return await self._rewrite(listing, "🗑 <b>DELISTED</b>", buttons=False)
