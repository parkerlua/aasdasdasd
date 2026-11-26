import os
import re
from urllib.error import URLError

from features.vanity.flow import amount, format_amount
from telegram_api import TelegramError

PAGE_SIZE = 8


def setup(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS offer_notifications (
            user_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1))
        );
        CREATE TABLE IF NOT EXISTS offer_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            offer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS offer_edits (
            staff_id INTEGER PRIMARY KEY,
            listing_id INTEGER NOT NULL
        );
    """)


def is_staff(user_id, owner_id):
    return user_id == owner_id or str(user_id) in {
        item.strip() for item in os.environ.get("FLORAL_STAFF_IDS", "").split(",")
    }


def enabled(db, user_id):
    row = db.execute("SELECT enabled FROM offer_notifications WHERE user_id = ?", (user_id,)).fetchone()
    return row is None or bool(row[0])


def clear(db, staff_id):
    with db:
        db.execute("DELETE FROM offer_edits WHERE staff_id = ?", (staff_id,))


def settings(db, api, user_id, message_id):
    state = enabled(db, user_id)
    label, style, action = ("Turn off", "danger", "notify:off") if state else ("Turn on", "success", "notify:on")
    content = (
        f"<p>Current offer notifications are {'on' if state else 'off'}.</p>"
        '<tg-button-row align="center">'
        f'<tg-button type="callback_data" style="{style}" data="{action}">{label}</tg-button>'
        '<tg-button type="callback_data" data="urls_back">Back</tg-button>'
        '</tg-button-row>'
    )
    api(
        "editMessageText", chat_id=user_id, message_id=message_id,
        rich_message={"html": content}, reply_markup={"inline_keyboard": []},
    )



def listing_page(db, api, staff_id, seller_id, page=0, message_id=None):
    rows = db.execute(
        """SELECT id, vanity, status FROM vanity_reviews WHERE user_id = ? AND status != 'delisted'
           ORDER BY id DESC LIMIT ? OFFSET ?""",
        (seller_id, PAGE_SIZE + 1, page * PAGE_SIZE),
    ).fetchall()
    buttons = [[{"text": f"#{item} · {name.splitlines()[0][:35]} · {status.title()}",
                 "callback_data": f"co:listing:{item}"}]
               for item, name, status in rows[:PAGE_SIZE]]
    navigation = []
    if page:
        navigation.append({"text": "Previous", "callback_data": f"co:page:{seller_id}:{page - 1}"})
    if len(rows) > PAGE_SIZE:
        navigation.append({"text": "Next", "callback_data": f"co:page:{seller_id}:{page + 1}"})
    if navigation:
        buttons.append(navigation)
    text = f"Listings for Telegram user {seller_id}" if rows else f"No listings found for Telegram user {seller_id}."
    params = {"chat_id": staff_id, "text": text, "reply_markup": {"inline_keyboard": buttons}}
    if message_id is None:
        api("sendMessage", **params)
    else:
        api("editMessageText", message_id=message_id, **params)


def start(db, api, staff_id, args):
    clear(db, staff_id)
    if len(args) != 1 or not re.fullmatch(r"[1-9][0-9]{0,17}", args[0]):
        api("sendMessage", chat_id=staff_id, text="Usage: /co TELEGRAM_USER_ID")
        return
    listing_page(db, api, staff_id, int(args[0]))


def offer_keyboard(offer_id, contact=False):
    keyboard = [
        [
            {"text": "Accept", "style": "success", "callback_data": f"co:respond:accept:{offer_id}"},
            {"text": "Decline", "style": "danger", "callback_data": f"co:respond:decline:{offer_id}"},
        ],
        [{"text": "Contact @Floral", "url": "https://t.me/Floral"} if contact else
         {"text": "Negotiate", "callback_data": f"co:respond:negotiate:{offer_id}"}],
    ]
    return {"inline_keyboard": keyboard}


def offer_text(listing_id, item, offer):
    return f"New current offer for listing #{listing_id} · {item.splitlines()[0]}\n\nCurrent offer: {offer}"


def respond(db, api, seller_id, owner_id, message_id, answer, action):
    match = re.fullmatch(r"co:respond:(accept|decline|negotiate):([0-9]{1,18})", action)
    if not match:
        api("answerCallbackQuery", **answer)
        return
    choice, offer_id = match[1], int(match[2])
    row = db.execute(
        """SELECT r.listing_id, r.offer, v.vanity
           FROM offer_responses r JOIN vanity_reviews v ON v.id = r.listing_id
           WHERE r.id = ? AND r.seller_id = ? AND v.user_id = ? AND r.status = 'pending'
             AND v.status IN ('approved', 'pending') AND v.offer = r.offer""",
        (offer_id, seller_id, seller_id),
    ).fetchone()
    if not row:
        api("answerCallbackQuery", **answer, text="This offer is no longer open.", show_alert=True)
        return
    listing_id, offer, item = row
    text = offer_text(listing_id, item, offer)
    if choice == "negotiate":
        api("answerCallbackQuery", **answer)
        api("editMessageText", chat_id=seller_id, message_id=message_id,
            text=f"{text}\n\nContact @Floral to negotiate.",
            reply_markup=offer_keyboard(offer_id, contact=True), link_preview_options={"is_disabled": True})
        return

    decision = "accepted" if choice == "accept" else "declined"
    try:
        with db:
            updated = db.execute(
                "UPDATE offer_responses SET status = ? WHERE id = ? AND status = 'pending'",
                (decision, offer_id),
            ).rowcount
            if updated:
                api("sendMessage", chat_id=owner_id,
                    text=f"Seller {seller_id} {decision} the {offer} offer on listing #{listing_id} · {item.splitlines()[0]}.",
                    link_preview_options={"is_disabled": True})
    except (TelegramError, URLError, TimeoutError):
        api("answerCallbackQuery", **answer, text="Could not notify @Floral. Please try again.", show_alert=True)
        return
    if not updated:
        api("answerCallbackQuery", **answer, text="This offer is no longer open.")
        return
    api("answerCallbackQuery", **answer)
    feedback = ("Offer accepted. @Floral has been notified and will follow up with you."
                if choice == "accept" else "Offer declined.")
    api("editMessageText", chat_id=seller_id, message_id=message_id,
        text=f"{text}\n\n{feedback}", reply_markup={"inline_keyboard": []},
        link_preview_options={"is_disabled": True})


def handle_button(db, api, user_id, owner_id, callback):
    action = callback["data"]
    message_id = callback["message"]["message_id"]
    answer = {"callback_query_id": callback["id"]}
    if action in ("notifications", "notify:on", "notify:off"):
        api("answerCallbackQuery", **answer)
        if action != "notifications":
            state = int(action == "notify:on")
            if enabled(db, user_id) == bool(state):
                return
            with db:
                db.execute("REPLACE INTO offer_notifications VALUES (?, ?)", (user_id, state))
        settings(db, api, user_id, message_id)
        return

    if action.startswith("co:respond:"):
        respond(db, api, user_id, owner_id, message_id, answer, action)
        return
    if not is_staff(user_id, owner_id):
        api("answerCallbackQuery", **answer)
        return
    page = re.fullmatch(r"co:page:([0-9]{1,18}):([0-9]{1,9})", action)
    item = re.fullmatch(r"co:listing:([0-9]{1,18})", action)
    if page:
        api("answerCallbackQuery", **answer)
        clear(db, user_id)
        listing_page(db, api, user_id, int(page[1]), int(page[2]), message_id)
    elif item:
        listing_id = int(item[1])
        row = db.execute("SELECT vanity, status, offer FROM vanity_reviews WHERE id = ?", (listing_id,)).fetchone()
        if not row or row[1] not in ("pending", "approved"):
            api("answerCallbackQuery", **answer, text="That listing is closed.", show_alert=True)
            return
        api("answerCallbackQuery", **answer)
        with db:
            db.execute("REPLACE INTO offer_edits VALUES (?, ?)", (user_id, listing_id))
        api(
            "editMessageText", chat_id=user_id, message_id=message_id,
            text=f"#{listing_id} · {row[0].splitlines()[0]}\nCurrent offer: {row[2]}\n\nEnter the new offer.",
            reply_markup={"inline_keyboard": [[{"text": "Cancel", "callback_data": "co:cancel"}]]},
        )
    elif action == "co:cancel":
        clear(db, user_id)
        api("answerCallbackQuery", **answer, text="Cancelled.")
        api("editMessageText", chat_id=user_id, message_id=message_id, text="Offer update cancelled.")
    else:
        api("answerCallbackQuery", **answer)


def handle_text(db, api, user_id, owner_id, text):
    if not is_staff(user_id, owner_id) or text.startswith("/"):
        return False
    edit = db.execute("SELECT listing_id FROM offer_edits WHERE staff_id = ?", (user_id,)).fetchone()
    if not edit:
        return False
    cents = amount(text)
    if not cents:
        api("sendMessage", chat_id=user_id, text="Enter a positive offer amount, for example $75 or 1.2k.")
        return True
    listing_id = edit[0]
    offer = format_amount(cents)
    with db:
        row = db.execute(
            "SELECT user_id, vanity FROM vanity_reviews WHERE id = ? AND status IN ('pending', 'approved')",
            (listing_id,),
        ).fetchone()
        if row:
            db.execute("UPDATE vanity_reviews SET offer = ? WHERE id = ?", (offer, listing_id))
            db.execute("UPDATE offer_responses SET status = 'superseded' WHERE listing_id = ? AND status = 'pending'",
                       (listing_id,))
            if enabled(db, row[0]):
                offer_id = db.execute(
                    "INSERT INTO offer_responses (listing_id, seller_id, offer) VALUES (?, ?, ?)",
                    (listing_id, row[0], offer),
                ).lastrowid
            else:
                offer_id = None
        db.execute("DELETE FROM offer_edits WHERE staff_id = ?", (user_id,))
    if not row:
        api("sendMessage", chat_id=user_id, text="That listing is closed.")
        return True
    seller_id, item = row
    if offer_id is not None:
        try:
            api("sendMessage", chat_id=seller_id,
                text=offer_text(listing_id, item, offer), reply_markup=offer_keyboard(offer_id),
                link_preview_options={"is_disabled": True})
            result = "Seller notified."
        except (TelegramError, URLError, TimeoutError):
            result = "The bot could not deliver the seller’s DM."
    else:
        result = "The seller has offer notifications off."
    api("sendMessage", chat_id=user_id, text=f"Current offer updated to {offer}. {result}")
    return True
