from features.offers import menu as offer_menu
from features.stock import menu as stock_menu
from features.vanity import flow as vanity_flow
from features.vanity import publishing

from .messages import EVALUATE_CATEGORIES, HELP, WELCOME_KEYBOARD, evaluate_menu, profile, urls_menu, welcome
from .store import ensure_code, get_code, refresh_code

COMMANDS = [
    {"command": "start", "description": "Start the bot"},
    {"command": "string", "description": "Show your code"},
]


def handle_update(update, db, owner_id, bot_username, api, listing_emojis=()):
    callback = update.get("callback_query")
    message = callback.get("message", {}) if callback else update.get("message", {})
    user = callback["from"] if callback else message.get("from", {})
    chat = message.get("chat", {})
    if chat.get("type") != "private" or chat.get("id") != user.get("id"):
        if callback:
            api("answerCallbackQuery", callback_query_id=callback["id"])
        return

    user_id = user["id"]
    chat_id = chat["id"]
    if callback:
        action = callback.get("data")
        answer = {"callback_query_id": callback["id"]}
        if action == "help":
            api("answerCallbackQuery", **answer)
            api("sendMessage", chat_id=chat_id, text=HELP)
        elif action == "refresh":
            ensure_code(db, user_id)
            code, wait = refresh_code(db, user_id)
            if wait:
                api("answerCallbackQuery", **answer, text=f"Try again in {wait}s.", show_alert=True)
            else:
                api("answerCallbackQuery", **answer, text="Code refreshed.")
                api(
                    "editMessageText", chat_id=chat_id, message_id=message["message_id"],
                    rich_message=profile(user, code),
                )
        elif action == "discord_vanity" or (action and action.startswith("vanity_")):
            vanity_flow.handle_button(db, api, user_id, callback, owner_id)
        elif action in ("evaluate_urls", "urls_back"):
            keyboard = {"inline_keyboard": []}
            if action == "evaluate_urls":
                content = urls_menu(listing_emojis)
            else:
                stock_menu.clear_edit(db, user_id)
                content = welcome(user, listing_emojis)
                keyboard = WELCOME_KEYBOARD
            api("answerCallbackQuery", **answer)
            api(
                "editMessageText", chat_id=chat_id, message_id=message["message_id"],
                rich_message=content, reply_markup=keyboard,
            )
        elif action == "active_listings" or (action and action.startswith("stock:")):
            stock_menu.handle_button(db, api, user_id, owner_id, callback)
        elif action == "evaluate":
            api("answerCallbackQuery", **answer)
            api(
                "editMessageText", chat_id=chat_id, message_id=message["message_id"],
                rich_message=evaluate_menu(listing_emojis), reply_markup={"inline_keyboard": []},
            )
        elif action and action.removeprefix("eval:") in EVALUATE_CATEGORIES and action.startswith("eval:"):
            stock_menu.clear_edit(db, user_id)
            vanity_flow.handle_button(db, api, user_id, callback, owner_id)
        elif action == "notifications" or (action and action.startswith(("notify:", "co:"))):
            offer_menu.handle_button(db, api, user_id, owner_id, callback)
        else:
            api("answerCallbackQuery", **answer)
        return

    if message.get("photo"):
        vanity_flow.handle_photo(db, api, user_id, message["photo"][-1]["file_id"])
        return

    parts = message.get("text", "").split()
    if not parts:
        return
    command, _, recipient = parts[0].lower().partition("@")
    if command.startswith("/") and recipient and recipient != bot_username:
        return
    if command == "/string" or (command == "/start" and get_code(db, user_id) is None):
        api(
            "sendRichMessage", chat_id=chat_id,
            rich_message=profile(user, ensure_code(db, user_id)), protect_content=True,
        )
    if command == "/start":
        offer_menu.clear(db, user_id)
        stock_menu.clear_edit(db, user_id)
        api(
            "sendRichMessage", chat_id=chat_id,
            rich_message=welcome(user, listing_emojis), reply_markup=WELCOME_KEYBOARD,
        )
    elif command == "/co":
        if offer_menu.is_staff(user_id, owner_id):
            offer_menu.start(db, api, user_id, parts[1:])
    elif command == "/publish":
        if user_id == owner_id:
            rows = publishing.queued(db)
            if len(rows) >= 2:
                publishing.ready_notice(api, owner_id, rows[0][0])
            else:
                api("sendMessage", chat_id=owner_id, text="The batch needs at least two approved vanities.")
    elif command == "/reviews":
        if user_id == owner_id:
            vanity_flow.show_reviews(db, api, owner_id, parts[1:])
    elif command == "/lookup" and user_id == owner_id:
        if len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit() or len(parts[1]) > 19:
            api("sendMessage", chat_id=chat_id, text="Usage\n/lookup TELEGRAM_ID")
            return
        target_id = int(parts[1])
        code = get_code(db, target_id) if target_id < 2**63 else None
        text = f"Code for {target_id}\n<code>{code}</code>" if code else "No code found for that Telegram ID."
        api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", protect_content=True)
    elif command not in ("/string", "/lookup"):
        text = message["text"].strip()
        if offer_menu.handle_text(db, api, user_id, owner_id, text):
            return
        if not stock_menu.handle_text(db, api, user_id, owner_id, text):
            vanity_flow.handle_text(db, api, user_id, text)
