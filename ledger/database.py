# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Database layer for Ledger.

Handles the SQLite connection and schema creation. The schema enforces
double-entry bookkeeping rules at the database level wherever possible:
every journal line is either a debit or a credit (never both, never
negative), which keeps the books trustworthy even if application code
has a bug.
"""

import sqlite3
import os
from datetime import datetime

from . import paths
from . import crypto

# Where the ledger lives by default. paths.default_db_path() returns
# the right per-platform location (a dot-folder on Linux, the AppData
# area on Windows), so this works the same from one folder on either
# operating system.
DEFAULT_DB_PATH = paths.default_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY,
    code           TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL
                   CHECK (type IN ('ASSET','LIABILITY','EQUITY','INCOME','EXPENSE')),
    normal_balance TEXT NOT NULL
                   CHECK (normal_balance IN ('DEBIT','CREDIT')),
    active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,                -- ISO format YYYY-MM-DD
    description TEXT NOT NULL,
    reference   TEXT,                         -- optional: invoice #, check #, etc.
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id         INTEGER PRIMARY KEY,
    entry_id   INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    debit      REAL NOT NULL DEFAULT 0,
    credit     REAL NOT NULL DEFAULT 0,
    -- A line is strictly a debit or a credit, never both, never negative:
    CHECK (debit  >= 0),
    CHECK (credit >= 0),
    CHECK (NOT (debit > 0 AND credit > 0)),
    CHECK (debit > 0 OR credit > 0)
);

CREATE INDEX IF NOT EXISTS idx_lines_entry   ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS idx_lines_account ON journal_lines(account_id);
CREATE INDEX IF NOT EXISTS idx_entries_date  ON journal_entries(date);

-- The business profile is the owner's own information (name, address,
-- contact, tagline). It is stored here, inside the data file, so it
-- belongs to THIS set of books only -- if someone else uses Ledger
-- with their own data file, they enter their own profile and never see
-- this one. There is only ever a single row, kept at id = 1.
--
-- `kind` records whether this set of books is for a business or for
-- personal use. It only changes the wording the program shows (so a
-- personal user sees "Your name" instead of "Business name"); the
-- accounts and the bookkeeping are identical either way.
CREATE TABLE IF NOT EXISTS business_profile (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    name      TEXT NOT NULL DEFAULT '',
    address   TEXT NOT NULL DEFAULT '',
    contact   TEXT NOT NULL DEFAULT '',
    tagline   TEXT NOT NULL DEFAULT '',
    kind      TEXT NOT NULL DEFAULT 'business'
              CHECK (kind IN ('business','personal'))
);
"""


# --- encrypted books: an in-memory database mirrored to an encrypted file --
#
# An encrypted ("Protected") book is never written to disk in the clear. It
# is held entirely in this process's memory for the open session, loaded from
# its encrypted file when opened, and written back -- encrypted -- on every
# commit. This needs SQLite's serialize/deserialize, which arrived in Python
# 3.11. If we are on an older Python we must NOT pretend: refuse clearly so a
# protected book is never created here that this same machine couldn't reopen.

_INMEM_OK = (hasattr(sqlite3.Connection, "serialize")
             and hasattr(sqlite3.Connection, "deserialize"))


def _require_inmem():
    if not _INMEM_OK:
        raise RuntimeError(
            "Encrypted books need Python 3.11 or newer than the version "
            "running Ledger here. Your data is safe; open the book on a "
            "computer with an up-to-date Python (or install a newer one).")


class EncryptedConnection(sqlite3.Connection):
    """A SQLite connection that lives entirely in memory but mirrors its
    committed state, encrypted, to a file on disk.

    The plaintext database is never written to disk: it exists only in memory
    for as long as the book is open. Each commit re-writes the on-disk file
    as one encrypted, authenticated blob. The data key is held only in memory
    and is never stored anywhere.

    Apart from that automatic encrypted save on commit, this behaves exactly
    like an ordinary SQLite connection, so the rest of the program does not
    have to know or care that a book is encrypted.
    """

    # Set once, immediately after construction by connect().
    _enc_path = None
    _enc_key = None

    def _bind(self, db_path, data_key):
        self._enc_path = db_path
        self._enc_key = data_key

    def _flush_encrypted(self):
        """Write the current database to its encrypted file. Raises on
        failure so a save problem is never silently swallowed -- a lost write
        must be visible. The in-memory database stays the source of truth, so
        a failed flush loses nothing in memory and the next commit retries."""
        if self._enc_path is None or self._enc_key is None:
            raise RuntimeError(
                "This encrypted book is missing its key or file path.")
        raw = self.serialize()
        crypto.save_encrypted_db(self._enc_path, self._enc_key, raw)

    def commit(self):
        # Commit in memory first, THEN persist the encrypted copy, so the
        # disk file only ever reflects committed state.
        super().commit()
        self._flush_encrypted()


def connect(db_path=DEFAULT_DB_PATH, data_key=None, allow_threads=False):
    """Open a connection to a ledger database, creating it if needed.

    With no `data_key`, this is an ordinary on-disk SQLite database -- an
    unencrypted ("Open") book -- exactly as before.

    With a `data_key`, the book is encrypted at rest: it is held in memory
    for the session, loaded from its encrypted file on disk if one already
    exists, and written back (encrypted) on every commit. The plaintext data
    never touches the disk.

    With `allow_threads=True`, the connection may be used from more than one
    thread. This is for the host server, where a background thread serves
    requests: SQLite normally forbids cross-thread use, but the host serializes
    every database access through a single lock, so it is safe to relax that
    check here. Ordinary single-window use leaves this off.
    """
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    same_thread = not allow_threads
    if data_key is None:
        # Unencrypted book: on-disk SQLite, unchanged behaviour.
        conn = sqlite3.connect(db_path, check_same_thread=same_thread)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Encrypted book: an in-memory database mirrored to an encrypted file.
    _require_inmem()
    conn = sqlite3.connect(":memory:", factory=EncryptedConnection,
                           check_same_thread=same_thread)
    conn._bind(db_path, data_key)
    conn.row_factory = sqlite3.Row
    if os.path.exists(db_path):
        # Load the existing encrypted book into memory before anything else.
        raw = crypto.load_encrypted_db(db_path, data_key)
        conn.deserialize(raw)
    # foreign_keys is a per-connection pragma (not stored in the file), so it
    # is set after any deserialize.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def encrypt_file_in_place(db_path, data_key):
    """Turn an existing *plaintext* database file into our encrypted form, in
    place. Used when protecting a freshly created (or existing) book.

    This is the one irreversible moment where the only copy of the data is
    rewritten, so it is done with care: the encrypted copy is written to a
    temp file, then read back and decrypted and checked byte-for-byte against
    the original BEFORE the plaintext file is replaced. A readable file is
    never traded for an unreadable one. The caller MUST have closed any
    connection to the file first.
    """
    _require_inmem()   # never make a file this machine could not reopen
    with open(db_path, "rb") as f:
        raw = f.read()
    tmp = db_path + ".enc.tmp"
    blob = crypto.encrypt_db_bytes(data_key, raw)
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    if crypto.load_encrypted_db(tmp, data_key) != raw:
        os.remove(tmp)
        raise RuntimeError(
            "Safety check failed while encrypting this book; the original "
            "file was left untouched.")
    os.replace(tmp, db_path)
    return db_path


def decrypt_file_in_place(db_path, data_key):
    """Turn an encrypted database file back into a plaintext SQLite file, in
    place and atomically. Used when turning protection off. The decryption is
    authenticated, so a successful decrypt is exactly the original bytes. The
    caller MUST have closed any connection to the file first."""
    raw = crypto.load_encrypted_db(db_path, data_key)
    tmp = db_path + ".dec.tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, db_path)
    return db_path


def init_db(conn):
    """Create all tables and indexes if they do not yet exist."""
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    """
    Bring an older data file up to date without touching its contents.

    Earlier versions of Ledger had no 'kind' on the business profile.
    Files created back then still open fine; we just add the column the
    first time they are opened, defaulting to 'business' so nothing about
    an existing ledger appears to change. Safe to run on every open.
    """
    existing = {row["name"] for row in
                conn.execute("PRAGMA table_info(business_profile)").fetchall()}
    if "kind" not in existing:
        conn.execute(
            "ALTER TABLE business_profile "
            "ADD COLUMN kind TEXT NOT NULL DEFAULT 'business'"
        )


def now_iso():
    """Current timestamp as an ISO string (used for created_at)."""
    return datetime.now().isoformat(timespec="seconds")


def get_setting(conn, key, default=None):
    """Read a per-book setting (a small key/value stored inside this set of
    books). Returns `default` if the key has never been set."""
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    except Exception:
        return default
    return row["value"] if row is not None else default


def set_setting(conn, key, value):
    """Write a per-book setting. Travels with this set of books and is gone
    if the books are deleted, so it only ever affects this one set."""
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
