"""Runs before everything else on every update: remembers who people are, learns the admin's chat, blocks banned users."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from ..context import svc

log = logging.getLogger(__name__)


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat = update.effective_user, update.effective_chat
    if not user or user.is_bot:
        return
    s = svc(context)
    s.users.upsert(user.id, user.username, user.full_name)

    # The first time @ADMIN_USERNAME talks to the bot, remember their chat so the bot can message them.
    st = s.settings
    if (not st.admin_id and (user.username or "").lower() == st.admin_username
            and s.admin_chat_id() != user.id):
        s.kv.set("admin_id", str(user.id))
        log.info("learned the admin's chat id (@%s)", user.username)
        from .approval import notify_approvers  # local import: approval -> wizard-free, but keeps startup light
        for listing in s.listings.pending():  # anything submitted before they first opened the bot
            await notify_approvers(context, listing.id)

    if chat and chat.type == "private" and s.users.is_banned(user.id) and not s.is_admin(user):
        if update.callback_query:
            await update.callback_query.answer("You can't use this bot.", show_alert=True)
        elif update.message:
            await update.message.reply_text("🚫 You can't use this bot.")
        raise ApplicationHandlerStop
