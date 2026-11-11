"""Everything that reads or writes rows lives here, so handlers never write SQL."""
from __future__ import annotations

import json
import sqlite3

from .database import Database
from .models import Listing, User

_COLS = "id, user_id, category, title, data, status, channel_msg_id, approved_by, created"


def _listing(row: sqlite3.Row | None) -> Listing | None:
    if row is None:
        return None
    return Listing(
        id=row["id"], user_id=row["user_id"], category=row["category"], title=row["title"],
        data=json.loads(row["data"]), status=row["status"], channel_msg_id=row["channel_msg_id"],
        approved_by=row["approved_by"], created=row["created"] or "",
    )


class ListingRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, category: str, title: str, data: dict, status: str = "pending",
               channel_msg_id: int | None = None) -> Listing:
        cur = self.db.execute(
            "INSERT INTO listings (user_id, category, title, data, status, channel_msg_id) VALUES (?,?,?,?,?,?)",
            (user_id, category, title, json.dumps(data), status, channel_msg_id))
        return self.get(cur.lastrowid)

    def get(self, listing_id: int) -> Listing | None:
        return _listing(self.db.query_one(f"SELECT {_COLS} FROM listings WHERE id=?", (listing_id,)))

    def find_by_channel_msg(self, msg_id: int) -> Listing | None:
        return _listing(self.db.query_one(f"SELECT {_COLS} FROM listings WHERE channel_msg_id=?", (msg_id,)))

    def save_data(self, listing_id: int, data: dict) -> None:
        self.db.execute("UPDATE listings SET data=? WHERE id=?", (json.dumps(data), listing_id))

    def set_channel_msg(self, listing_id: int, msg_id: int | None) -> None:
        self.db.execute("UPDATE listings SET channel_msg_id=? WHERE id=?", (msg_id, listing_id))

    def set_status(self, listing_id: int, status: str, approved_by: int | None = None) -> None:
        if approved_by is None:
            self.db.execute("UPDATE listings SET status=? WHERE id=?", (status, listing_id))
        else:
            self.db.execute("UPDATE listings SET status=?, approved_by=? WHERE id=?", (status, approved_by, listing_id))

    def transition(self, listing_id: int, from_status: str, to_status: str, *, owner_id: int | None = None,
                   approved_by: int | None = None) -> bool:
        """Move a listing between statuses atomically. False if it wasn't in `from_status` (or isn't the owner's).
        Two approvers tapping Yes at the same moment: only one of them gets True."""
        sql, args = "UPDATE listings SET status=?", [to_status]
        if approved_by is not None:
            sql, args = sql + ", approved_by=?", args + [approved_by]
        sql, args = sql + " WHERE id=? AND status=?", args + [listing_id, from_status]
        if owner_id is not None:
            sql, args = sql + " AND user_id=?", args + [owner_id]
        return self.db.execute(sql, args).rowcount > 0

    def for_user(self, user_id: int | None, status: str | None = None, limit: int = 500) -> list[Listing]:
        """A seller's listings (rejected ones hidden). user_id=None -> everyone's (admin view)."""
        sql, args = f"SELECT {_COLS} FROM listings WHERE status != 'rejected'", []
        if user_id is not None:
            sql, args = sql + " AND user_id=?", args + [user_id]
        if status:
            sql, args = sql + " AND status=?", args + [status]
        return [_listing(r) for r in self.db.query(sql + " ORDER BY id DESC LIMIT ?", args + [limit])]

    def pending(self) -> list[Listing]:
        return [_listing(r) for r in self.db.query(f"SELECT {_COLS} FROM listings WHERE status='pending' ORDER BY id")]

    def search(self, keyword: str, limit: int = 20) -> list[Listing]:
        like = f"%{keyword.lower()}%"
        rows = self.db.query(
            f"SELECT {_COLS} FROM listings WHERE lower(title) LIKE ? OR lower(data) LIKE ? ORDER BY id DESC LIMIT ?",
            (like, like, limit))
        return [_listing(r) for r in rows]

    def counts(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self.db.query("SELECT status, COUNT(*) AS n FROM listings GROUP BY status")}


class UserRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, user_id: int, username: str | None, name: str) -> None:
        self.db.execute(
            "INSERT INTO users (id, username, name) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET username=excluded.username, name=excluded.name",
            (user_id, (username or "").lower(), name))

    @staticmethod
    def _user(row: sqlite3.Row | None) -> User | None:
        return None if row is None else User(row["id"], row["username"] or "", row["name"] or "", bool(row["banned"]))

    def get(self, user_id: int) -> User | None:
        return self._user(self.db.query_one("SELECT * FROM users WHERE id=?", (user_id,)))

    def by_username(self, username: str) -> User | None:
        return self._user(self.db.query_one("SELECT * FROM users WHERE username=?", (username.lstrip("@").lower(),)))

    def set_banned(self, user_id: int, banned: bool) -> None:
        self.db.execute("UPDATE users SET banned=? WHERE id=?", (int(banned), user_id))

    def is_banned(self, user_id: int) -> bool:
        row = self.db.query_one("SELECT banned FROM users WHERE id=?", (user_id,))
        return bool(row and row["banned"])

    def count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) AS n FROM users")["n"]


class KV:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.query_one("SELECT v FROM kv WHERE k=?", (key,))
        return row["v"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, value))

