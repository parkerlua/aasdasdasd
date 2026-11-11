"""Anything a handler didn't catch: log it, tell the alerts chat, and apologise to the user."""
from __future__ import annotations

import html
import logging
import traceback

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, NetworkError):  # transient: Telegram or the network hiccuped, polling retries by itself
        log.warning("network error: %s", err)
        return
    log.error("unhandled error", exc_info=err)
    svc = context.application.bot_data.get("svc")
    if svc:
        tb = "".join(traceback.format_exception_only(type(err), err)).strip()
        await svc.notifier.alert(f"⚠️ <b>Error</b>\n<code>{html.escape(tb[-600:])}</code>")
    if isinstance(update, Update):
        try:
            if update.callback_query:
                await update.callback_query.answer("Something went wrong. Try again.", show_alert=True)
            elif update.effective_message and update.effective_chat and update.effective_chat.type == "private":
                await update.effective_message.reply_text("Something went wrong. Please try again.")
        except Exception:  # noqa: BLE001
            pass
