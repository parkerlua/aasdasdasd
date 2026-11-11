"""Admin forwards a post from the channel -> offer to add it back into the database."""
from __future__ import annotations

import html

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, filters

from ..context import svc
from ..listing import FLOWS, summary
from ..listing.importer import parse_post
from ..ui.buttons import ibtn
from ..ui.screens import show


class AdminOnly(filters.MessageFilter):
    """Messages from the admin, even if they change their username."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def filter(self, message) -> bool:
        return bool(message.from_user) and self.app.bot_data["svc"].is_admin(message.from_user)


async def on_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s, msg = svc(context), update.message
    origin = msg.forward_origin
    if s.settings.channel is None or s.settings.posts_to_saved:
        return await msg.reply_text("Importing needs a real channel in CHANNEL_ID, so there's nothing to import from.")
    if not origin or origin.type != "channel":
        return await msg.reply_text("Forward a post from your channel and I can add it to the database.")
    wanted = str(s.settings.channel).lstrip("@").lower()
    if wanted not in (str(origin.chat.id), (origin.chat.username or "").lower()):
        return await msg.reply_text("That post isn't from your channel.")
    existing = s.listings.find_by_channel_msg(origin.message_id)
    if existing:
        return await msg.reply_text(f"That post is already in the database as #{existing.id}.")
    parsed = parse_post(msg.text or msg.caption or "", msg.photo[-1].file_id if msg.photo else None)
    if not parsed:
        return await msg.reply_text("I couldn't read that post.")
    key, data = parsed
    context.user_data["import"] = {"flow": key, "data": data, "msg_id": origin.message_id, "step": "confirm"}
    await show(update, context, summary(FLOWS[key], data), InlineKeyboardMarkup([
        [ibtn("Add listing to DB", "imp:go")], [ibtn("Cancel", "imp:no", "cancel")]]))


async def save_import(update: Update, context: ContextTypes.DEFAULT_TYPE, seller: dict) -> None:
    s = svc(context)
    imp = context.user_data.pop("import")
    flow, data = FLOWS[imp["flow"]], imp["data"]
    data["_seller"] = seller
    title = data.get(flow.title_key) or flow.name
    title = ", ".join(title) if isinstance(title, list) else str(title)
    listing = s.listings.create(seller["id"], flow.key, title, data, status="active", channel_msg_id=imp["msg_id"])
    await show(update, context, f"✅ Added as #{listing.id} for {html.escape(seller['name'])}.",
               InlineKeyboardMarkup([[ibtn("Open it", f"l:{listing.id}")]]))


async def on_owner_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = svc(context)
    text = update.message.text.strip().lstrip("@")
    user = s.users.get(int(text)) if text.isdigit() else s.users.by_username(text)
    if text.isdigit():
        seller = {"id": int(text), "username": (user.username if user else "") or None,
                  "name": user.name if user else f"User {text}"}
    elif user:
        seller = {"id": user.id, "username": user.username or None, "name": user.name}
    else:
        return await update.message.reply_text(
            f"I haven't seen @{html.escape(text)} yet. Ask them to open the bot and send /start, then send their "
            "@username again, or send their numeric ID.")
    await save_import(update, context, seller)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = svc(context)
    action, _, arg = update.callback_query.data.partition(":")
    imp = context.user_data.get("import")
    if not imp or not s.is_admin(update.effective_user):
        return await show(update, context, "Nothing to add. Forward a channel post to me first.")
    if arg == "no":
        context.user_data.pop("import")
        return await show(update, context, "Cancelled.")
    if arg == "go":
        imp["step"] = "owner"
        return await show(update, context, "Whose listing is it?\nSend their @username (they must have opened the bot) "
                                           "or their numeric ID. Or tap <b>Mine</b>.", InlineKeyboardMarkup([
            [ibtn("Mine", "imp:me")], [ibtn("Cancel", "imp:no", "cancel")]]))
    u = update.effective_user
    await save_import(update, context, {"id": u.id, "username": u.username, "name": u.full_name})
