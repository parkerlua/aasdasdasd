"""Showing a screen (text + buttons) and the screens shared by several handlers."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ..context import svc
from . import richmsg
from .buttons import ibtn

log = logging.getLogger(__name__)

BTN_START, BTN_LISTINGS, BTN_SOLD = "New Listing", "My Stock", "Mark as Sold"


def home_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [ibtn(BTN_START, "menu:new", "start_listing"), ibtn(BTN_LISTINGS, "menu:stock", "my_listings")],
        [ibtn(BTN_SOLD, "menu:sold", "mark_sold")],
    ])


def back_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[ibtn("Back", "menu:home", "back")]])


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, markup: InlineKeyboardMarkup | None = None):
    """Show a screen: edit the tapped message in place, or send a new one for commands (or if the old one is a photo).
    Uses the rich-message style (buttons inside the message); falls back to the classic style if Telegram refuses."""
    q = update.callback_query
    chat = update.effective_chat
    if svc(context).settings.rich_ui:
        try:
            if q and not q.message.photo:
                try:
                    await richmsg.edit(chat.get_bot(), chat.id, q.message.message_id, text, markup)
                except BadRequest as e:
                    if "not modified" not in str(e).lower():
                        raise
                return
            if q:
                await q.message.delete()
            return await richmsg.send(chat.get_bot(), chat.id, text, markup)
        except BadRequest as e:
            log.warning("rich message refused (%s); using the classic style", e)
    kw = dict(parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
    if q and not q.message.photo:
        try:
            return await q.edit_message_text(text, **kw)
        except BadRequest as e:
            if "not modified" in str(e):
                return
            raise
    if q:
        await q.message.delete()
    return await chat.send_message(text, **kw)


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Hey 👋 What do you want to do?"):
    context.user_data.pop("flow", None)
    await show(update, context, text, home_markup())
