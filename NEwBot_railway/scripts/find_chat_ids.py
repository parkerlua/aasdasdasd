"""Print the ID of every group / channel the bot hears about. Add the bot to a chat as admin (or post in it) and
the ID appears. Use it to fill CHANNEL_ID / APPROVAL_CHAT_ID / LOGS_CHAT_ID.

    python scripts/find_chat_ids.py

Stop the real bot first: only one program can read a bot's updates at a time.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.ext import Application, ContextTypes, TypeHandler  # noqa: E402

from lateproxy.config import load_settings  # noqa: E402
from lateproxy.paths import ROOT  # noqa: E402

seen: set[int] = set()


async def on_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or chat.type == "private" or chat.id in seen:
        return
    seen.add(chat.id)
    print(f"{chat.type:<11} id={chat.id:<16} {chat.title or chat.username or '?'}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(load_settings().bot_token).build()
    app.add_handler(TypeHandler(Update, on_update))
    print("Listening... add the bot to your chats as admin, or post in them. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
