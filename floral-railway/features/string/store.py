import secrets
import sqlite3
import time

COOLDOWN = 300
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code():
    return "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(5))
        for _ in range(5)
    )


def open_database(path):
    db = sqlite3.connect(path)
    db.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            user_id INTEGER PRIMARY KEY,
            code TEXT NOT NULL,
            refreshed_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    return db


def get_code(db, user_id):
    row = db.execute("SELECT code FROM codes WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row else None


def ensure_code(db, user_id):
    code = get_code(db, user_id)
    if code is not None:
        return code
    with db:
        db.execute(
            "INSERT OR IGNORE INTO codes (user_id, code) VALUES (?, ?)",
            (user_id, generate_code()),
        )
    return get_code(db, user_id)


def refresh_code(db, user_id):
    now = int(time.time())
    with db:
        result = db.execute(
            """UPDATE codes SET code = ?, refreshed_at = ?
               WHERE user_id = ? AND refreshed_at <= ?""",
            (generate_code(), now, user_id, now - COOLDOWN),
        )
        code, refreshed_at = db.execute(
            "SELECT code, refreshed_at FROM codes WHERE user_id = ?", (user_id,)
        ).fetchone()
    return code, 0 if result.rowcount else max(1, COOLDOWN - (now - refreshed_at))
