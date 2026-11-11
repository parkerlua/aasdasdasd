"""My Stock: browse, edit, delist and mark-as-sold. Sellers see their own listings; the admin sees everyone's."""
from __future__ import annotations

import html

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..context import svc
from ..db import Listing
from ..listing import FLOWS, summary
from ..listing.flows import amount
from ..ui.buttons import ibtn
from ..ui.screens import back_markup, show

STATUS_ICON = {"active": "🟢", "pending": "⏳", "sold": "✅", "rejected": "❌", "delisted": "🗑"}
EDIT_FIELDS = {"bin": ("price", "BIN"), "co": ("co_amount", "C/O"), "notes": ("notes", "Notes")}
PAGE_SIZE = 8  # listings per page


def stock_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[ibtn("Back", "menu:stock", "back")]])


def paginate(rows: list, page: int):
    """(rows on this page, the page number kept in range, total pages)"""
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    return rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], page, pages


def page_nav(prefix: str, page: int, pages: int) -> list:
    """The ◀ 2/5 ▶ row, or nothing when everything fits on one page."""
    if pages < 2:
        return []
    return [[ibtn("◀", f"{prefix}:{(page - 1) % pages}"), ibtn(f"{page + 1}/{pages}", "noop"),
             ibtn("▶", f"{prefix}:{(page + 1) % pages}")]]


def _first_line(title: str, n: int) -> str:
    return (title.splitlines() or [""])[0][:n]


def _can_manage(update: Update, context, listing: Listing) -> bool:
    s = svc(context)
    return s.is_admin(update.effective_user) or update.effective_user.id == listing.user_id


def _editable(update: Update, context, listing: Listing) -> bool:
    """Sellers can edit live listings; the admin can also fix a pending one before approving it."""
    return listing.status == "active" or (listing.status == "pending" and svc(context).is_admin(update.effective_user))


def _mine(update: Update, context, status: str | None = None) -> list[Listing]:
    s = svc(context)
    owner = None if s.is_admin(update.effective_user) else update.effective_user.id
    return s.listings.for_user(owner, status)


# ---------- screens ----------
async def my_listings(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    rows = _mine(update, context)
    if not rows:
        return await show(update, context, "You have no listings yet.", back_markup())
    shown, page, pages = paginate(rows, page)
    context.user_data["stock_page"] = page  # so Back from a listing returns to this page
    admin = svc(context).is_admin(update.effective_user)
    kb = []
    for ls in shown:
        seller = f" · {ls.seller['name'][:10]}" if admin else ""
        kb.append([ibtn(f"{STATUS_ICON[ls.status]} #{ls.id} · {_first_line(ls.title, 22)}{seller}", f"l:{ls.id}")])
    kb += page_nav("sp", page, pages)
    kb.append([ibtn("Back", "menu:home", "back")])
    await show(update, context, f"<b>Your stock</b> ({len(rows)})\nTap a listing to edit it.", InlineKeyboardMarkup(kb))


async def view_listing(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id: int) -> None:
    ls = svc(context).listings.get(listing_id)
    if not ls or not _can_manage(update, context, ls):
        return await show(update, context, "Listing not found.", stock_back())
    admin = svc(context).is_admin(update.effective_user)
    seller = f"Seller: {html.escape(ls.seller['name'])}\n" if admin else ""
    text = f"{seller}{summary(FLOWS[ls.category], ls.data)}\n\nStatus: {STATUS_ICON[ls.status]} <b>{ls.status}</b>"
    rows = []
    if ls.status == "active" or (admin and ls.status == "pending"):
        rows += [[ibtn("Edit BIN", f"e:bin:{ls.id}"), ibtn("Edit C/O", f"e:co:{ls.id}")],
                 [ibtn("Edit notes", f"e:notes:{ls.id}")],
                 [ibtn("Mark sold", f"sold:{ls.id}"), ibtn("Delist", f"dl:{ls.id}")]
                 if ls.status == "active" else [ibtn("Withdraw", f"dl:{ls.id}")]]
    elif ls.status == "pending":
        rows.append([ibtn("Withdraw", f"dl:{ls.id}")])
    rows.append([ibtn("Back", f"sp:{context.user_data.get('stock_page', 0)}", "back")])
    await show(update, context, text, InlineKeyboardMarkup(rows))


async def mark_sold_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    rows = _mine(update, context, "active")
    if not rows:
        return await show(update, context, "You have no active listings.", back_markup())
    shown, page, pages = paginate(rows, page)
    kb = [[ibtn(f"#{ls.id} · {_first_line(ls.title, 30)}", f"sold:{ls.id}", None, "primary")] for ls in shown]
    kb += page_nav("mp", page, pages)
    kb.append([ibtn("Cancel", "menu:home", "cancel")])
    await show(update, context, "Which listing was sold?", InlineKeyboardMarkup(kb))


# ---------- editing ----------
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, listing_id: int) -> None:
    ls = svc(context).listings.get(listing_id)
    if not ls or not _can_manage(update, context, ls) or not _editable(update, context, ls):
        return await show(update, context, "That listing can't be edited.", stock_back())
    context.user_data["edit"] = {"id": listing_id, "field": field}
    prompt, preset = {
        "bin": ("💵 <b>New BIN?</b>\nType a price, or tap <b>Open to offers</b>.", "Open to offers"),
        "co": ("💰 <b>New C/O?</b>\nType the amount, or tap <b>No C/O</b>.", "No C/O"),
        "notes": ("📝 <b>New notes?</b>\nType them, or tap <b>No notes</b>.", "No notes"),
    }[field]
    await show(update, context, prompt, InlineKeyboardMarkup([
        [ibtn(preset, f"ev:{field}:{listing_id}")], [ibtn("Cancel", f"l:{listing_id}", "cancel")]]))


async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, listing_id: int, value) -> None:
    s = svc(context)
    ls = s.listings.get(listing_id)
    if not ls or not _can_manage(update, context, ls) or not _editable(update, context, ls):
        return await show(update, context, "That listing can't be edited.", stock_back())
    ls.data[EDIT_FIELDS[field][0]] = value
    s.listings.save_data(listing_id, ls.data)
    context.user_data.pop("edit", None)
    await s.publisher.refresh(ls, FLOWS[ls.category])
    await view_listing(update, context, listing_id)


async def apply_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: dict) -> None:
    text = update.message.text
    if edit["field"] in ("bin", "co"):
        try:
            value = amount(text)
        except ValueError as e:
            return await update.message.reply_text(f"⚠️ {e}")
    else:
        value = text.strip()
    await save_edit(update, context, edit["field"], edit["id"], value)


# ---------- delist / sold ----------
async def delist(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id: int) -> None:
    s = svc(context)
    ls = s.listings.get(listing_id)
    if not ls or not _can_manage(update, context, ls) or ls.status not in ("active", "pending"):
        return await show(update, context, "Listing not found.", stock_back())
    s.listings.set_status(listing_id, "delisted")
    if ls.status == "active":
        await s.publisher.remove(ls)
    await s.notifier.log(f"🗑 Listing #{listing_id} delisted by {update.effective_user.full_name}")
    await show(update, context, f"🗑 Listing #{listing_id} delisted.", stock_back())


async def sold(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id: int) -> None:
    s = svc(context)
    ls = s.listings.get(listing_id)
    owner = None if s.is_admin(update.effective_user) else update.effective_user.id
    if ls and s.listings.transition(listing_id, "active", "sold", owner_id=owner):
        await s.publisher.mark_sold(ls)
        await s.notifier.log(f"✅ Listing #{listing_id} marked sold by {update.effective_user.full_name}")
        return await show(update, context, f"✅ Listing #{listing_id} marked as sold.", stock_back())
    await show(update, context, "Listing not found.", stock_back())


# ---------- buttons ----------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    action, _, arg = q.data.partition(":")
    if action == "sp":
        return await my_listings(update, context, int(arg))
    if action == "mp":
        return await mark_sold_menu(update, context, int(arg))
    if action == "l":
        return await view_listing(update, context, int(arg))
    if action == "e":
        field, _, lid = arg.partition(":")
        return await start_edit(update, context, field, int(lid))
    if action == "ev":  # preset button: Open to offers / No C/O / No notes
        field, _, lid = arg.partition(":")
        preset = {"bin": "Highest Offer", "co": None, "notes": None}[field]
        return await save_edit(update, context, field, int(lid), preset)
    if action == "dl":
        return await show(update, context, f"Delist #{arg}? This removes it from the channel.", InlineKeyboardMarkup([
            [ibtn("Yes, delist", f"dly:{arg}"), ibtn("No", f"l:{arg}")]]))
    if action == "dly":
        return await delist(update, context, int(arg))
    if action == "sold":
        return await sold(update, context, int(arg))

