"""Floral Telegram bot. Run with Python 3.10+; no packages required.

Copy .env.example to .env beside this script. Set TELEGRAM_BOT_TOKEN
to your BotFather token and FLORAL_OWNER_ID to
@Floral's numeric Telegram user ID. Keep the SQLite database across restarts.
Optional FLORAL_DB_PATH overrides the default database beside this script.
"""

import os
from pathlib import Path
import time
from urllib.error import URLError

from features.offers.menu import setup as setup_offers
from features.stock.menu import setup as setup_stock
from features.string.handlers import COMMANDS, handle_update
from features.string.store import open_database
from features.vanity.flow import setup as setup_vanity
from telegram_api import TelegramError, telegram

DESCRIPTION = (
    "@Evaluate — Submit your accounts for listing.\n\n"
    "• Listing fee: 8%\n"
    "• Minimum fee: $15\n\n"
    "An admin must approve each listing before it goes live."
)


def load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or key not in ("TELEGRAM_BOT_TOKEN", "FLORAL_OWNER_ID", "FLORAL_DB_PATH", "TELEGRAM_API_ID",
                                         "TELEGRAM_API_HASH", "FLORAL_PUBLISH_CHANNEL", "FLORAL_PUBLISH_SESSION",
                                         "DISCORD_BOT_TOKEN", "FLORAL_STAFF_IDS"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main():
    project_dir = Path(__file__).resolve().parent
    load_env(project_dir / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    owner_id = os.environ.get("FLORAL_OWNER_ID", "")
    if not token or not owner_id.isascii() or not owner_id.isdigit() or int(owner_id) < 1:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and FLORAL_OWNER_ID in .env or in your environment.")

    def api(method, **params):
        return telegram(token, method, **params)

    os.umask(0o077)
    default_db = project_dir / "floral.sqlite3"
    db = open_database(os.environ.get("FLORAL_DB_PATH") or default_db)
    setup_vanity(db)
    setup_stock(db)
    setup_offers(db)
    bot_username = api("getMe")["username"].lower()
    api("setMyDescription", description=DESCRIPTION)
    api("setMyCommands", commands=COMMANDS)
    listing_emojis = ()
    try:
        stickers = api("getStickerSet", name="EvaluateEmojis")["stickers"]
        if len(stickers) >= 2:
            listing_emojis = (stickers[-1], stickers[-2])
    except (TelegramError, URLError, TimeoutError):
        print("Could not load EvaluateEmojis. Listing buttons will use text labels.", flush=True)
    print(f"Running @{bot_username}", flush=True)
    offset = 0
    while True:
        try:
            updates = api(
                "getUpdates", offset=offset, timeout=25,
                allowed_updates=["message", "callback_query"],
            )
        except (TelegramError, URLError, TimeoutError) as error:
            if isinstance(error, TelegramError) and error.code in (401, 404, 409):
                raise SystemExit(str(error)) from None
            print("Polling interrupted. Retrying in five seconds.", flush=True)
            time.sleep(5)
            continue
        for update in updates:
            try:
                handle_update(update, db, int(owner_id), bot_username, api, listing_emojis)
            except (TelegramError, URLError, TimeoutError) as error:
                print(f"Update {update['update_id']} could not be completed ({type(error).__name__}).", flush=True)
            offset = update["update_id"] + 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (TelegramError, URLError, TimeoutError) as error:
        raise SystemExit(f"Startup failed ({type(error).__name__}). Check the bot token and connection.") from None
