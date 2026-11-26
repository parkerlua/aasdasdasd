import asyncio
import html
import os
from urllib.error import URLError

from telegram_api import TelegramError


def queued(db):
    return db.execute(
        "SELECT id, vanity, bin FROM vanity_reviews WHERE category = 'discord_vanity' AND status = 'approved' AND published_at IS NULL AND draft_sent_at IS NULL ORDER BY id"
    ).fetchall()


def ready_notice(api, owner_id, first_id):
    api(
        "sendMessage", chat_id=owner_id,
        text="Your vanity batch is ready. Any listings approved before you request the draft will be included.",
        reply_markup={"inline_keyboard": [[{
            "text": "Send batch draft", "style": "success", "callback_data": f"vanity_publish:{first_id}",
        }]]},
    )


def format_post(rows, stickers, types):
    parts = []
    entities = []
    offset = 0

    def add(text, entity=None, **fields):
        nonlocal offset
        length = len(text.encode("utf-16-le")) // 2
        if entity:
            entities.append(entity(offset=offset, length=length, **fields))
        parts.append(text)
        offset += length

    def emoji(index):
        sticker = stickers[index]
        add(sticker.get("emoji") or "🔹", types.MessageEntityCustomEmoji,
            document_id=int(sticker["custom_emoji_id"]))
        add(" ")

    emoji(-10)
    add("NEW DISCORD VANITIES", types.MessageEntityBold)
    add("\n\n")
    lines = "\n".join(f"{vanity} — BIN: {price.removeprefix('$')}" for _, vanity, price in rows)
    add(lines, types.MessageEntityBlockquote)
    add("\n\n")
    emoji(2)
    add("Contact ")
    add("@floral", types.MessageEntityMention)
    add("\n")
    emoji(1)
    add("List Via: ")
    add("@LateProxyApp", types.MessageEntityMention)
    return "".join(parts), entities


async def account_client(sign_in=False, post=None, channel_message=None):
    from telethon import TelegramClient

    client = TelegramClient(
        os.environ.get("FLORAL_PUBLISH_SESSION", "floral-publisher"),
        int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"],
    )
    try:
        if sign_in:
            await client.start()
            return
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("Publisher session needs sign-in")
        if channel_message:
            chat_id, message_id = channel_message
            if post is None:
                await client.delete_messages(chat_id, [message_id])
            else:
                from telethon.errors import MessageNotModifiedError

                text, entities = post
                try:
                    await client.edit_message(
                        chat_id, message_id, text, formatting_entities=entities, link_preview=False,
                    )
                except MessageNotModifiedError:
                    pass
            return

        text, entities = post
        channel = os.environ["FLORAL_PUBLISH_CHANNEL"]
        destination = int(channel) if channel.removeprefix("-").isdigit() else channel
        sent = await client.send_message(destination, text, formatting_entities=entities, link_preview=False)
        return sent.chat_id, sent.id
    finally:
        await client.disconnect()


def send_channel_post(rows, stickers):
    from telethon import types

    return asyncio.run(account_client(post=format_post(rows, stickers, types)))


def emoji_markup(stickers, position, fallback):
    try:
        emoji_id = stickers[position - 1 if position > 0 else position]["custom_emoji_id"]
        if not isinstance(emoji_id, str) or not emoji_id.isascii() or not emoji_id.isdigit():
            return fallback
    except (IndexError, KeyError):
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def send_draft(api, owner_id, build, photo=None):
    try:
        stickers = api("getStickerSet", name="EvaluateEmojis")["stickers"]
    except (TelegramError, URLError, TimeoutError):
        stickers = []
    text = build(stickers)
    if photo and len(text) <= 1024:
        method, payload = "sendPhoto", {"photo": photo, "caption": text}
    else:
        method, payload = "sendMessage", {"text": text, "link_preview_options": {"is_disabled": True}}
    try:
        api(method, chat_id=owner_id, parse_mode="HTML", **payload)
    except TelegramError as error:
        if error.code != 400 or "<tg-emoji" not in text:
            raise
        payload["caption" if method == "sendPhoto" else "text"] = build([])
        api(method, chat_id=owner_id, parse_mode="HTML", **payload)
    if photo and method == "sendMessage":
        api("sendPhoto", chat_id=owner_id, photo=photo)


def clean_price(price):
    return {"Taking Offers": "Highest Offer"}.get(price, price.removeprefix("$"))


def compact_badges(text):
    from .details import BADGES, NITRO_DISPLAY

    names = {name: f"Nitro {tier}" for name, (tier, _) in zip(BADGES["Nitro"], NITRO_DISPLAY) if name != "Nitro"}
    names.update({badge: f"{badge.split()[2]}M Boost" for badge in BADGES["Boosts"]})
    return ", ".join(names.get(badge, badge) for badge in text.split(", "))


def listing_draft(category, item, price, offer, notes, stickers):
    titles = {
        "discord_badges": ("DISCORD BADGE", 52, "🔵"),
        "discord_username": ("DISCORD USERNAME", None, "🔵"),
        "telegram_username": ("TELEGRAM USERNAME", -3, "✈️"),
        "telegram_gift": ("TELEGRAM GIFT", -3, "🎁"),
        "tiktok_username": ("TIKTOK USERNAME", None, "🎵"),
    }
    title, position, fallback = titles[category]
    icon = emoji_markup(stickers, position, fallback) if position else fallback
    lines = item.splitlines()
    fields = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
    parts = [f"{icon} <b>NEW {title}</b>"]
    if category != "discord_badges":
        first = lines[0]
        if category in ("discord_username", "telegram_username", "tiktok_username"):
            names = first.split(", ") if category == "telegram_username" else [first]
            first = ", ".join(f'<a href="https://t.me/floral">{html.escape("@" + name.lstrip("@"))}</a>' for name in names)
        else:
            first = html.escape(first)
        parts[0] += f"\n{first}"
    bullets = []
    if category == "discord_badges" and fields.get("Badges"):
        bullets.append(compact_badges(fields["Badges"]))
    if fields.get("Original email") == "Yes":
        provider = fields.get("Email domain") or fields.get("Email provider")
        bullets.append(f"OGE ({provider})" if provider else "OGE")
    if fields.get("Pullback test"):
        bullets.append("Pullback Test Accepted" if fields["Pullback test"] == "Yes" else "Pullback Test Not Accepted")
    if fields.get("Account standing"):
        bullets.append(f"Standing {fields['Account standing']}")
    if category == "discord_username" and fields.get("Badges"):
        bullets.append(compact_badges(fields["Badges"]))
    note_lines = [line.strip() for line in notes.splitlines() if line.strip()]
    if category.startswith("discord_"):
        bullets.extend(note_lines)
    if bullets:
        parts.append("\n".join(f"- {html.escape(line)}" for line in bullets))
    pricing = f"BIN: {html.escape(clean_price(price))}\nC/O: {html.escape(clean_price(offer))}"
    if not category.startswith("discord_") and note_lines:
        pricing += "\n" + "\n".join(f"- {html.escape(line)}" for line in note_lines)
    parts.append(pricing)
    footer = emoji_markup(stickers, 3, "✈️")
    parts.append(f"{footer} Contact @floral")
    return "\n\n".join(parts)


def publish(db, api, owner_id, message_id, action):
    with db:
        db.execute("BEGIN IMMEDIATE")
        rows = queued(db)
        if len(rows) < 2 or action != f"vanity_publish:{rows[0][0]}":
            return

        def batch(stickers):
            icon = emoji_markup(stickers, -10, "🔵")
            lines = "\n".join(f"{html.escape(vanity)} — BIN: {html.escape(clean_price(price))}"
                              for _, vanity, price in rows)
            contact = emoji_markup(stickers, 3, "✈️")
            list_icon = emoji_markup(stickers, 2, "🤖")
            return (f"{icon} <b>NEW DISCORD VANITIES</b>\n\n<blockquote>{lines}</blockquote>\n\n"
                    f"{contact} Contact @floral\n{list_icon} List Via: @LateProxyApp")

        send_draft(api, owner_id, batch)
        db.executemany(
            "UPDATE vanity_reviews SET draft_sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            [(row[0],) for row in rows],
        )
    api("editMessageText", chat_id=owner_id, message_id=message_id,
        text=f"Sent a copy-ready draft for {len(rows)} Discord vanities.",
        reply_markup={"inline_keyboard": []})


def remove_listing(db, api, listing_id):
    published_at, channel_id, message_id = db.execute(
        "SELECT published_at, published_channel_id, published_message_id FROM vanity_reviews WHERE id = ?",
        (listing_id,),
    ).fetchone()
    if not published_at:
        return ""
    if channel_id is None or message_id is None:
        return "This older channel post has no saved message ID. Remove the listing from that post manually."

    others = db.execute(
        """SELECT id, vanity, bin FROM vanity_reviews
           WHERE published_channel_id = ? AND published_message_id = ?
               AND status != 'delisted' AND id != ? ORDER BY id""",
        (channel_id, message_id, listing_id),
    ).fetchall()
    post = None
    if others:
        from telethon import types

        stickers = api("getStickerSet", name="EvaluateEmojis")["stickers"]
        post = format_post(others, stickers, types)
    asyncio.run(account_client(post=post, channel_message=(channel_id, message_id)))
    return ""


if __name__ == "__main__":
    from pathlib import Path
    from floral_bot import load_env

    load_env(Path(__file__).resolve().parents[2] / ".env")
    asyncio.run(account_client(sign_in=True))
