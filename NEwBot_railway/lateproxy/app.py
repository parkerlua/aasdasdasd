"""Builds the Telegram Application and wires every service into it."""
from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand
from telegram.ext import Application

from .config import Settings
from .context import Services
from .db import KV, Database, ListingRepo, UserRepo
from .handlers import register
from .services.backup import backup_loop
from .services.discord import DiscordLookup
from .services.notifier import Notifier
from .services.publisher import Publisher
from .services.userbot import Userbot

log = logging.getLogger(__name__)


def build_services(app: Application, settings: Settings, db: Database | None = None) -> Services:
    db = db or Database(settings.db_path)
    userbot = Userbot(settings)
    return Services(
        settings=settings, db=db, listings=ListingRepo(db), users=UserRepo(db), kv=KV(db), userbot=userbot,
        publisher=Publisher(app.bot, settings, userbot), notifier=Notifier(app.bot, settings),
        discord=DiscordLookup(settings.discord_token))


async def _post_init(app: Application) -> None:
    s: Services = app.bot_data["svc"]
    await app.bot.set_my_commands([BotCommand("start", "Open the menu")])
    if s.settings.selection_only:
        log.info("SELECTION_ONLY is on: the bot stops after the category choice. No wizard, review, posting or userbot.")
        return
    await s.userbot.start()
    if s.settings.backup_chat is not None:
        app.bot_data["backup_task"] = asyncio.create_task(backup_loop(app.bot, s.db, s.settings))
    if s.settings.channel is not None and s.userbot.ready:
        mode = "saved messages (userbot)" if s.settings.posts_to_saved else "userbot"
    elif s.settings.channel is not None and not s.settings.posts_to_saved:
        mode = "bot"
    else:
        mode = "dm"
    log.info("LateProxyBot is up. Posting mode: %s | approvals: %s | discord lookup: %s",
             mode, "approval chat" if s.settings.approval_chat else "admin DM",
             "on" if s.discord.enabled else "off")


async def _post_shutdown(app: Application) -> None:
    s: Services = app.bot_data["svc"]
    task = app.bot_data.get("backup_task")
    if task:
        task.cancel()
    await s.userbot.stop()
    await s.discord.aclose()
    s.db.close()


def build_application(settings: Settings, db: Database | None = None, bot=None) -> Application:
    """`db` and `bot` can be swapped for fakes in tests."""
    builder = Application.builder().post_init(_post_init).post_shutdown(_post_shutdown)
    if bot is not None:
        builder = builder.bot(bot)
    else:  # patient timeouts: a slow connection to Telegram shouldn't kill the bot (the default is only 5 seconds)
        builder = (builder.token(settings.bot_token).connect_timeout(20).read_timeout(30).write_timeout(30)
                   .pool_timeout(20).get_updates_connect_timeout(20).get_updates_read_timeout(40))
    app = builder.build()
    app.bot_data["svc"] = build_services(app, settings, db)
    register(app)
    return app
