"""A daily copy of the database, zipped and sent to a private chat (BACKUP_CHAT_ID)."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import tempfile
import zipfile
from pathlib import Path

from telegram import Bot

from ..config import Settings
from ..db import Database

log = logging.getLogger(__name__)


def make_backup_zip(db: Database, folder: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M")
    raw = folder / "listings.db"
    db.backup_to(raw)
    archive = folder / f"listings-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(raw, "listings.db")
    raw.unlink()
    return archive


async def backup_once(bot: Bot, db: Database, settings: Settings) -> bool:
    if settings.backup_chat is None:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = make_backup_zip(db, Path(tmp))
            with archive.open("rb") as f:
                await bot.send_document(settings.backup_chat, f, caption="🗄 Daily database backup")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("backup failed: %s", e)
        return False


def seconds_until(hour_utc: int, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


async def backup_loop(bot: Bot, db: Database, settings: Settings) -> None:
    while True:
        await asyncio.sleep(seconds_until(settings.backup_hour_utc))
        await backup_once(bot, db, settings)
