"""Entry point:  python main.py"""
import asyncio
import logging

from dotenv import load_dotenv
from telegram import Update

from lateproxy.app import build_application
from lateproxy.config import ConfigError, load_settings


def main() -> None:
    load_dotenv()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines contain the bot token
    logging.getLogger("telethon").setLevel(logging.WARNING)
    try:
        settings = load_settings()
    except ConfigError as e:
        raise SystemExit(f"Config error: {e}") from None
    asyncio.set_event_loop(asyncio.new_event_loop())  # Python 3.14+ no longer creates one for us
    # bootstrap_retries=-1: if Telegram can't be reached at startup, keep retrying instead of crashing
    build_application(settings).run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    main()
