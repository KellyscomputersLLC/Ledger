# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
User accounts, roles, and the audit log for shared business books.

These live as tables *inside the (encrypted) book file*, so they are private
to the books and protected at rest along with everything else. The login
secrets themselves are NOT here -- those are the vault slots (see crypto.py).
A user's `username` is the label of their vault slot; this module holds the
matching role and account details, plus a record of what was done.

Everything here is created lazily: the tables do not exist until multi-user is
actually switched on for a set of books, so personal books and ordinary
single-owner business books are never touched.
"""

from datetime import datetime

from . import roles

# --- table definitions (created only when multi-user is switched on) -------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    role           TEXT NOT NULL,
    display_name   TEXT NOT NULL DEFAULT '',
    active         INTEGER NOT NULL DEFAULT 1,
    must_change_pw INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    created_by     TEXT NOT NULL DEFAULT '',
    pw_set_at      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    username TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
"""


def ensure_tables(conn):
    """Create the users and audit_log tables if they are not present. Called
    the first time multi-user is set up for a set of books. Also brings an
    older multi-user book up to date if a column was added in a later
    version."""
    conn.executescript(_SCHEMA)
    # Add columns that may be missing from a book made by an earlier version.
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(users)").fetchall()}
    if "must_change_pw" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_pw "
                     "INTEGER NOT NULL DEFAULT 0")
    if "pw_set_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pw_set_at "
                     "TEXT NOT NULL DEFAULT ''")
        # Existing users start their password-age clock from the first time the
        # book is opened under this version (i.e. now), not from their original
        # account-creation date -- so upgrading never immediately flags a
        # long-standing password as expired. Everyone gets the full window.
        conn.execute("UPDATE users SET pw_set_at = ? WHERE pw_set_at = ''",
                     (_now(),))
    conn.commit()


def _users_table_exists(conn):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    return row is not None


def migrate(conn):
    """Bring an existing multi-user book's tables up to date (add any columns
    introduced by a later version). A no-op for books that are not multi-user,
    so it is safe to call on every open without creating empty tables on
    personal or single-owner books."""
    if _users_table_exists(conn):
        ensure_tables(conn)


def multiuser_enabled(conn):
    """True if this set of books has been switched into multi-user mode --
    i.e. the users table exists and at least one user is registered. Used to
    decide between a simple passphrase prompt and a username login."""
    if not _users_table_exists(conn):
        return False
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return n > 0


# --- usernames -------------------------------------------------------------

_USERNAME_MAX = 32


def normalize_username(name):
    """Tidy a username so capitalisation and stray spaces do not matter:
    trimmed and lower-cased. Returns '' if there is nothing usable."""
    return (name or "").strip().lower()


def is_valid_username(name):
    """A username must be 1..32 characters of letters, digits, and the simple
    separators . _ - (after normalising). Kept conservative so a username is
    safe as a vault slot label and easy to type."""
    n = normalize_username(name)
    if not (1 <= len(n) <= _USERNAME_MAX):
        return False
    return all(ch.isalnum() or ch in "._-" for ch in n)


def _now():
    return datetime.now().isoformat(timespec="seconds")


# --- user records ----------------------------------------------------------

def create_user(conn, username, role, display_name="", created_by="",
                must_change=False):
    """Add a user record. The matching login secret (vault slot) is added
    separately by the caller, who holds the data key. Raises ValueError on a
    bad username or role, or if the username already exists.

    `must_change` marks the account so the person is required to set their own
    password the first time they sign in (used with a generated one-time
    password)."""
    ensure_tables(conn)
    uname = normalize_username(username)
    if not is_valid_username(uname):
        raise ValueError(
            "A username must be 1-32 characters: letters, numbers, and "
            ". _ - only.")
    if not roles.is_valid_role(role):
        raise ValueError("Unknown role: %r" % (role,))
    if get_user(conn, uname) is not None:
        raise ValueError("There is already a user named %r." % uname)
    conn.execute(
        "INSERT INTO users (username, role, display_name, active, "
        "must_change_pw, created_at, created_by, pw_set_at) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
        (uname, role, display_name or "", 1 if must_change else 0, _now(),
         normalize_username(created_by), _now()))
    conn.commit()
    return uname


def get_user(conn, username):
    """Return a user as a dict, or None. Safe to call before the tables
    exist (returns None)."""
    if not _users_table_exists(conn):
        return None
    row = conn.execute(
        "SELECT username, role, display_name, active, created_at, created_by, "
        "must_change_pw, pw_set_at FROM users WHERE username = ?",
        (normalize_username(username),)
    ).fetchone()
    if row is None:
        return None
    return {"username": row[0], "role": row[1], "display_name": row[2],
            "active": bool(row[3]), "created_at": row[4], "created_by": row[5],
            "must_change_pw": bool(row[6]), "pw_set_at": row[7]}


def list_users(conn, include_inactive=True):
    """All users, owners first then by name. Returns [] if multi-user is not
    set up."""
    if not _users_table_exists(conn):
        return []
    sql = ("SELECT username, role, display_name, active, created_at, "
           "created_by, must_change_pw, pw_set_at FROM users")
    if not include_inactive:
        sql += " WHERE active = 1"
    # Owners first, then managers, then staff, then alphabetical.
    sql += (" ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 "
            "WHEN 'staff' THEN 2 ELSE 3 END, username")
    out = []
    for row in conn.execute(sql).fetchall():
        out.append({"username": row[0], "role": row[1], "display_name": row[2],
                    "active": bool(row[3]), "created_at": row[4],
                    "created_by": row[5], "must_change_pw": bool(row[6]),
                    "pw_set_at": row[7]})
    return out


def count_owners(conn, active_only=True):
    """How many owners there are -- used to refuse removing or demoting the
    last one, so a set of books can never be left with no owner."""
    if not _users_table_exists(conn):
        return 0
    sql = "SELECT COUNT(*) FROM users WHERE role = 'owner'"
    if active_only:
        sql += " AND active = 1"
    return conn.execute(sql).fetchone()[0]


def set_role(conn, username, role):
    """Change a user's role. Raises ValueError on an unknown role or if this
    would remove the last active owner."""
    uname = normalize_username(username)
    if not roles.is_valid_role(role):
        raise ValueError("Unknown role: %r" % (role,))
    user = get_user(conn, uname)
    if user is None:
        raise ValueError("No such user: %r" % uname)
    if (user["role"] == roles.OWNER and role != roles.OWNER
            and user["active"] and count_owners(conn) <= 1):
        raise ValueError("This is the last owner; promote another owner "
                         "first.")
    conn.execute("UPDATE users SET role = ? WHERE username = ?",
                 (role, uname))
    conn.commit()


def set_active(conn, username, active):
    """Activate or deactivate a user. Deactivating does not remove their login
    secret -- the caller revokes that vault slot separately. Refuses to
    deactivate the last active owner."""
    uname = normalize_username(username)
    user = get_user(conn, uname)
    if user is None:
        raise ValueError("No such user: %r" % uname)
    if (not active and user["role"] == roles.OWNER and user["active"]
            and count_owners(conn) <= 1):
        raise ValueError("This is the last owner and cannot be deactivated.")
    conn.execute("UPDATE users SET active = ? WHERE username = ?",
                 (1 if active else 0, uname))
    conn.commit()


def set_must_change(conn, username, value):
    """Set or clear the 'must change password at next sign-in' flag."""
    uname = normalize_username(username)
    if get_user(conn, uname) is None:
        raise ValueError("No such user: %r" % uname)
    conn.execute("UPDATE users SET must_change_pw = ? WHERE username = ?",
                 (1 if value else 0, uname))
    conn.commit()


def stamp_password_set(conn, username, when=None):
    """Record that a user's password was (re)set just now. Called whenever a
    login slot's secret is created or changed, so the password-age clock used
    by the rotation rule starts fresh."""
    uname = normalize_username(username)
    conn.execute("UPDATE users SET pw_set_at = ? WHERE username = ?",
                 (when or _now(), uname))
    conn.commit()


def password_age_days(conn, username, now=None):
    """How many days old a user's password is, or None if it has never been
    stamped (so callers can treat 'unknown' as 'not expired')."""
    user = get_user(conn, normalize_username(username))
    if not user:
        return None
    stamp = user.get("pw_set_at") or ""
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return ((now or datetime.now()) - when).days


def set_display_name(conn, username, display_name):
    uname = normalize_username(username)
    if get_user(conn, uname) is None:
        raise ValueError("No such user: %r" % uname)
    conn.execute("UPDATE users SET display_name = ? WHERE username = ?",
                 (display_name or "", uname))
    conn.commit()


def delete_user(conn, username):
    """Remove a user record. The caller removes the matching vault slot
    separately. Refuses to delete the last active owner."""
    uname = normalize_username(username)
    user = get_user(conn, uname)
    if user is None:
        return False
    if user["role"] == roles.OWNER and count_owners(conn) <= 1:
        raise ValueError("This is the last owner and cannot be removed.")
    conn.execute("DELETE FROM users WHERE username = ?", (uname,))
    conn.commit()
    return True


# --- audit log -------------------------------------------------------------

def log_action(conn, username, action, detail=""):
    """Record that `username` did `action` (with optional detail). Committed
    immediately, so the record survives even if a later step fails.

    Honest note: this records actions taken *through the application*. On a
    single shared computer it is an accountability aid among cooperating
    users, not tamper-proof evidence -- someone who bypasses the app to reach
    the data directly will not appear here. The host/client model is what
    makes the log authoritative, because there the actions happen on the host.
    """
    ensure_tables(conn)
    conn.execute(
        "INSERT INTO audit_log (at, username, action, detail) "
        "VALUES (?, ?, ?, ?)",
        (_now(), normalize_username(username), action, detail or ""))
    conn.commit()


def list_audit(conn, limit=200, newest_first=True):
    """Recent audit entries as dicts. Returns [] if the log does not exist."""
    if not _users_table_exists(conn):
        return []
    order = "DESC" if newest_first else "ASC"
    rows = conn.execute(
        "SELECT id, at, username, action, detail FROM audit_log "
        "ORDER BY id " + order + " LIMIT ?", (int(limit),)
    ).fetchall()
    return [{"id": r[0], "at": r[1], "username": r[2], "action": r[3],
             "detail": r[4]} for r in rows]
