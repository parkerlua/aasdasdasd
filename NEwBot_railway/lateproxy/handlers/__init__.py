"""Wires every handler into the Application. The order here is the order Telegram updates are matched in."""
from __future__ import annotations

from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          TypeHandler, filters)

from . import admin, approval, errors, importing, start, stock, text, wizard
from .guard import guard

# Button actions, grouped by who handles them.
WIZARD = "cat|ans|grp|pg|tog|clr|skip|back|confirm|cancel"
STOCK = "sp|mp|l|e|ev|dl|dly|sold"


async def _pre_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs first for every button press: tapping anything cancels a pending edit prompt, and the tap is
    acknowledged (the approval and skip buttons answer themselves, since they may need a popup)."""
    q = update.callback_query
    context.user_data.pop("edit", None)
    if q.data.partition(":")[0] not in ("appr", "rej", "skip"):
        await q.answer()


def register(app: Application) -> None:
    app.add_handler(TypeHandler(Update, guard), group=-2)
    app.add_handler(CallbackQueryHandler(_pre_callback), group=-1)

    app.add_handler(CommandHandler("start", start.start))
    for name, fn in (("help", admin.help_cmd), ("admincommands", admin.help_cmd), ("pending", admin.pending),
                     ("info", admin.info), ("search", admin.search), ("stats", admin.stats), ("health", admin.health),
                     ("marksold", admin.marksold), ("removelisting", admin.removelisting),
                     ("updatebin", admin.updatebin), ("updateco", admin.updateco),
                     ("ban", admin.ban), ("unban", admin.unban)):
        app.add_handler(CommandHandler(name, fn))

    app.add_handler(MessageHandler(filters.FORWARDED & importing.AdminOnly(app), importing.on_forward))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, wizard.on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text.on_text))

    app.add_handler(CallbackQueryHandler(start.on_menu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(wizard.on_callback, pattern=rf"^({WIZARD})(:|$)"))
    app.add_handler(CallbackQueryHandler(stock.on_callback, pattern=rf"^({STOCK})(:|$)"))
    app.add_handler(CallbackQueryHandler(approval.on_callback, pattern=r"^(appr|rej):"))
    app.add_handler(CallbackQueryHandler(importing.on_callback, pattern=r"^imp:"))

    app.add_error_handler(errors.on_error)
