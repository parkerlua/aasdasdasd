"""SQLite connection plus versioned migrations (PRAGMA user_version).

Migrations only ever add things, and each one checks what already exists, so a database made by the
very first version of the bot (no version number at all) upgrades cleanly.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

log = logging.getLogger(__name__)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _m1_base(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, category TEXT NOT NULL,
        title TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    _add_column(conn, "listings", "channel_msg_id", "INTEGER")
    conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")


def _m2_approvals_and_bans(conn: sqlite3.Connection) -> None:
    _add_column(conn, "listings", "approved_by", "INTEGER")
    _add_column(conn, "users", "banned", "INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_channel_msg ON listings(channel_msg_id)")


def _m3_drop_dwc(conn: sqlite3.Connection) -> None:
    """The DWC feature was removed. Drop its tables if an earlier build created them (the number stays reserved)."""
    for table in ("dwc_entries", "dwc_authorized", "dwc_appeals"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_m1_base, _m2_approvals_and_bans, _m3_drop_dwc]


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for version, migration in enumerate(MIGRATIONS, start=1):
                if version > current:
                    log.info("database: applying migration %d (%s)", version, migration.__name__)
                    migration(self._conn)
                    self._conn.execute(f"PRAGMA user_version = {version}")
            self._conn.commit()

    @property
    def version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def backup_to(self, dest: str | Path) -> None:
        """A consistent copy of the live database (safe while the bot is running)."""
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._conn.backup(target)
            finally:
                target.close()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
