# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Standalone test of the multi-user foundation: roles.py + users.py.
No tkinter, no networking. Run from the folder containing `ledger/`:

    python3 test_users_roles.py
"""
import sqlite3
import os
import sys
import tempfile

from ledger import roles, users, database, crypto, seed

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


print("1. Role matrix: Owner can everything, Staff is limited, unknown=nothing")
check(all(roles.can(roles.OWNER, a) for a in roles.ALL_ACTIONS),
      "owner can do every action")
check(roles.can(roles.STAFF, roles.RECORD_ENTRY),
      "staff can record entries")
check(not roles.can(roles.STAFF, roles.VOID_ENTRY),
      "staff cannot void entries")
check(not roles.can(roles.STAFF, roles.MANAGE_USERS),
      "staff cannot manage users")
check(roles.can(roles.MANAGER, roles.RECONCILE)
      and not roles.can(roles.MANAGER, roles.MANAGE_USERS),
      "manager reconciles but cannot manage users")
check(not roles.can(roles.MANAGER, roles.RESTORE_BACKUP),
      "manager cannot restore backups")
check(not roles.can("nonsense", roles.VIEW_REPORTS),
      "an unknown role can do nothing (fails closed)")

print("2. A fresh book is NOT multi-user and the tables don't exist yet")
plain = os.path.join(tempfile.mkdtemp(), "books.db")
conn = database.connect(plain)
database.init_db(conn)
seed.seed_accounts(conn)
conn.commit()
check(not users.multiuser_enabled(conn), "multiuser_enabled is False")
check(users.get_user(conn, "anyone") is None, "get_user returns None")
check(users.list_users(conn) == [], "list_users is empty")
check(users.list_audit(conn) == [], "list_audit is empty")

print("3. Creating the first users switches multi-user on")
users.create_user(conn, "Ben", roles.OWNER, display_name="Ben K",
                  created_by="")
check(users.multiuser_enabled(conn), "multiuser_enabled is True after first user")
users.create_user(conn, "manny", roles.MANAGER, created_by="ben")
users.create_user(conn, "sam", roles.STAFF, created_by="ben")
check(users.get_user(conn, "BEN")["role"] == roles.OWNER,
      "username is case-insensitive (BEN == ben), owner role stored")
names = [u["username"] for u in users.list_users(conn)]
check(names[0] == "ben", "owners are listed first")
check(set(names) == {"ben", "manny", "sam"}, "all three users present")

print("4. Validation: bad usernames, bad roles, duplicates are refused")
for bad in ("", "  ", "a b", "no/slash", "x" * 33):
    try:
        users.create_user(conn, bad, roles.STAFF); check(False, "rejected %r" % bad)
    except ValueError:
        check(True, "bad username refused: %r" % bad)
try:
    users.create_user(conn, "newbie", "supervisor"); check(False, "bad role")
except ValueError:
    check(True, "unknown role refused")
try:
    users.create_user(conn, "sam", roles.STAFF); check(False, "dup refused")
except ValueError:
    check(True, "duplicate username refused")

print("5. The last owner is protected")
try:
    users.set_role(conn, "ben", roles.STAFF); check(False, "demote refused")
except ValueError:
    check(True, "cannot demote the only owner")
try:
    users.set_active(conn, "ben", False); check(False, "deactivate refused")
except ValueError:
    check(True, "cannot deactivate the only owner")
try:
    users.delete_user(conn, "ben"); check(False, "delete refused")
except ValueError:
    check(True, "cannot delete the only owner")
# With a second owner, the first can be changed.
users.set_role(conn, "manny", roles.OWNER)
check(users.count_owners(conn) == 2, "now two owners")
users.set_role(conn, "ben", roles.STAFF)
check(users.get_user(conn, "ben")["role"] == roles.STAFF,
      "former owner can be demoted once another owner exists")

print("6. Deactivate and delete non-owners")
users.set_active(conn, "sam", False)
check(users.get_user(conn, "sam")["active"] is False, "sam deactivated")
check([u["username"] for u in users.list_users(conn, include_inactive=False)]
      == [u for u in ["manny", "ben"] if True] or
      "sam" not in [u["username"]
                    for u in users.list_users(conn, include_inactive=False)],
      "inactive user hidden when include_inactive=False")
check(users.delete_user(conn, "sam") is True, "deleted a non-owner")
check(users.get_user(conn, "sam") is None, "sam is gone")

print("7. Audit log records actions, newest first")
users.log_action(conn, "ben", "record_entry", "Invoice #100")
users.log_action(conn, "manny", "void_entry", "Entry 7")
entries = users.list_audit(conn)
check(len(entries) >= 2, "audit entries recorded")
check(entries[0]["action"] == "void_entry", "newest-first ordering")
check(entries[0]["username"] == "manny", "records the acting user")
conn.close()

print("8. It all lives in the ENCRYPTED book and survives a reopen")
d = tempfile.mkdtemp()
enc = os.path.join(d, "secure.db")
v, _ = crypto.create_vault("owner passphrase")
key = crypto.unlock(v, "owner passphrase")
c = database.connect(enc, data_key=key)
database.init_db(c)
seed.seed_accounts(c)
users.create_user(c, "owner", roles.OWNER)
users.log_action(c, "owner", "create_user", "added owner")
c.commit()
c.close()
# Prove the usernames are NOT sitting in the clear on disk.
with open(enc, "rb") as fh:
    raw = fh.read()
check(crypto.is_encrypted_db_file(enc), "book is encrypted at rest")
check(b"audit_log" not in raw and b"owner passphrase" not in raw,
      "user/audit data is not readable in the encrypted file")
c = database.connect(enc, data_key=key)
check(users.multiuser_enabled(c), "multi-user state persisted across reopen")
check(users.get_user(c, "owner")["role"] == roles.OWNER, "owner persisted")
check(len(users.list_audit(c)) == 1, "audit entry persisted")
c.close()

print("8b. An older book missing the pw_set_at column migrates on open")
mc = sqlite3.connect(":memory:")
# A users table exactly as an earlier version created it (no pw_set_at).
mc.executescript(
    "CREATE TABLE users (username TEXT PRIMARY KEY, role TEXT NOT NULL, "
    "display_name TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, "
    "must_change_pw INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, "
    "created_by TEXT NOT NULL DEFAULT '');"
    "INSERT INTO users (username, role, created_at) "
    "VALUES ('owner','owner','2026-01-01T00:00:00');")
users.migrate(mc)
check(users.get_user(mc, "owner") is not None,
      "get_user works after migrating an older book")
check(users.get_user(mc, "owner")["pw_set_at"] not in ("", None)
      and users.get_user(mc, "owner")["pw_set_at"] != "2026-01-01T00:00:00",
      "pw_set_at is set to now on migration, not the old creation date")
check(users.password_age_days(mc, "owner") == 0,
      "an upgraded user's password is treated as fresh (full window)")
check(len(users.list_users(mc)) == 1, "list_users works after migration")
mc.close()
# migrate() must not create tables on a non-multi-user (personal) book.
pc = sqlite3.connect(":memory:")
users.migrate(pc)
check(not users.multiuser_enabled(pc),
      "migrate() leaves a personal book without user tables")
pc.close()

print("9. Enforcement policy lock: exact capabilities the GUI gates on")
# Owner can do everything.
check(all(roles.can(roles.OWNER, a) for a in roles.ALL_ACTIONS),
      "owner: all actions allowed")
# Manager: day-to-day, but not restore / protection / users.
mgr_yes = [roles.RECORD_ENTRY, roles.VOID_ENTRY, roles.VIEW_JOURNAL,
           roles.VIEW_REPORTS, roles.RECONCILE, roles.MANAGE_ACCOUNTS,
           roles.EDIT_PROFILE, roles.MAKE_BACKUP, roles.VIEW_AUDIT]
mgr_no = [roles.RESTORE_BACKUP, roles.MANAGE_PROTECTION, roles.MANAGE_USERS]
check(all(roles.can(roles.MANAGER, a) for a in mgr_yes),
      "manager: day-to-day actions allowed")
check(not any(roles.can(roles.MANAGER, a) for a in mgr_no),
      "manager: NOT restore, protection, or user management")
# Staff: record + view only.
staff_yes = [roles.RECORD_ENTRY, roles.VIEW_JOURNAL, roles.VIEW_REPORTS]
staff_no = [roles.VOID_ENTRY, roles.RECONCILE, roles.MANAGE_ACCOUNTS,
            roles.EDIT_PROFILE, roles.MAKE_BACKUP, roles.RESTORE_BACKUP,
            roles.MANAGE_PROTECTION, roles.MANAGE_USERS, roles.VIEW_AUDIT]
check(all(roles.can(roles.STAFF, a) for a in staff_yes),
      "staff: record and view allowed")
check(not any(roles.can(roles.STAFF, a) for a in staff_no),
      "staff: NOT void, reconcile, accounts, profile, backup, restore, "
      "protection, users, or audit")

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All multi-user foundation checks passed.")
