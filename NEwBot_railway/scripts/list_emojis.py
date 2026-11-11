"""Print every custom emoji ID in an emoji pack, with a ready-to-paste tag.

    python scripts/list_emojis.py            # the LateEmojis pack
    python scripts/list_emojis.py OtherPack

Put the IDs you want into assets/icons.json.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from telegram import Bot  # noqa: E402

from lateproxy.config import load_settings  # noqa: E402
from lateproxy.paths import ROOT  # noqa: E402


async def main() -> None:
    load_dotenv(ROOT / ".env")
    name = sys.argv[1] if len(sys.argv) > 1 else "LateEmojis"
    async with Bot(load_settings().bot_token) as bot:
        pack = await bot.get_sticker_set(name)
        for i, s in enumerate(pack.stickers, 1):
            print(f'{i:>3}. {s.custom_emoji_id}  <tg-emoji emoji-id="{s.custom_emoji_id}">{s.emoji}</tg-emoji>')


if __name__ == "__main__":
    asyncio.run(main())
