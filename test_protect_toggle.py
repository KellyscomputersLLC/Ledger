# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Reproduces the data-layer choreography of the Backup tab's Protect /
Unprotect controls, plus the interruption-recovery that _open_database does.
No tkinter needed (run test_gui.py on a desktop for the real dialogs).

Covers:
  * turn protection ON for an existing Open book that already has real data,
  * turn it OFF again,
  * data integrity across an on -> off -> on -> off round trip,
  * recovery from an interrupted turn-ON (vault saved, file still plaintext),
  * recovery from an interrupted turn-OFF (file decrypted, vault not removed).

Run from the folder containing `ledger/`:
    python3 test_protect_toggle.py
"""
import os
import sys
import tempfile

from ledger import crypto, database, seed, profile

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


def open_book(path):
    """A new Open (plaintext) book with seeded accounts and one real entry."""
    conn = database.connect(path)
    database.init_db(conn)
    seed.seed_accounts(conn)
    profile.save_profile(conn, name="Test Co", kind="personal")
    conn.execute("INSERT INTO journal_entries (date, description, created_at) "
                 "VALUES ('2025-05-05', 'Real money', '2025-05-05T00:00:00')")
    conn.commit()
    return conn


def turn_on(conn, path, secret):
    """Mirror _protect_existing_book(): vault, key, then encrypt at rest."""
    vault, _recovery = crypto.create_vault(secret)
    crypto.save_vault(path, vault)
    key = crypto.unlock(vault, secret)
    # _encrypt_open_book_at_rest choreography:
    conn.commit()
    conn.close()
    database.encrypt_file_in_place(path, key)
    return database.connect(path, data_key=key), key


def turn_off(conn, path, key):
    """Mirror _unprotect_existing_book(): decrypt FIRST, then drop the vault."""
    conn.commit()
    conn.close()
    database.decrypt_file_in_place(path, key)
    crypto.delete_vault(path)
    return database.connect(path)


def open_database_like(path, key_for_protected=None):
    """Mirror the relevant branch of _open_database, including the stray-vault
    recovery: if a vault sits beside a plaintext file, drop it and open Open."""
    if crypto.is_protected(path):
        if not crypto.is_encrypted_db_file(path):
            crypto.delete_vault(path)              # interrupted toggle: recover
            return database.connect(path)
        return database.connect(path, data_key=key_for_protected)
    return database.connect(path)


tmp = tempfile.mkdtemp()


print("1. Turn protection ON for an existing Open book with real data")
path = os.path.join(tmp, "books.db")
conn = open_book(path)
check(not crypto.is_protected(path), "starts Open (no vault)")
before = conn.execute(
    "SELECT description FROM journal_entries").fetchone()[0]
conn, key = turn_on(conn, path, "my passphrase")
check(crypto.is_protected(path), "now Protected (vault present)")
check(crypto.is_encrypted_db_file(path), "data file is encrypted at rest")
with open(path, "rb") as fh:
    check(b"Real money" not in fh.read(), "real entry text no longer in clear")
after = conn.execute(
    "SELECT description FROM journal_entries").fetchone()[0]
check(before == after == "Real money", "the real data survived encryption")

print("2. Turn protection OFF again")
conn = turn_off(conn, path, key)
check(not crypto.is_protected(path), "vault removed (now Open)")
with open(path, "rb") as fh:
    check(fh.read(16).startswith(b"SQLite format 3"),
          "data file is a plain SQLite database again")
d = conn.execute("SELECT description FROM journal_entries").fetchone()[0]
check(d == "Real money", "data intact after turning protection off")

print("3. Data is identical across on -> off -> on -> off")
conn, key = turn_on(conn, path, "second passphrase")
conn = turn_off(conn, path, key)
n = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
acc = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
check(n == 1 and acc > 0, "entries and accounts intact after full round trip")
conn.close()

print("4. Recover from an interrupted turn-ON (vault saved, file plaintext)")
p2 = os.path.join(tmp, "half_on.db")
c2 = open_book(p2)
c2.close()
# Simulate the crash point: vault written, but encrypt_file_in_place never ran.
v, _ = crypto.create_vault("xyz")
crypto.save_vault(p2, v)
check(crypto.is_protected(p2) and not crypto.is_encrypted_db_file(p2),
      "state: vault present but file still plaintext")
c2 = open_database_like(p2)        # _open_database recovers it
check(not crypto.is_protected(p2), "stray vault removed on open")
check(c2.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1,
      "data is readable after recovery")
c2.close()

print("5. Recover from an interrupted turn-OFF (decrypted, vault remains)")
p3 = os.path.join(tmp, "half_off.db")
c3 = open_book(p3)
c3, k3 = turn_on(c3, p3, "abc")
c3.commit(); c3.close()
# Simulate the crash point: file decrypted, but delete_vault never ran.
database.decrypt_file_in_place(p3, k3)
check(crypto.is_protected(p3) and not crypto.is_encrypted_db_file(p3),
      "state: file decrypted but vault still present")
c3 = open_database_like(p3)        # _open_database recovers it
check(not crypto.is_protected(p3), "stray vault removed on open")
check(c3.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1,
      "data is readable after recovery")
c3.close()

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All protect/unprotect toggle checks passed.")
