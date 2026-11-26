import html
import json
import re

from urllib.error import URLError

from telegram_api import TelegramError

from . import details, discord_profile, publishing


INVITE = re.compile(r"(?:https?://)?(?:discord\.gg/|discord(?:app)?\.com/invite/|\.gg/|/)?([a-z0-9-]{1,32})/?", re.I | re.ASCII)
PRICE = re.compile(r"\$?(\d{1,9}(?:\.\d{1,2})?)(k)?", re.I | re.ASCII)

MIN_BIN_CENTS = 3500
EMAIL_BUTTONS = ((0, 4), (1, 3), (6, None))
BADGE_CATEGORY_EMOJIS = {"Rare": 10, "Nitro": 16, "Boosts": 24, "Other": 15}

VANITY_PROMPT = "What is the vanity you are selling?\n\nExample: discord.gg/vanity"
ITEM_FIELDS = {
    "discord_vanity": ("Vanity", VANITY_PROMPT),
    "discord_username": ("Discord username", "What is the Discord user ID of the account you are selling?"),
    "discord_badges": ("Discord username", "What is the Discord user ID of the badged account you are selling?"),
    "telegram_username": ("Telegram usernames", "Which Telegram usernames are you selling? Enter one @username per line."),
    "telegram_gift": ("Telegram gift", "What gift are you selling? Enter its t.me/nft/ link."),
    "tiktok_username": ("TikTok username", "What is the TikTok username you are selling?"),
}
GENERAL_BIN_PROMPT = "Enter a buy-it-now price, or choose Taking Offers."
BIN_PROMPT = f"Choose a BIN option.\n\nEnter a buy-it-now price like 2000, $2000, or 2k. Minimum BIN: ${MIN_BIN_CENTS // 100:,}."
OFFER_PROMPT = "What is the current offer?\n\nEnter an amount or choose No Current Offer."
NOTES_PROMPT = "Add any notes about the vanity, or choose Skip Notes."
STEPS = {"vanity": 1, "bin": 2, "offer": 3, "notes": 4, "review": 5}
CANCEL = ("Cancel", "vanity_cancel")


def setup(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vanity_drafts (
            user_id INTEGER PRIMARY KEY,
            stage TEXT NOT NULL,
            vanity TEXT,
            bin TEXT,
            offer TEXT,
            message_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS vanity_reviews (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            vanity TEXT NOT NULL,
            bin TEXT NOT NULL,
            offer TEXT NOT NULL
        );
    """)

    migrations = (
        ("vanity_drafts", "message_id", "INTEGER"),
        ("vanity_drafts", "notes", "TEXT NOT NULL DEFAULT ''"),
        ("vanity_reviews", "notes", "TEXT NOT NULL DEFAULT ''"),
        ("vanity_reviews", "status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("vanity_reviews", "published_at", "TEXT"),
        ("vanity_reviews", "draft_sent_at", "TEXT"),
        ("vanity_reviews", "profile_card_id", "TEXT"),
        ("vanity_reviews", "published_channel_id", "INTEGER"),
        ("vanity_reviews", "published_message_id", "INTEGER"),
        ("vanity_drafts", "category", "TEXT NOT NULL DEFAULT 'discord_vanity'"),
        ("vanity_drafts", "details", "TEXT NOT NULL DEFAULT '{}'"),
        ("vanity_reviews", "category", "TEXT NOT NULL DEFAULT 'discord_vanity'"),
    )
    with db:
        for table, column, definition in migrations:
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if column not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def draft_for(db, user_id):
    return db.execute(
        "SELECT stage, vanity, bin, offer, message_id, notes, category FROM vanity_drafts WHERE user_id = ?", (user_id,)
    ).fetchone()


def rich_content(text, *buttons, stage=None, pair_first_buttons=False, badge_icons=None):
    paragraphs = "".join(
        f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>"
        for paragraph in text.split("\n\n")
    )
    paragraphs = re.sub(
        r"(Profile picture: |Banner: )(https://cdn\.discordapp\.com/[A-Za-z0-9_/.?=]+)(?=<)",
        lambda match: f'{match[1]}<a href="{match[2]}">View image</a>',
        paragraphs,
    )
    rows = []
    if stage is not None:
        number, total = stage
        label = f"STEP {number} / {total}" if total is not None else f"STEP {number}"
        rows.append(
            '<tg-button-row align="center">'
            f'<tg-button type="disabled">{label}</tg-button>'
            '</tg-button-row>'
        )
    def button_tag(button):
        label, action = button
        style = "primary"
        if action == "vanity_cancel":
            style = "danger"
        elif action == "vanity_detail:badges:done" or label.startswith("✓ "):
            style = "success"
        elif action.startswith(("vanity_detail:group:", "vanity_detail:badges:")):
            style = ""
        color = f' style="{style}"' if style else ""
        icon = (badge_icons or {}).get(action, "")
        return f'<tg-button type="callback_data"{color} data="{action}">{icon}{html.escape(label)}</tg-button>' 

    if any(action == "vanity_detail:badges:done" for _, action in buttons):
        tabs = [button for button in buttons if button[1].startswith("vanity_detail:group:")]
        choices = [button for button in buttons if button[1].startswith("vanity_detail:badges:")
                   and button[1] != "vanity_detail:badges:done"]
        controls = [button for button in buttons if button not in tabs and button not in choices]
        button_rows = [group[index:index + width] for group, width in ((tabs, 4), (choices, 3), (controls, 2))
                       for index in range(0, len(group), width)]
    else:
        paired = 2 if pair_first_buttons is True else int(pair_first_buttons)
        button_rows = [buttons[i:i + 2] for i in range(0, paired, 2)]
        button_rows.extend((button,) for button in buttons[paired:])

    rows.extend(
        '<tg-button-row align="center">' + "".join(map(button_tag, row)) + '</tg-button-row>'
        for row in button_rows
    )
    return {"html": paragraphs + "".join(rows), "skip_entity_detection": True}


def edit_step(api, user_id, message_id, text, *buttons, stage=None, pair_first_buttons=False):
    api(
        "editMessageText", chat_id=user_id, message_id=message_id,
        rich_message=rich_content(text, *buttons, stage=stage, pair_first_buttons=pair_first_buttons),
        reply_markup={"inline_keyboard": []},
    )


def send_review_message(api, owner_id, text):
    api("sendMessage", chat_id=owner_id, text=text, link_preview_options={"is_disabled": True})


def summary(vanity, bin_price, offer, notes, category="discord_vanity"):
    label = ITEM_FIELDS[category][0]
    return f"{label}: {vanity}\nBIN: {bin_price}\nCurrent offer: {offer}\nNotes: {notes or 'None'}"


def amount(text):
    match = PRICE.fullmatch(text.replace(",", ""))
    if not match:
        return None
    whole, _, fraction = match[1].partition(".")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    return cents * (1000 if match[2] else 1)


def format_amount(cents):
    dollars, remainder = divmod(cents, 100)
    return f"${dollars:,}.{remainder:02d}" if remainder else f"${dollars:,}"


def progress(draft, values):
    stage, _, _, offer, _, _, category = draft
    if category == "discord_vanity":
        path = list(STEPS)
    else:
        questions = details.questions(category, values)
        path = ["vanity"] if category not in discord_profile.CATEGORIES else []
        path += ["vanity" if key == "discord_id" else f"detail:{key}" for key in questions]
        path += ["offer"]
        if offer and offer != "None":
            path.append("detail:offer_proof")
        path += ["bin", "detail:tiktok_proof" if category == "tiktok_username" else "notes", "review"]
    total = len(path) if category == "discord_vanity" else None
    return (path.index(stage) + 1, total) if stage in path else None


def show_detail(api, user_id, message_id, key, category, values, position):
    prompt, buttons = details.screen(key, category, values)
    if key == "email":
        show_email_provider(api, user_id, message_id, prompt, buttons, position)
        return
    if key == "badges":
        categories = [button for button in buttons if button[1].startswith("vanity_detail:group:")]
        choices = [button for button in buttons if button not in categories]
        active = values.get("_group") or "Rare" if categories else "Rare"
        tabs = [
            (label, action, BADGE_CATEGORY_EMOJIS[label] - 1, "success" if label == active else None)
            for label, action in categories
        ]
        edit_with_icon_buttons(
            api, user_id, message_id,
            lambda stickers: rich_content(
                prompt, *choices, CANCEL, stage=position,
                badge_icons=badge_tier_icons(stickers, active),
            ),
            [tabs] if tabs else [],
        )
        return
    paired = {"oge": 2, "pb": 2, "standing": 4}.get(key, 0)
    edit_step(api, user_id, message_id, prompt, *buttons, CANCEL, stage=position, pair_first_buttons=paired)


def show_email_provider(api, user_id, message_id, prompt, buttons, position):
    row = [(*buttons[choice], emoji_index, None) for choice, emoji_index in EMAIL_BUTTONS]
    edit_with_icon_buttons(api, user_id, message_id, rich_content(prompt, stage=position), [row])


def badge_tier_icons(stickers, group):
    rare = ((12, "🏆"), (13, "💗"), (10, "🛡"), (11, "🛡"), (9, "🛠"),
            (8, "🤝"), (14, "💻"), (7, "🐛"), (6, "🏅"))
    positions = {
        "Nitro": [position for _, position in details.NITRO_DISPLAY],
        "Boosts": range(24, 24 + len(details.BADGES["Boosts"])),
    }
    icons = {}
    choices = rare if group == "Rare" else [(position, "") for position in positions.get(group, ())]
    for index, (position, symbol) in enumerate(choices):
        action = f"vanity_detail:badges:{group}:{index}"
        if symbol:
            icons[action] = f"{symbol} "
        if position is not None and len(stickers) >= position:
            emoji = stickers[position - 1]
            emoji_id = emoji.get("custom_emoji_id", "")
            if re.fullmatch(r"[0-9]+", emoji_id):
                fallback = html.escape(emoji.get("emoji") or "💎")
                icons[action] = f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> '
    return icons


def edit_with_icon_buttons(api, user_id, message_id, content, rows):
    try:
        stickers = api("getStickerSet", name="EvaluateEmojis")["stickers"]
    except (TelegramError, URLError, TimeoutError):
        stickers = []

    def keyboard(with_icons):
        result = []
        for row in rows:
            buttons = []
            for label, action, emoji_index, style in row:
                button = {"text": label, "callback_data": action}
                if style:
                    button["style"] = style
                if with_icons and emoji_index is not None and len(stickers) > emoji_index:
                    emoji_id = stickers[emoji_index].get("custom_emoji_id")
                    if emoji_id:
                        button["icon_custom_emoji_id"] = emoji_id
                buttons.append(button)
            result.append(buttons)
        return {"inline_keyboard": result}

    markup = keyboard(True)
    with_icons = content(stickers) if callable(content) else content
    try:
        api("editMessageText", chat_id=user_id, message_id=message_id,
            rich_message=with_icons, reply_markup=markup)
    except TelegramError as error:
        if error.code != 400 or not (callable(content) or any(
            "icon_custom_emoji_id" in button for row in markup["inline_keyboard"] for button in row
        )):
            raise
        api("editMessageText", chat_id=user_id, message_id=message_id,
            rich_message=content([]) if callable(content) else content, reply_markup=keyboard(False))


def save_detail(db, api, user_id, message_id, category, key, value):
    values = details.load(db, user_id)
    values[key] = value
    if key in ("offer_proof", "tiktok_proof"):
        next_stage = "review" if key == "tiktok_proof" else "bin"
    else:
        questions = details.questions(category, values)
        index = questions.index(key) + 1
        next_stage = f"detail:{questions[index]}" if index < len(questions) else "offer"
        if next_stage == "detail:discord_id":
            next_stage = "vanity"
    with db:
        db.execute("UPDATE vanity_drafts SET stage = ?, details = ? WHERE user_id = ?",
                   (next_stage, json.dumps(values), user_id))
    show_stage(db, api, user_id, message_id, next_stage)


def handle_detail_button(db, api, user_id, message_id, stage, category, action):
    key = stage.removeprefix("detail:")
    values = details.load(db, user_id)
    parts = action.removeprefix(details.BUTTON).split(":")
    groups = ("Rare",) if category == "discord_username" else tuple(details.BADGES)
    if key == "badges":
        chosen = values.setdefault("badges", [])
        if parts == ["badges", "done"]:
            save_detail(db, api, user_id, message_id, category, key, chosen)
            return
        if len(parts) == 2 and parts[0] == "group" and parts[1] in groups:
            if parts[1] == values.get("_group", groups[0]):
                return
            values["_group"] = parts[1]
        elif len(parts) == 3 and parts[0] == key and parts[1] in groups and parts[2].isdigit():
            labels = details.BADGES[parts[1]]
            index = int(parts[2])
            if index >= len(labels):
                return
            label = labels[index]
            if label in chosen:
                chosen.remove(label)
            else:
                if parts[1] in details.SINGLE_SELECT_BADGE_GROUPS:
                    chosen[:] = [badge for badge in chosen if badge not in labels]
                chosen.append(label)
            values["_group"] = parts[1]
        else:
            return
        with db:
            db.execute("UPDATE vanity_drafts SET details = ? WHERE user_id = ?", (json.dumps(values), user_id))
        show_detail(api, user_id, message_id, key, category, values, progress(draft_for(db, user_id), values))
        return
    if key not in details.QUESTIONS or len(parts) != 2 or parts[0] != key or not parts[1].isdigit():
        return
    choices = details.QUESTIONS[key][2]
    index = int(parts[1])
    if key == "oge" and index == 1:
        edit_step(
            api, user_id, message_id,
            "Sorry, we only list accounts that still have their original email address.",
            ("Back", "evaluate"),
        )
        with db:
            db.execute("DELETE FROM vanity_drafts WHERE user_id = ? AND message_id = ?",
                       (user_id, message_id))
        return
    if key == "email" and index not in {choice for choice, _ in EMAIL_BUTTONS}:
        show_detail(api, user_id, message_id, key, category, values, progress(draft_for(db, user_id), values))
        return
    if index < len(choices):
        save_detail(db, api, user_id, message_id, category, key, choices[index])


def handle_photo(db, api, user_id, photo):
    draft = draft_for(db, user_id)
    if draft and draft[0].startswith("detail:") and draft[4] is not None:
        key = draft[0].removeprefix("detail:")
        if key in details.PHOTOS:
            save_detail(db, api, user_id, draft[4], draft[-1], key, photo)


def accept_answer(db, api, user_id, message_id, stage, value):
    column, next_stage = {
        "vanity": ("vanity", "bin"),
        "bin": ("bin", "offer"),
        "offer": ("offer", "notes"),
        "notes": ("notes", "review"),
    }[stage]
    draft = draft_for(db, user_id)
    if not draft or draft[0] != stage or draft[4] != message_id:
        return
    category = draft[-1]
    if stage == "vanity":
        questions = details.questions(category, {})
        if category in discord_profile.CATEGORIES:
            steps = details.questions(category, details.load(db, user_id))
            next_stage = f"detail:{steps[steps.index('discord_id') + 1]}"
        elif questions:
            next_stage = f"detail:{questions[0]}"
        elif category != "discord_vanity":
            next_stage = "offer"
    elif stage == "offer" and category != "discord_vanity":
        next_stage = "bin" if value == "None" else "detail:offer_proof"
    elif stage == "bin" and category != "discord_vanity":
        next_stage = "detail:tiktok_proof" if category == "tiktok_username" else "notes"
    with db:
        changed = db.execute(
            f"UPDATE vanity_drafts SET {column} = ?, stage = ? WHERE user_id = ? AND stage = ? AND message_id = ?",
            (value, next_stage, user_id, stage, message_id),
        ).rowcount
    if not changed:
        return
    show_stage(db, api, user_id, message_id, next_stage)


def show_stage(db, api, user_id, message_id, next_stage):
    draft = draft_for(db, user_id)
    _, vanity, bin_price, offer, _, notes, category = draft
    values = details.load(db, user_id)
    position = progress(draft, values)
    if next_stage == "vanity":
        edit_step(api, user_id, message_id, ITEM_FIELDS[category][1], CANCEL, stage=position)
    elif next_stage == "detail:proof":
        ready = values.get("_card") or send_profile_preview(db, api, user_id, vanity, category)
        prompt = details.PHOTOS["proof"]
        if not ready:
            prompt += "\n\nThe generated profile example is unavailable. You can still upload your screenshot."
        edit_step(api, user_id, message_id, prompt, CANCEL, stage=position)
    elif next_stage.startswith("detail:"):
        show_detail(api, user_id, message_id, next_stage.removeprefix("detail:"), category, values, position)
    elif next_stage == "bin":
        edit_step(api, user_id, message_id, BIN_PROMPT if category == "discord_vanity" else GENERAL_BIN_PROMPT, ("Taking Offers", "vanity_taking_offers"), CANCEL, stage=position)
    elif next_stage == "offer":
        edit_step(api, user_id, message_id, OFFER_PROMPT, ("No Current Offer", "vanity_no_offer"), CANCEL, stage=position)
    elif next_stage == "notes":
        edit_step(api, user_id, message_id, notes_prompt(category), ("Skip Notes", "vanity_skip_notes"), CANCEL, stage=position)
    else:
        preview = summary(with_details(vanity, values), bin_price, offer, notes, category)
        if (category in discord_profile.CATEGORIES and not values.get("_card")
                and not send_profile_preview(db, api, user_id, vanity, category)):
            preview += "\n\nThe profile card could not load the Discord avatar."
        edit_step(api, user_id, message_id, preview, ("Send for Review", "vanity_submit"), CANCEL, stage=position)


def notes_prompt(category):
    if category == "discord_vanity":
        return NOTES_PROMPT
    if category == "discord_badges":
        return "Add badge names and any listing notes, or choose Skip Notes. Do not include sign-in credentials."
    return "Add any listing notes, or choose Skip Notes. Do not include sign-in credentials."


def normalize_item(category, text):
    if category == "discord_vanity":
        match = INVITE.fullmatch(text)
        return f".gg/{match[1]}" if match else None
    if category in discord_profile.CATEGORIES:
        return discord_profile.lookup(text)
    if category == "telegram_gift":
        match = re.fullmatch(r"(?:https?://)?t\.me/nft/([a-z0-9]{1,64}-[0-9]{1,12})/?", text, re.I | re.ASCII)
        return f"https://t.me/nft/{match[1]}" if match else None
    if category == "telegram_username":
        names = [name.strip().removeprefix("@") for name in text.splitlines() if name.strip()]
        if 1 <= len(names) <= 5 and all(re.fullmatch(r"[A-Za-z0-9_]{1,32}", name) for name in names):
            return ", ".join(f"@{name}" for name in names)
        return None
    username = text.removeprefix("@")
    if re.fullmatch(r"[A-Za-z0-9_.]{1,32}", username):
        return f"@{username}"
    return None


def handle_text(db, api, user_id, text):
    draft = draft_for(db, user_id)
    if not draft or draft[0] == "review" or draft[4] is None:
        return
    stage, _, _, _, message_id, _, category = draft
    position = progress(draft, details.load(db, user_id))
    if stage.startswith("detail:"):
        key = stage.removeprefix("detail:")
        if key == "domain" and re.fullmatch(r"[A-Za-z0-9.-]{1,80}", text):
            save_detail(db, api, user_id, message_id, category, key, text)
        return
    if stage == "vanity":
        try:
            value = normalize_item(category, text)
        except discord_profile.ProfileError as error:
            edit_step(api, user_id, message_id, f"{error}\n\n{ITEM_FIELDS[category][1]}", CANCEL, stage=position)
            return
        if value is None:
            edit_step(api, user_id, message_id, "Enter a valid listing item.\n\n" + ITEM_FIELDS[category][1], CANCEL, stage=position)
            return
    elif stage == "notes":
        if len(text) > 1000:
            edit_step(api, user_id, message_id, "Notes must be 1,000 characters or fewer.\n\n" + notes_prompt(category),
                      ("Skip Notes", "vanity_skip_notes"), CANCEL, stage=position)
            return
        value = text
    else:
        cents = amount(text)
        minimum = (MIN_BIN_CENTS if category == "discord_vanity" else 1) if stage == "bin" else 0
        if cents is None or cents < minimum:
            prompt = OFFER_PROMPT
            if stage == "bin":
                prompt = BIN_PROMPT if category == "discord_vanity" else GENERAL_BIN_PROMPT
            option = ("Taking Offers", "vanity_taking_offers") if stage == "bin" else ("No Current Offer", "vanity_no_offer")
            edit_step(api, user_id, message_id, "Enter a valid amount.\n\n" + prompt, option, CANCEL, stage=position)
            return
        value = "None" if stage == "offer" and cents == 0 else format_amount(cents)
    accept_answer(db, api, user_id, message_id, stage, value)


def handle_button(db, api, user_id, callback, owner_id=None):
    action = callback["data"]
    message_id = callback["message"]["message_id"]
    api("answerCallbackQuery", callback_query_id=callback["id"])
    if action.startswith("vanity_publish:"):
        if user_id == owner_id:
            publishing.publish(db, api, owner_id, message_id, action)
        return
    if action.startswith("vanity_decide:"):
        if user_id == owner_id:
            decide(db, api, owner_id, message_id, action)
        return
    category = action.removeprefix("eval:")
    if category in ITEM_FIELDS:
        with db:
            db.execute(
                "INSERT OR REPLACE INTO vanity_drafts (user_id, stage, message_id, category) VALUES (?, 'vanity', ?, ?)",
                (user_id, message_id, category),
            )
        if category in discord_profile.CATEGORIES:
            with db:
                db.execute("UPDATE vanity_drafts SET stage = 'detail:oge' WHERE user_id = ?", (user_id,))
            show_stage(db, api, user_id, message_id, "detail:oge")
        else:
            show_stage(db, api, user_id, message_id, "vanity")
        return
    draft = draft_for(db, user_id)
    if not draft or draft[4] != message_id:
        return
    if action.startswith(details.BUTTON) and draft[0].startswith("detail:"):
        handle_detail_button(db, api, user_id, message_id, draft[0], draft[-1], action)
    elif action == "vanity_cancel":
        with db:
            deleted = db.execute("DELETE FROM vanity_drafts WHERE user_id = ?", (user_id,)).rowcount
        if deleted:
            edit_step(api, user_id, message_id, "Listing cancelled. Use /start to return to the menu.")
    elif action == "vanity_taking_offers":
        accept_answer(db, api, user_id, message_id, "bin", "Taking Offers")
    elif action == "vanity_no_offer":
        accept_answer(db, api, user_id, message_id, "offer", "None")
    elif action == "vanity_skip_notes":
        accept_answer(db, api, user_id, message_id, "notes", "")
    elif action == "vanity_submit" and owner_id is not None:
        with db:
            result = db.execute(
                """INSERT INTO vanity_reviews (user_id, vanity, bin, offer, notes, category)
                   SELECT user_id, vanity, bin, offer, notes, category FROM vanity_drafts
                   WHERE user_id = ? AND stage = 'review'""",
                (user_id,),
            )
            if not result.rowcount:
                return
            review_id = result.lastrowid
            values = details.load(db, user_id)
            _, vanity, bin_price, offer, _, notes, category = draft
            vanity = with_details(vanity, values)
            db.execute(
                "UPDATE vanity_reviews SET vanity = ?, profile_card_id = ? WHERE id = ?",
                (vanity, values.get("_card"), review_id),
            )
            text = review_message(review_id, user_id, vanity, bin_price, offer, notes, category)
            api(
                "sendRichMessage", chat_id=owner_id,
                rich_message=review_content(text, user_id),
                reply_markup={"inline_keyboard": [[
                    {"text": "Approve", "style": "success",
                     "callback_data": f"vanity_decide:approved:{review_id}"},
                    {"text": "Deny", "style": "danger",
                     "callback_data": f"vanity_decide:denied:{review_id}"},
                ]]},
            )
            db.execute("DELETE FROM vanity_drafts WHERE user_id = ?", (user_id,))
        edit_step(api, user_id, message_id, f"Listing #{review_id} sent for review.")
        if values.get("_card"):
            api("sendPhoto", chat_id=owner_id, photo=values["_card"],
                caption=f"Listing #{review_id} · Profile card")
        for key in details.PHOTOS:
            if key in values:
                api("sendPhoto", chat_id=owner_id, photo=values[key],
                    caption=f"Listing #{review_id} · {key.replace('_', ' ').title()}", protect_content=True)


def download_profile_image(url, folder):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    match = re.fullmatch(
        rf"https://cdn\.discordapp\.com/((?:{folder}/|embed/avatars/)[A-Za-z0-9_/.]+)"
        r"(?:\?size=[0-9]+)?",
        url,
    )
    if not match:
        if folder == "avatars":
            print("Discord avatar lookup returned no usable image URL.", flush=True)
        return None

    path = match[1]
    candidates = [url]
    if not path.startswith("embed/"):
        png_path = path.rsplit(".", 1)[0] + ".png"
        candidates += [
            f"https://media.discordapp.net/{png_path}?width=256",
            f"https://cdn.discordapp.com/{png_path}",
        ]
    for candidate in dict.fromkeys(candidates):
        request = Request(candidate, headers={"User-Agent": "EvaluateProfilePreview/1.0", "Accept": "image/*"})
        host = request.host
        try:
            with urlopen(request, timeout=5) as response:
                image = response.read(4_000_001)
            if 0 < len(image) <= 4_000_000:
                return image
            reason = "empty image or image exceeds 4 MB"
        except HTTPError as error:
            reason = f"HTTP {error.code}"
        except (URLError, TimeoutError, OSError) as error:
            reason = str(getattr(error, "reason", error))
        print(f"Discord {folder} download from {host} failed ({reason}).", flush=True)
    return None


def send_profile_preview(db, api, user_id, account, category):
    values = details.load(db, user_id)
    fields = dict(line.split(": ", 1) for line in account.splitlines()[1:] if ": " in line)
    avatar = download_profile_image(fields.get("Profile picture", ""), "avatars")
    if not avatar:
        print("Discord avatar download failed for generated profile example.", flush=True)
        return False
    try:
        from .profile_card import CardData, render

        badge_names = []
        for badge in values.get("badges", []):
            label = badge.replace(" · ", " — ")
            if label.startswith("Nitro — "):
                months = int(label.split()[-2])
                tiers = dict(zip((1, 3, 6, 12, 24, 36, 60, 72),
                                 ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Emerald", "Ruby", "Opal")))
                label = f"Nitro {tiers[months]} — {months}{'+' if months == 72 else ''} Month{'s' if months != 1 else ''}"
            elif label.startswith("Boost — "):
                label = label.replace(" months", " Month" if label.startswith("Boost — 1 ") else " Months")
            badge_names.append(label)
        photo = render(CardData(
            created=fields.get("Created", "Unknown"), display=fields.get("Display name", ""),
            username=account.splitlines()[0], show_username=category == "discord_username",
            badges=badge_names, avatar=avatar, blur_avatar=False,
            banner=download_profile_image(fields.get("Banner", ""), "banners"),
        ))
        result = api("sendPhoto", chat_id=user_id, photo=photo, caption="Generated profile example", protect_content=True)
        if result and result.get("photo"):
            values["_card"] = result["photo"][-1]["file_id"]
            with db:
                db.execute("UPDATE vanity_drafts SET details = ? WHERE user_id = ?", (json.dumps(values), user_id))
        return bool(values.get("_card"))
    except (ImportError, OSError, ValueError, TelegramError, URLError, TimeoutError) as error:
        print(f"Discord profile card preview unavailable ({type(error).__name__}: {error}).", flush=True)
        return False


def with_details(item, values):
    description = details.describe(values)
    return f"{item}\n{description}" if description else item


def review_message(review_id, seller, vanity, bin_price, offer, notes, category):
    return f"Listing #{review_id} · Telegram ID {seller}\n\n{summary(vanity, bin_price, offer, notes, category)}"


def review_content(text, seller):
    content = rich_content(text)
    telegram_id = f"Telegram ID {seller}"
    mention = f'<a href="tg://user?id={seller}">{telegram_id}</a>'
    content["html"] = content["html"].replace(telegram_id, mention, 1)
    return content


def decide(db, api, owner_id, message_id, action):
    _, _, payload = action.partition(":")
    decision, _, item = payload.partition(":")
    if decision not in ("approved", "denied") or not re.fullmatch(r"[0-9]{1,18}", item):
        return
    review_id = int(item)
    with db:
        changed = db.execute(
            "UPDATE vanity_reviews SET status = ? WHERE id = ? AND status = 'pending'",
            (decision, review_id),
        ).rowcount
        if not changed:
            return
        row = db.execute(
            "SELECT user_id, vanity, bin, offer, notes, category FROM vanity_reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if decision == "approved" and row[-1] != "discord_vanity":
            photo, = db.execute(
                "SELECT profile_card_id FROM vanity_reviews WHERE id = ?", (review_id,)
            ).fetchone()
            _, item, price, offer, notes, category = row
            publishing.send_draft(
                api, owner_id,
                lambda stickers: publishing.listing_draft(category, item, price, offer, notes, stickers),
                photo=photo if category in discord_profile.CATEGORIES else None,
            )
    if decision == "approved" and row[-1] == "discord_vanity":
        rows = publishing.queued(db)
        if len(rows) == 2:
            publishing.ready_notice(api, owner_id, rows[0][0])
    status = f"{review_message(review_id, *row)}\n\nStatus: {decision.title()}"
    api(
        "editMessageText", chat_id=owner_id, message_id=message_id,
        rich_message=review_content(status, row[0]), reply_markup={"inline_keyboard": []},
    )


def show_reviews(db, api, owner_id, args):
    before = None
    if args:
        if len(args) != 1 or not args[0].isascii() or not args[0].isdigit() or len(args[0]) > 18:
            send_review_message(api, owner_id, "Usage: /reviews [before_id]")
            return
        before = int(args[0])
    rows = db.execute(
        """SELECT id, user_id, vanity, bin, offer, notes, category FROM vanity_reviews
           WHERE status = 'pending' AND (? IS NULL OR id < ?) ORDER BY id DESC LIMIT 4""",
        (before, before),
    ).fetchall()
    if not rows:
        send_review_message(api, owner_id, "No listings awaiting review.")
        return
    page = "\n\n".join(
        review_message(*row) for row in rows[:3]
    )
    if len(rows) > 3:
        page += f"\n\nMore: /reviews {rows[2][0]}"
    send_review_message(api, owner_id, page)
