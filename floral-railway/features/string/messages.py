import html

WELCOME_KEYBOARD = {"inline_keyboard": [[
    {"text": "Active Listings", "callback_data": "active_listings"},
    {"text": "Notifications", "callback_data": "notifications"},
]]}

HELP = (
    "If someone DMs you claiming to be @Floral, ask them to tell you your "
    "code. Compare it with the current code in this bot. "
    "If it’s missing or different, stop the deal.\n\n"
    "Keep your code private. @Floral can look it up using your Telegram ID "
    "and will never ask you to send the code back.\n\n"
    "If you’ve shared it by mistake, tap Refresh code. "
    "You can refresh it once every five minutes."
)


def emoji_markup(sticker):
    if not sticker or not sticker.get("custom_emoji_id"):
        return ""
    emoji_id = html.escape(sticker["custom_emoji_id"])
    fallback = html.escape(sticker.get("emoji") or "✦")
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> '


def welcome(user, listing_emojis=()):
    username = user.get("username") or user["first_name"]
    urls, evaluate = (emoji_markup(sticker) for sticker in listing_emojis) if listing_emojis else ("", "")
    return {"html": (
        '<table><tr><td align="center">'
        f'Welcome, {html.escape(username)}<br><br>'
        '<b>Where would you like to list?</b>'
        '</td></tr></table>'
        '<tg-button-row align="center">'
        f'<tg-button type="callback_data" style="primary" data="evaluate">{evaluate}Evaluate</tg-button>'
        f'<tg-button type="callback_data" style="primary" data="evaluate_urls">{urls}Evaluate URLs</tg-button>'
        '</tg-button-row>'
    )}


EVALUATE_CATEGORIES = {
    "discord_username": "Discord Usernames",
    "discord_badges": "Discord Badged Accounts",
    "telegram_username": "Telegram Usernames",
    "telegram_gift": "Telegram Gifts",
    "tiktok_username": "TikTok Usernames",
}


def evaluate_menu(listing_emojis):
    icon = emoji_markup(listing_emojis[1]) if listing_emojis else ""
    title = f"{icon}<b>Evaluate</b>"
    buttons = [
        f'<tg-button type="callback_data" style="primary" data="eval:{key}">{label}</tg-button>'
        for key, label in EVALUATE_CATEGORIES.items()
    ]
    buttons.append('<tg-button type="callback_data" data="urls_back">Back</tg-button>')
    rows = "".join(
        '<tg-button-row align="center">' + "".join(buttons[index:index + 2]) + '</tg-button-row>'
        for index in range(0, len(buttons), 2)
    )
    return {"html": f'<table><tr><td align="center">{title}</td></tr></table>{rows}'}


def urls_menu(listing_emojis):
    icon = emoji_markup(listing_emojis[0]) if listing_emojis else ""
    return {"html": (
        '<table><tr><td align="center">'
        f'{icon}<b>Evaluation URLs</b>'
        '</td></tr></table>'
        '<tg-button-row align="center">'
        '<tg-button type="callback_data" style="primary" data="discord_vanity">Discord Vanity</tg-button>'
        '</tg-button-row>'
        '<tg-button-row align="center">'
        '<tg-button type="callback_data" data="urls_back">Back</tg-button>'
        '</tg-button-row>'
    )}


def profile(user, code):
    name = " ".join(filter(None, (user["first_name"], user.get("last_name"))))
    username = "@" + user["username"] if user.get("username") else "None"
    return {"html": (
        f'<p>Display name · {html.escape(name)}<br>'
        f'Username · {html.escape(username)}<br>'
        f'Telegram ID · <code>{user["id"]}</code></p>'
        f'<p><b>Code:</b> <code>{html.escape(code)}</code></p>'
        '<tg-button-row align="center">'
        '<tg-button type="callback_data" style="primary" data="refresh">Refresh code</tg-button>'
        '</tg-button-row>'
        '<tg-button-row align="center">'
        '<tg-button type="callback_data" style="primary" data="help">How it works</tg-button>'
        '</tg-button-row>'
    )}
