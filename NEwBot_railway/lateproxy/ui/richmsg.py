"""Rich messages: the text with the buttons *inside* the message body (Bot API 10.1+).

python-telegram-bot has no wrapper for these yet, so the API is called directly. Screens are still written as
(HTML text, InlineKeyboardMarkup); this module turns that into one rich-message HTML document.
"""
from __future__ import annotations

import html
import re
import warnings
from types import SimpleNamespace

from ..services.emoji import ALT_BY_ID, STAR

warnings.filterwarnings("ignore", message=".*do_api_request.*")  # ptb nags about calling the API by hand


def text_html(text: str) -> str:
    """Telegram HTML -> rich HTML: a paragraph per blank line, <br> per line break."""
    text = text.replace("&#x27;", "&apos;").replace("&#39;", "&apos;")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paragraphs)


def buttons_html(markup) -> str:
    """InlineKeyboardMarkup -> one centered button row per keyboard row."""
    rows = []
    for row in markup.inline_keyboard:
        buttons = []
        for b in row:
            label = html.escape(b.text, quote=False)
            if b.icon_custom_emoji_id:
                alt = ALT_BY_ID.get(b.icon_custom_emoji_id, STAR)
                label = f'<tg-emoji emoji-id="{b.icon_custom_emoji_id}">{alt}</tg-emoji> {label}'
            style = f' style="{b.style}"' if b.style else ""
            if b.url:
                buttons.append(f'<tg-button type="url" url="{html.escape(b.url)}"{style}>{label}</tg-button>')
            else:
                buttons.append(f'<tg-button type="callback_data" data="{html.escape(b.callback_data)}"{style}>{label}</tg-button>')
        rows.append('<tg-button-row align="center">' + "".join(buttons) + "</tg-button-row>")
    return "".join(rows)


def document(text: str, markup=None) -> dict:
    return {"html": text_html(text) + (buttons_html(markup) if markup else "")}


async def send(bot, chat_id, text: str, markup=None):
    result = await bot.do_api_request("sendRichMessage", api_kwargs={"chat_id": chat_id, "rich_message": document(text, markup)})
    return SimpleNamespace(message_id=result["message_id"], chat_id=chat_id)


async def edit(bot, chat_id, message_id: int, text: str, markup=None):
    """Works on rich messages and on old plain ones (Telegram turns them into rich)."""
    await bot.do_api_request("editMessageText", api_kwargs={
        "chat_id": chat_id, "message_id": message_id, "rich_message": document(text, markup)})
