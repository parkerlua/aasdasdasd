"""The listing wizard: walks a seller through a flow's steps and creates the pending listing."""
from __future__ import annotations

import html
import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..context import Services, svc
from ..listing import FLOWS, MENU_FLOWS, next_index, summary, visible
from ..listing.flows import BADGE_GROUP_ICONS, PERSIST_EXTRA, amount
from ..listing.post import all_badges
from ..paths import ASSETS
from ..services import discord as discord_api
from ..services.emoji import emoji_html
from ..services.profile_card import ONLINE_MODES, CardData
from ..services.profile_card import render as render_card
from ..ui.buttons import SELECTED, ibtn
from ..ui.screens import home, show

log = logging.getLogger(__name__)

PAGE_SIZE = 10  # badges per page: 5 rows of 2, so every tab fits on one page
COLUMNS = 2     # badges per row
SHORTEN = ("Nitro ", "Boost — ", "Gift — ")  # the tab already says Nitro / Boost / Gift, so the buttons can be shorter


def badge_label(name: str) -> str:
    """'Nitro Gold — 6 Months' -> 'Gold — 6 Months', 'Boost — 12 Months' -> '12 Months' (plain 'Nitro' stays)."""
    for prefix in SHORTEN:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


# ---------- state ----------
def current(context: ContextTypes.DEFAULT_TYPE):
    st = context.user_data.get("flow")
    return (st, FLOWS[st["cat"]].steps[st["idx"]]) if st else (None, None)


async def start_listing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("flow", None)
    rows = [[ibtn(f.name, f"cat:{f.key}", f.icon, "primary")] for f in MENU_FLOWS]
    rows.append([ibtn("Cancel", "menu:home", "cancel")])
    await show(update, context, "What are you selling?", InlineKeyboardMarkup(rows))


# ---------- rendering ----------
def card_png(flow, data: dict, s: Services) -> bytes:
    """The public profile card for a Discord listing."""
    return render_card(CardData(
        created=data.get("created") or "", online=ONLINE_MODES.get(data.get("online"), "offline"),
        display=data.get("display") or "", username=data.get("username") or "",
        show_username=flow.key == "discord_username", badges=all_badges(data), tag=s.settings.card_tag_text,
        avatar=data.get("_avatar"), blur_avatar=s.settings.card_blur_avatar))


def keyboard(flow, step, st) -> InlineKeyboardMarkup:
    rows = []
    if step.kind == "confirm":
        rows.append([ibtn("Send for review", "confirm", "confirm", "success")])
    if step.kind == "choice":
        btns = [ibtn(text, f"ans:{i}", icon, style) for i, (text, _, icon, style) in enumerate(step.options)]
        per_row = step.per_row or (2 if len(btns) <= 4 else 3)
        rows += [btns[i:i + per_row] for i in range(0, len(btns), per_row)]
    selected = (st["data"].get(step.key) or []) if step.kind == "multi" else []
    if step.kind == "multi":
        def picked_in(group: str) -> int:
            return sum(1 for text, _ in step.groups[group] if text in selected)

        tabs = [] if len(step.groups) < 2 else [
            ibtn(("✓ " if g == st["group"] else "") + g + (f" ({picked_in(g)})" if picked_in(g) else ""),
                 f"grp:{g}", BADGE_GROUP_ICONS[g], SELECTED if g == st["group"] else None) for g in step.groups]
        rows += [row for row in (tabs[:3], tabs[3:]) if row]
        items = step.groups[st["group"]]
        pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
        page = min(st.get("page", 0), pages - 1)
        rows.append([ibtn(f"─────  {st['group']}  ─────", "noop")])  # divider between the tabs and the badges
        grid = []
        for i in range(page * PAGE_SIZE, min(len(items), (page + 1) * PAGE_SIZE)):
            text, icon = items[i]
            grid.append(ibtn(("✓ " if text in selected else "") + badge_label(text), f"tog:{i}", icon,
                             SELECTED if text in selected else None))
        rows += [grid[i:i + COLUMNS] for i in range(0, len(grid), COLUMNS)]
        if pages > 1:
            rows.append([ibtn("◀", f"pg:{(page - 1) % pages}"), ibtn(f"{page + 1}/{pages}", "noop"),
                         ibtn("▶", f"pg:{(page + 1) % pages}")])
        rows.append([ibtn("──────────────", "noop")])  # divider above the actions
        if selected:
            rows.append([ibtn(f"Done ({len(selected)})", "skip", None, SELECTED), ibtn("Clear", "clr")])
    elif step.skip:
        text, _, icon, style = step.skip
        rows.append([ibtn(text, "skip", icon, style)])
    nav = []
    if st["history"] and not step.sub:
        nav.append(ibtn("Back", "back", "back"))
    nav.append(ibtn("Cancel", "cancel", "cancel"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)


def step_text(flow, step, st) -> str:
    text = step.prompt.format_map(st["data"])
    if step.kind == "multi" and st["data"].get(step.key):  # show what's picked, since the buttons only show one tab
        picked = ", ".join(html.escape(p) for p in st["data"][step.key])
        text = f"{text}\n\n<b>Picked ({len(st['data'][step.key])}):</b> {picked}"
    if step.kind == "confirm":
        return f"{summary(flow, st['data'])}\n\n{text}"
    if st["idx"] == 0:
        return f"{emoji_html(flow.icon, flow.emoji)} <b>{flow.name}</b>\n{text}"
    return text


async def render(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = svc(context)
    st = context.user_data["flow"]
    flow = FLOWS[st["cat"]]
    step = flow.steps[st["idx"]]
    if step.kind == "multi":
        st.setdefault("group", next(iter(step.groups)))
    text, markup = step_text(flow, step, st), keyboard(flow, step, st)
    chat = update.effective_chat

    if flow.card and step.kind == "confirm":  # show the generated profile card with the summary under it
        if update.callback_query:
            await update.callback_query.message.delete()
        png = card_png(flow, st["data"], s)
        if len(text) <= 1000:
            msg = await chat.send_photo(png, caption=text, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            msg = await chat.send_photo(png)
            await chat.send_message(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        st["data"]["account_image"] = msg.photo[-1].file_id  # the public post uses this card
        return

    if step.example:  # a photo with a caption stays a classic message
        if update.callback_query:
            await update.callback_query.message.delete()
        with open(ASSETS / step.example, "rb") as f:
            await chat.send_photo(f, caption=text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await show(update, context, text, markup)


# ---------- hooks: things that happen right after a step is answered ----------
async def discord_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, st: dict, user_id: str) -> None:
    """Fill what we can from the Discord ID: creation date (always), and username / display / avatar / badges
    when a Discord token is configured. Whatever isn't found is simply asked later."""
    s, data, flow = svc(context), st["data"], FLOWS[st["cat"]]
    for key in ("_display_known", "_username_known", "_avatar", "verified_badges", "created"):
        data.pop(key, None)  # they may have gone Back and typed a different ID
    created = discord_api.snowflake_to_datetime(user_id)
    if created.year >= 2015:
        data["created"] = discord_api.format_created(created)
    profile = await s.discord.fetch(user_id)
    if not profile:
        return
    # Badge listings hide the name (like the example card); username listings show it.
    data["display"] = "" if flow.key == "discord_badge" else (profile.display_name or profile.username)
    data["_display_known"] = True
    if flow.key == "discord_username":
        data["username"], data["_username_known"] = profile.username, True
    if profile.badges:
        data["verified_badges"] = profile.badges
    avatar = await s.discord.download(profile.avatar_url)
    if avatar:
        data["_avatar"] = avatar


HOOKS = {"discord_lookup": discord_lookup}


async def advance(update: Update, context: ContextTypes.DEFAULT_TYPE, value) -> None:
    st = context.user_data["flow"]
    flow = FLOWS[st["cat"]]
    step = flow.steps[st["idx"]]
    st["data"][step.key] = value
    st["history"].append(st["idx"])
    if step.hook:
        await HOOKS[step.hook](update, context, st, value)
    st["idx"] = next_index(flow, st["idx"], st["data"])
    await render(update, context)


# ---------- messages ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st, step = current(context)
    if not st:
        from ..ui.screens import home_markup
        return await show(update, context, "Tap a button to get started.", home_markup())
    if step.kind in ("choice", "multi", "confirm"):
        return await update.message.reply_text("Please use the buttons above.")
    if step.kind == "photo":
        return await update.message.reply_text("Please send a screenshot (photo).")
    validate = step.validate or (amount if step.kind == "amount" else lambda t: t.strip())
    try:
        value = validate(update.message.text)
    except ValueError as e:
        return await update.message.reply_text(f"⚠️ {e}")
    await advance(update, context, value)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st, step = current(context)
    if not st or step.kind != "photo":
        return
    msg = update.message
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    await advance(update, context, file_id)


# ---------- buttons ----------
def collect_data(flow, st: dict) -> dict:
    """What gets saved with a listing: the answers to the questions that were asked, plus a card's extras."""
    data = {k.key: st["data"].get(k.key) for k in visible(flow, st["data"]) if k.kind != "confirm"}
    if flow.card:
        for key in PERSIST_EXTRA:
            if st["data"].get(key) is not None:
                data[key] = st["data"][key]  # includes display == "" (hidden)
    return data


async def finish_test_run(update: Update, context: ContextTypes.DEFAULT_TYPE, st: dict) -> None:
    """Test mode: nothing is saved, reviewed or posted. The finished post is sent to Saved Messages (if CHANNEL_ID=me and
    the userbot is connected) or DM'd to the admin, so it can be checked."""
    s, flow, u = svc(context), FLOWS[st["cat"]], update.effective_user
    context.user_data.pop("flow", None)
    chat_id, where = s.admin_chat_id(), None
    if chat_id or (s.settings.posts_to_saved and s.userbot.ready):
        try:
            where = await s.publisher.send_preview(chat_id, flow, collect_data(flow, st),
                                                   f"🧪 Test post from {u.full_name}: {flow.name}\nNothing was saved or posted.")
        except Exception:  # noqa: BLE001
            log.exception("couldn't send the test post")
    admin = f"@{s.settings.admin_username}"
    if where == "saved":
        result = "The finished post was sent to your Saved Messages."
    elif where == "dm":
        result = f"The finished post was sent to {admin}."
    else:
        result = f"I couldn't send it to {admin}. They need to open this bot and send /start first."
    await show(update, context, f"✅ That's the whole flow.\n\n{result}\n<i>Test mode: nothing was submitted, "
                                "sent for review or posted.</i>",
               InlineKeyboardMarkup([[ibtn("Back to menu", "menu:home", "back")]]))


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE, st: dict) -> None:
    from .approval import notify_approvers  # approval never imports the wizard, so no cycle at import time

    s, flow, u = svc(context), FLOWS[st["cat"]], update.effective_user
    data = collect_data(flow, st)
    title = data.get(flow.title_key) or flow.name
    title = ", ".join(title) if isinstance(title, list) else str(title)
    data["_seller"] = {"id": u.id, "username": u.username, "name": u.full_name}
    listing = s.listings.create(u.id, flow.key, title, data, status="pending")
    context.user_data.pop("flow", None)
    await show(update, context, f"{summary(flow, st['data'])}\n\n⏳ Listing #{listing.id} submitted. "
                                "You'll be notified once it's reviewed.")
    await notify_approvers(context, listing.id)
    await s.notifier.log(f"🆕 Listing #{listing.id} ({flow.name}) submitted by {u.full_name} (<code>{u.id}</code>)")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    action, _, arg = q.data.partition(":")
    if action == "cancel":
        return await home(update, context, "Listing cancelled. What next?")
    if action == "cat":
        cfg = svc(context).settings
        if cfg.selection_only and arg not in cfg.test_flows:
            flow = FLOWS[arg]
            text = (f"{emoji_html(flow.icon, flow.emoji)} <b>{flow.name}</b> selected ✅\n\n"
                    "<i>Test mode: everything after picking a category is switched off.</i>")
            return await show(update, context, text, InlineKeyboardMarkup([[ibtn("Back", "menu:new", "back")]]))
        context.user_data["flow"] = {"cat": arg, "idx": 0, "data": {}, "history": []}
        return await render(update, context)

    st, step = current(context)
    if action == "skip" and not st:
        await q.answer()
    if not st:
        return await home(update, context, "That session timed out. Start again:")

    if action == "ans" and step.kind == "choice":
        return await advance(update, context, step.options[int(arg)][1])
    if action == "grp" and step.kind == "multi" and arg in step.groups:
        st["group"], st["page"] = arg, 0
        return await render(update, context)
    if action == "pg" and step.kind == "multi":
        st["page"] = int(arg)
        return await render(update, context)
    if action == "clr" and step.kind == "multi":
        st["data"][step.key] = []
        return await render(update, context)
    if action == "tog" and step.kind == "multi":
        text = step.groups[st["group"]][int(arg)][0]
        picked = list(st["data"].get(step.key) or [])
        picked.remove(text) if text in picked else picked.append(text)
        st["data"][step.key] = picked
        return await render(update, context)
    if action == "skip" and (step.skip or step.kind == "multi"):
        if step.kind == "multi" and not st["data"].get(step.key):
            return await q.answer("Pick at least one badge.", show_alert=True)
        await q.answer()
        if step.kind == "multi":
            return await advance(update, context, st["data"][step.key])
        return await advance(update, context, step.skip[1])
    if action == "back" and st["history"]:
        st["idx"] = st["history"].pop()
        return await render(update, context)
    if action == "confirm" and step.kind == "confirm":
        if svc(context).settings.selection_only:
            return await finish_test_run(update, context, st)
        return await submit(update, context, st)
