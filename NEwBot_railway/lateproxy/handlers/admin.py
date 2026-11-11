"""Commands for approvers and the admin. Anyone else gets silence."""
from __future__ import annotations

import functools
import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..context import Services, svc
from ..db import Listing
from ..listing import FLOWS, summary
from ..listing.flows import amount
from .approval import notify_approvers

HELP = """<b>Approver commands</b>
/pending — resend every listing still waiting for review
/info <code>id</code> — everything about a listing
/search <code>text</code> — find listings by name or details
/marksold <code>id</code> — mark a listing sold
/removelisting <code>id</code> — delist and remove its post
/updatebin <code>id amount|offers</code> — change the BIN
/updateco <code>id amount|none</code> — change the C/O
/ban <code>id|@name</code> · /unban <code>id|@name</code>
/stats — counts · /health — check the connections"""


def approvers_only(fn):
    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user and svc(context).is_approver(update.effective_user):
            return await fn(update, context)
    return wrapper


async def _reply(update: Update, text: str) -> None:
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def _listing_from_args(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Listing | None:
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await _reply(update, "Give a listing id, e.g. <code>/info 12</code>")
        return None
    listing = svc(context).listings.get(int(context.args[0].lstrip("#")))
    if not listing:
        await _reply(update, "Listing not found.")
    return listing


def post_link(s: Services, listing: Listing) -> str | None:
    ch, mid = s.settings.channel, listing.channel_msg_id
    if ch is None or not mid or s.settings.posts_to_saved:
        return None
    if isinstance(ch, str):
        return f"https://t.me/{ch.lstrip('@')}/{mid}"
    return f"https://t.me/c/{str(ch).removeprefix('-100')}/{mid}"


@approvers_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, HELP)


@approvers_only
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = svc(context).listings.pending()
    if not rows:
        return await _reply(update, "Nothing is waiting for review.")
    sent = 0
    for listing in rows:
        sent += await notify_approvers(context, listing.id)
    await _reply(update, f"Resent {sent} of {len(rows)} pending listings for review.")


@approvers_only
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    listing = await _listing_from_args(update, context)
    if not listing:
        return
    s = svc(context)
    seller = listing.seller
    lines = [summary(FLOWS[listing.category], listing.data), "",
             f"Status: <b>{listing.status}</b>",
             f"Seller: {html.escape(seller['name'])} (<code>{seller['id']}</code>)" +
             (f" @{html.escape(seller['username'])}" if seller.get("username") else ""),
             f"Submitted: {html.escape(listing.created)}"]
    if listing.approved_by:
        lines.append(f"Reviewed by: <code>{listing.approved_by}</code>")
    link = post_link(s, listing)
    if link:
        lines.append(f'<a href="{link}">View the post</a>')
    await _reply(update, "\n".join(lines))


@approvers_only
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        return await _reply(update, "Usage: <code>/search keyword</code>")
    rows = svc(context).listings.search(" ".join(context.args), limit=15)
    if not rows:
        return await _reply(update, "No listings match.")
    await _reply(update, "\n".join(
        f"#{r.id} · {html.escape((r.title.splitlines() or [''])[0][:40])} · {r.status} · BIN {html.escape(str(r.data.get('price')))}"
        for r in rows))


@approvers_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = svc(context)
    counts = s.listings.counts()
    lines = ["<b>Stats</b>", f"Users: <b>{s.users.count()}</b>"]
    lines += [f"{status}: <b>{counts.get(status, 0)}</b>" for status in ("pending", "active", "sold", "rejected", "delisted")]
    await _reply(update, "\n".join(lines))


@approvers_only
async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = svc(context)
    ub = f"✅ @{s.userbot.username}" if s.userbot.ready else ("❌ not connected" if s.settings.userbot_enabled else "➖ not configured")
    lines = ["<b>Health</b>", f"Database: ✅ v{s.db.version}", f"Userbot: {ub}",
             f"Discord lookup: {'✅ on' if s.discord.enabled else '➖ off (creation date only)'}"]
    for name, chat in (("Channel", s.settings.channel), ("Approval chat", s.settings.approval_chat),
                       ("Logs", s.settings.logs_chat), ("Alerts", s.settings.alerts_chat), ("Backups", s.settings.backup_chat)):
        if chat is None:
            lines.append(f"{name}: ➖ not set")
            continue
        if chat == "me":
            lines.append(f"{name}: 💾 Saved Messages (userbot){'' if s.userbot.ready else ' ❌ userbot not connected'}")
            continue
        try:
            c = await context.bot.get_chat(chat)
            lines.append(f"{name}: ✅ {html.escape(c.title or str(chat))}")
        except Exception as e:  # noqa: BLE001
            lines.append(f"{name}: ❌ {html.escape(type(e).__name__)} ({html.escape(str(chat))})")
    await _reply(update, "\n".join(lines))


@approvers_only
async def marksold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    listing = await _listing_from_args(update, context)
    if not listing:
        return
    s = svc(context)
    if not s.listings.transition(listing.id, "active", "sold"):
        return await _reply(update, f"#{listing.id} isn't an active listing.")
    await s.publisher.mark_sold(listing)
    await s.notifier.log(f"✅ #{listing.id} marked sold by {html.escape(update.effective_user.full_name)}")
    await _reply(update, f"🔴 #{listing.id} marked sold.")


@approvers_only
async def removelisting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    listing = await _listing_from_args(update, context)
    if not listing:
        return
    s = svc(context)
    if listing.status not in ("active", "pending"):
        return await _reply(update, f"#{listing.id} is already {listing.status}.")
    s.listings.set_status(listing.id, "delisted")
    if listing.status == "active":
        await s.publisher.remove(listing)
    await s.notifier.log(f"🗑 #{listing.id} removed by {html.escape(update.effective_user.full_name)}")
    await _reply(update, f"🗑 #{listing.id} removed.")


async def _update_field(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, none_words: tuple, none_value) -> None:
    listing = await _listing_from_args(update, context)
    if not listing:
        return
    if len(context.args) < 2:
        return await _reply(update, f"Usage: <code>/{'updatebin' if field == 'price' else 'updateco'} {listing.id} amount</code>")
    raw = context.args[1].lower()
    try:
        value = none_value if raw in none_words else amount(raw)
    except ValueError as e:
        return await _reply(update, f"⚠️ {html.escape(str(e))}")
    s = svc(context)
    listing.data[field] = value
    s.listings.save_data(listing.id, listing.data)
    await s.publisher.refresh(listing, FLOWS[listing.category])
    await _reply(update, f"✅ #{listing.id} {'BIN' if field == 'price' else 'C/O'} is now <b>{html.escape(str(value))}</b>.")


@approvers_only
async def updatebin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _update_field(update, context, "price", ("offers", "offer"), "Highest Offer")


@approvers_only
async def updateco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _update_field(update, context, "co_amount", ("none", "no", "0"), None)


async def _ban(update: Update, context: ContextTypes.DEFAULT_TYPE, banned: bool) -> None:
    if not context.args:
        return await _reply(update, "Usage: <code>/ban 123456789</code> or <code>/ban @name</code>")
    s, arg = svc(context), context.args[0]
    user = s.users.get(int(arg)) if arg.lstrip("-").isdigit() else s.users.by_username(arg)
    if not user:
        return await _reply(update, "I haven't seen that user. They must have opened the bot once.")
    s.users.set_banned(user.id, banned)
    await _reply(update, f"{'🚫 Banned' if banned else '✅ Unbanned'} {html.escape(user.name)} (<code>{user.id}</code>).")


@approvers_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ban(update, context, True)


@approvers_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ban(update, context, False)

