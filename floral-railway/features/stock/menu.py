import re

from features.vanity import flow, publishing

PAGE_SIZE = 8
STATUS = {
    "approved": "🟢 Approved", "pending": "⏳ Pending", "denied": "❌ Denied",
    "sold": "✅ Sold", "delisted": "🗑 Delisted",
}
FIELDS = {"bin": "BIN", "offer": "Current Offer", "notes": "Notes"}
BACK = ("Back", "urls_back")


def setup(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS stock_edits (
            user_id INTEGER PRIMARY KEY,
            listing_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)


def listing(db, user_id, owner_id, listing_id):
    return db.execute(
        """SELECT id, vanity, bin, offer, notes, status, published_at, category
           FROM vanity_reviews WHERE id = ? AND (user_id = ? OR ?)""",
        (listing_id, user_id, user_id == owner_id),
    ).fetchone()


def editable(row, user_id, owner_id):
    return row[5] == "approved" or (row[5] == "pending" and user_id == owner_id)


def render(api, user_id, message_id, text, rows):
    keyboard = {"inline_keyboard": [
        [{"text": label, "callback_data": action} for label, action in row]
        for row in rows
    ]}
    api("editMessageText", chat_id=user_id, message_id=message_id,
        rich_message=flow.rich_content(text), reply_markup=keyboard)


def show(db, api, user_id, owner_id, message_id, page, notice=""):
    if user_id == owner_id:
        scope = "status IN (?, ?)"
        params = ("pending", "approved")
    else:
        scope = "user_id = ? AND status != ?"
        params = (user_id, "delisted")
    total, = db.execute(f"SELECT count(*) FROM vanity_reviews WHERE {scope}", params).fetchone()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages - 1)
    rows = db.execute(
        f"""SELECT id, vanity, status FROM vanity_reviews WHERE {scope}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        (*params, PAGE_SIZE, page * PAGE_SIZE),
    ).fetchall()
    buttons = [[(f"{STATUS[status]} · #{item} · {vanity.splitlines()[0]}", f"stock:view:{item}:{page}")]
               for item, vanity, status in rows]
    if pages > 1:
        buttons.append([("‹", f"stock:page:{(page - 1) % pages}"),
                        ("›", f"stock:page:{(page + 1) % pages}")])
    title = f"{'All stock' if user_id == owner_id else 'Your stock'} · {total} listings"
    if pages > 1:
        title += f"\nPage {page + 1} / {pages}"
    if not rows:
        title += "\n\nNo listings yet."
    render(api, user_id, message_id, f"{notice}\n\n{title}" if notice else title, [*buttons, [BACK]])


def view(api, user_id, owner_id, message_id, row, page):
    item, vanity, bin_price, offer, notes, status, published_at, category = row
    text = f"Listing #{item}\n\n{flow.summary(vanity, bin_price, offer, notes, category)}\n\nStatus: {STATUS[status]}"
    if published_at:
        text += "\nPublished to the channel"
    buttons = []
    if editable(row, user_id, owner_id):
        buttons.extend([
            [("Edit BIN", f"stock:bin:{item}:{page}"), ("Edit C/O", f"stock:offer:{item}:{page}")],
            [("Edit notes", f"stock:notes:{item}:{page}")],
        ])
    if status == "approved":
        buttons.append([("Mark sold", f"stock:sold:{item}:{page}"), ("Delist", f"stock:remove:{item}:{page}")])
    elif status == "pending":
        buttons.append([("Withdraw", f"stock:remove:{item}:{page}")])
    buttons.append([("Back", f"stock:page:{page}")])
    render(api, user_id, message_id, text, buttons)


def clear_edit(db, user_id):
    with db:
        db.execute("DELETE FROM stock_edits WHERE user_id = ?", (user_id,))


def handle_button(db, api, user_id, owner_id, callback):
    action = callback["data"]
    mid = callback["message"]["message_id"]
    answer = {"callback_query_id": callback["id"]}
    if action == "active_listings":
        api("answerCallbackQuery", **answer)
        clear_edit(db, user_id)
        show(db, api, user_id, owner_id, mid, 0)
        return
    match = re.fullmatch(r"stock:([a-z]+):([0-9]{1,18})(?::([0-9]{1,9}))?", action)
    if not match:
        api("answerCallbackQuery", **answer)
        return
    verb, number, page = match[1], int(match[2]), int(match[3] or 0)
    if verb == "page":
        api("answerCallbackQuery", **answer)
        clear_edit(db, user_id)
        show(db, api, user_id, owner_id, mid, number)
        return
    row = listing(db, user_id, owner_id, number)
    if not row or row[5] == "delisted":
        api("answerCallbackQuery", **answer, text="Listing not found.", show_alert=True)
        return
    api("answerCallbackQuery", **answer)
    if verb == "view":
        clear_edit(db, user_id)
    elif verb in FIELDS and editable(row, user_id, owner_id):
        minimum = flow.MIN_BIN_CENTS // 100 if row[-1] == "discord_vanity" else 0.01
        with db:
            db.execute("REPLACE INTO stock_edits VALUES (?, ?, ?, ?)", (user_id, number, verb, mid))
        examples = {
            "bin": f"Enter at least ${minimum}, or type Taking Offers.",
            "offer": "Enter an amount, or type None.",
            "notes": "Enter new notes, or type None to clear them.",
        }
        render(api, user_id, mid, f"New {FIELDS[verb]}?\n\n{examples[verb]}",
               [[("Cancel", f"stock:view:{number}:{page}")]])
        return
    elif verb in ("sold", "remove"):
        label = "Mark sold" if verb == "sold" else "Delist"
        render(api, user_id, mid, f"{label} listing #{number}?",
               [[("Confirm", f"stock:{verb}confirm:{number}:{page}"),
                 ("Cancel", f"stock:view:{number}:{page}")]])
        return
    elif verb in ("soldconfirm", "removeconfirm"):
        sold = verb == "soldconfirm"
        if row[5] == "approved" or (not sold and row[5] == "pending"):
            try:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    notice = "" if sold else publishing.remove_listing(db, api, number)
                    db.execute("UPDATE vanity_reviews SET status = ? WHERE id = ? AND status = ?",
                               ("sold" if sold else "delisted", number, row[5]))
            except Exception as error:
                if sold:
                    raise
                print(f"Delisting channel update failed ({type(error).__name__}).", flush=True)
                render(api, user_id, mid, "Could not update the channel post. The listing is still in stock.",
                       [[("Retry", f"stock:removeconfirm:{number}:{page}"),
                         ("Back", f"stock:view:{number}:{page}")]])
                return
            if not sold:
                show(db, api, user_id, owner_id, mid, page, f"Listing #{number} delisted. {notice}".strip())
                return
            row = listing(db, user_id, owner_id, number)
    view(api, user_id, owner_id, mid, row, page)


def handle_text(db, api, user_id, owner_id, text):
    edit = db.execute("SELECT listing_id, field, message_id FROM stock_edits WHERE user_id = ?", (user_id,)).fetchone()
    if not edit:
        return False
    item, field, mid = edit
    row = listing(db, user_id, owner_id, item)
    if not row or not editable(row, user_id, owner_id):
        clear_edit(db, user_id)
        return True
    if field == "notes":
        value = "" if text.lower() == "none" else text if len(text) <= 1000 else None
    elif field == "bin" and text.lower() == "taking offers":
        value = "Taking Offers"
    elif field == "offer" and text.lower() == "none":
        value = "None"
    else:
        cents = flow.amount(text)
        minimum = (flow.MIN_BIN_CENTS if row[-1] == "discord_vanity" else 1) if field == "bin" else 0
        value = None if cents is None or cents < minimum else flow.format_amount(cents) if cents else "None"
    if value is None:
        api("sendMessage", chat_id=user_id, text=f"Enter a valid {FIELDS[field]} value and try again.")
        return True
    with db:
        db.execute(f"UPDATE vanity_reviews SET {field} = ? WHERE id = ? AND status = ?", (value, item, row[5]))
        db.execute("DELETE FROM stock_edits WHERE user_id = ?", (user_id,))
    view(api, user_id, owner_id, mid, listing(db, user_id, owner_id, item), 0)
    return True
