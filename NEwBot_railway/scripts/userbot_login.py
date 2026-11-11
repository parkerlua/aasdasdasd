"""Log the Premium userbot account in ONCE and print its session string.

    python scripts/userbot_login.py

1. Get an api_id and api_hash for the userbot account at https://my.telegram.org  ->  API development tools.
2. Run this script, enter the account's phone number, then the login code Telegram sends it
   (and its 2-step-verification password if it has one).
3. Copy the long string it prints into the USERBOT_SESSION variable (.env locally, Railway variables online).
   Also set USERBOT_API_ID and USERBOT_API_HASH.

The string is a login for that account. Never share it or commit it.
"""
import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ.get("USERBOT_API_ID") or input("api_id: ").strip())
    api_hash = os.environ.get("USERBOT_API_HASH") or input("api_hash: ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:  # asks for phone + code in the terminal
        me = await client.get_me()
        print(f"\nLogged in as @{me.username} (Premium: {getattr(me, 'premium', False)})")
        if not getattr(me, "premium", False):
            print("Note: this account has no Telegram Premium, so custom emojis won't show in posts.")
        print("\nUSERBOT_SESSION=" + client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
