"""Review: new listings go to the approval chat (or the admin's DM); any approver can Yes/No them.

Yes publishes the listing (userbot / bot / DM, see services/publisher.py). Two approvers tapping at once can't
double-post: the status change is atomic and only the first one wins.
"""
from __future__ import annotations

import html
import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..context import Services, svc
from ..db import Listing
from ..listing import FLOWS, summary
from ..ui.buttons import ibtn

log = logging.getLogger(__name__)
PROMPT = "<b>Post this listing?</b>"
CAPTION_LIMIT = 1000


def seller_link(seller: dict) -> str:
    name = html.escape(seller["name"])
    if seller.get("username"):
        return f'<a href="https://t.me/{seller["username"]}">{name}</a>'
    return f'<a href="tg://user?id={seller["id"]}">{name}</a>'


def review_markup(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[ibtn("Yes", f"appr:{listing_id}", "approve"), ibtn("No", f"rej:{listing_id}", "reject")]])


async def send_listing(bot, chat_id, listing: Listing, *, header: str = "", footer: str = "", markup=None):
    """The listing summary, with its image on top when it has one (caption too long -> image, then text)."""
    text = f"{header}{summary(FLOWS[listing.category], listing.data)}{footer}"
    image = listing.data.get("account_image")
    if image and len(text) <= CAPTION_LIMIT:
        return await bot.send_photo(chat_id, image, caption=text, reply_markup=markup, parse_mode=ParseMode.HTML)
    if image:
        await bot.send_photo(chat_id, image)
    return await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=ParseMode.HTML,
                                  disable_web_page_preview=True)


async def notify_approvers(context: ContextTypes.DEFAULT_TYPE, listing_id: int) -> bool:
    s: Services = svc(context)
    listing = s.listings.get(listing_id)
    if not listing or listing.status != "pending" or s.settings.selection_only:
        return False
    chat = s.review_chat()
    if not chat:
        log.warning("@%s hasn't opened the bot yet and no approval chat is set - listing #%s stays pending",
                    s.settings.admin_username, listing_id)
        return False
    seller = listing.seller
    try:
        await send_listing(
            context.bot, chat, listing, markup=review_markup(listing_id),
            header=f"🆕 <b>New listing #{listing_id}</b>\nSeller: {seller_link(seller)} (<code>{seller['id']}</code>)\n\n",
            footer=f"\n\n{PROMPT}")
        if listing.data.get("proof_image"):
            await context.bot.send_photo(chat, listing.data["proof_image"],
                                         caption=f"Real screenshot (private proof) for #{listing_id}")
        if listing.data.get("co_proof"):
            await context.bot.send_photo(chat, listing.data["co_proof"], caption=f"C/O proof for #{listing_id}")
        return True
    except Exception as e:  # noqa: BLE001
        log.exception("couldn't send listing #%s for review", listing_id)
        await s.notifier.alert(f"⚠️ Couldn't send listing #{listing_id} for review: {html.escape(str(e))}")
        return False


async def _tell_seller(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str) -> None:
    try:
        await context.bot.send_message(user_id, text)
    except Exception as e:  # noqa: BLE001  (they may have blocked the bot)
        log.info("couldn't message seller %s: %s", user_id, e)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    action, _, arg = q.data.partition(":")
    s, user = svc(context), update.effective_user
    if s.settings.selection_only:
        return await q.answer("Reviews are switched off in test mode.", show_alert=True)
    if not s.is_approver(user):
        return await q.answer("Not allowed.", show_alert=True)
    listing_id = int(arg)
    listing = s.listings.get(listing_id)
    if not listing or listing.status != "pending":
        return await q.answer("Already handled.", show_alert=True)
    flow = FLOWS[listing.category]
    who = html.escape(user.full_name)

    if action == "rej":
        if not s.listings.transition(listing_id, "pending", "rejected", approved_by=user.id):
            return await q.answer("Already handled.", show_alert=True)
        verdict = f"❌ Declined #{listing_id} by {who}"
        await _tell_seller(context, listing.user_id, f"❌ Your listing #{listing_id} was rejected.")
    else:
        if not s.listings.transition(listing_id, "pending", "active", approved_by=user.id):
            return await q.answer("Already handled.", show_alert=True)  # someone else got there first
        try:
            result = await s.publisher.publish(listing, flow, dm_chat_id=user.id)
        except Exception as e:  # noqa: BLE001
            s.listings.set_status(listing_id, "pending")  # put it back so it can be retried
            log.exception("publishing listing #%s failed", listing_id)
            await s.notifier.alert(f"⚠️ Publishing listing #{listing_id} failed: {html.escape(str(e))}")
            return await q.answer(f"Couldn't post: {e}"[:190], show_alert=True)
        if result.message_id:
            s.listings.set_channel_msg(listing_id, result.message_id)
        if result.mode == "dm":
            verdict = f"✅ Approved #{listing_id} by {who} (post sent to your DM)"
            await _tell_seller(context, listing.user_id, f"✅ Your listing #{listing_id} was approved and will be posted shortly.")
        else:
            verdict = f"✅ Approved #{listing_id} by {who} · posted ({result.mode})"
            await _tell_seller(context, listing.user_id, f"✅ Your listing #{listing_id} was approved and posted.")
    await s.notifier.log(verdict)
    await q.answer()
    body = (q.message.caption_html if q.message.caption is not None else q.message.text_html)
    body = body.replace(PROMPT, "").rstrip()
    if q.message.caption is not None:
        await q.edit_message_caption(f"{body}\n\n<b>{verdict}</b>", parse_mode=ParseMode.HTML)
    else:
        await q.edit_message_text(f"{body}\n\n<b>{verdict}</b>", parse_mode=ParseMode.HTML, disable_web_page_preview=True)
