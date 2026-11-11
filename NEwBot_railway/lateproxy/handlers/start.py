"""/start and the main menu."""
from __future__ import annotations

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from ..ui.screens import home
from . import stock, wizard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # clear the old bottom keyboard if one is still showing from a previous version
    m = await update.message.reply_text("·", reply_markup=ReplyKeyboardRemove())
    await m.delete()
    if context.args and context.args[0] == "list":  # deep link: t.me/<bot>?start=list
        return await wizard.start_listing(update, context)
    await home(update, context)


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.callback_query.data.partition(":")[2]
    handler = {"home": home, "new": wizard.start_listing, "stock": stock.my_listings, "sold": stock.mark_sold_menu}[target]
    await handler(update, context)
