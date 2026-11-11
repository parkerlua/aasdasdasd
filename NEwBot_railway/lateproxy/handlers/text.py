"""One place that decides who gets a plain text message: an edit prompt, an import prompt, or the wizard."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..context import svc
from . import importing, stock, wizard


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if edit := context.user_data.get("edit"):
        return await stock.apply_edit_text(update, context, edit)
    imp = context.user_data.get("import")
    if imp and imp["step"] == "owner" and svc(context).is_admin(update.effective_user):
        return await importing.on_owner_text(update, context)
    await wizard.on_text(update, context)
