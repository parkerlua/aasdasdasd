"""Check the Premium userbot BEFORE going live. It does not touch your channel.

    python scripts/userbot_check.py

It logs in with USERBOT_SESSION, tells you who it is and whether it has Premium, checks it can see CHANNEL_ID,
and sends one test message to that account's own Saved Messages. Open Saved Messages in Telegram: if the stars show as
your custom emojis (not plain ⭐), posting from the channel will work the same way.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from lateproxy.config import load_settings  # noqa: E402
from lateproxy.paths import ROOT  # noqa: E402
from lateproxy.services.emoji import STAR, emoji_html  # noqa: E402
from lateproxy.services.userbot import Userbot  # noqa: E402


async def main() -> None:
    load_dotenv(ROOT / ".env")
    s = load_settings()
    if not s.userbot_enabled:
        print("Not set up yet. Put USERBOT_API_ID, USERBOT_API_HASH and USERBOT_SESSION in .env "
              "(see docs/SETUP.md, or run scripts/userbot_login.py).")
        return
    ub = Userbot(s)
    await ub.start()
    if not ub.ready:
        print("Login failed. The session string may be wrong or expired: run scripts/userbot_login.py again.")
        return
    try:
        me = await ub._client.get_me()
        print(f"Logged in as @{me.username} ({me.first_name}). Premium: {getattr(me, 'premium', False)}")
        if s.channel is None:
            print("CHANNEL_ID is not set, so channel access wasn't checked.")
        else:
            try:
                if s.posts_to_saved:
                    print("CHANNEL_ID=me: listings will be posted to this account's Saved Messages. No channel needed.")
                else:
                    chat = await ub._client.get_entity(s.channel)
                    print(f"Channel OK: {getattr(chat, 'title', s.channel)}")
                    perms = await ub._client.get_permissions(chat, me)
                    print(f"  can post: {getattr(perms, 'post_messages', None)} | can edit: {getattr(perms, 'edit_messages', None)} "
                          f"| can delete: {getattr(perms, 'delete_messages', None)}")
            except Exception as e:  # noqa: BLE001
                print(f"Can't see the channel ({type(e).__name__}). Add this account to it as an admin.")
        html = (f"{emoji_html('post_discord', STAR)} <b>Userbot test</b>\n"
                f"{emoji_html('contact_line', STAR)} @{s.contact_username}\n"
                f"{emoji_html('submit_line', STAR)} Submit Via: @{s.submit_username}")
        message_id = await ub.send("me", html)
        print(f"Sent test message {message_id} to Saved Messages. Open it: the stars should be custom emojis.")
    finally:
        await ub.stop()


if __name__ == "__main__":
    asyncio.run(main())
