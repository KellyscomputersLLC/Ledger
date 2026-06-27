# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Standalone test of encrypted backups, content-based dedup, and safe
restore (backup.py + database.py + crypto.py). No tkinter needed.

Run from the folder containing `ledger/`:
    python3 test_backup_atrest.py
"""
import os
import sys
import tempfile
import sqlite3

from ledger import crypto, database, seed, backup

problems = []


def check(cond, msg):
    if cond:
        print("  ok:", msg)
    else:
        print("  FAIL:", msg)
        problems.append(msg)


def make_protected_book(path, secret):
    vault, _ = crypto.create_vault(secret)
    key = crypto.unlock(vault, secret)
    conn = database.connect(path, data_key=key)
    database.init_db(conn)
    seed.seed_accounts(conn)
    conn.commit()
    return conn, key


tmp = tempfile.mkdtemp()
bdir = os.path.join(tmp, "backups")
os.makedirs(bdir)

print("1. A backup of a protected book is itself encrypted")
db = os.path.join(tmp, "books.db")
conn, key = make_protected_book(db, "passphrase one")
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-01-01', 'Opening', '2025-01-01T00:00:00')")
conn.commit()
b1 = backup.backup(db_path=db, backup_dir=bdir, create=True)
check(crypto.is_encrypted_db_file(b1), "backup file carries encrypted header")
with open(b1, "rb") as f:
    raw = f.read()
check(b"Opening" not in raw, "no plaintext entry text leaks into the backup")
# It decrypts with the book's key back to the real data.
plain = crypto.decrypt_db_bytes(key, raw)
check(plain.startswith(b"SQLite format 3"), "backup decrypts to a real DB")

print("2. Dedup: the same data is recognised despite a fresh-nonce re-save")
# Simulate the on-close path: commit again with NO data change. For an
# encrypted book this re-writes the live file with a brand-new nonce, so its
# raw bytes now differ from the backup we just made.
conn.commit()
with open(db, "rb") as f:
    live_now = f.read()
check(live_now != raw, "live file bytes changed after a no-op re-save (new nonce)")
# Raw-byte comparison (no key) would wrongly say 'not backed up' -> the bug:
check(not backup.is_current_state_backed_up(db, bdir, data_key=None),
      "without the key, raw-byte dedup is fooled (would over-backup) -- the bug")
# Content comparison (with key) correctly sees the data is already backed up:
check(backup.is_current_state_backed_up(db, bdir, data_key=key),
      "with the key, content dedup recognises the data IS backed up -- fixed")

print("3. Dedup: a real data change is detected")
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-01-02', 'A new entry', '2025-01-02T00:00:00')")
conn.commit()
check(not backup.is_current_state_backed_up(db, bdir, data_key=key),
      "a genuine change is seen as not-yet-backed-up")

print("4. Restore an encrypted backup brings the old data back")
# Right now the live book has 2 entries; b1 was made when it had 1.
before = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
conn.close()
restored_from, safety = backup.restore(b1, db_path=db, data_key=key)
check(safety is not None and os.path.exists(safety),
      "a pre-restore safety copy was made")
check(crypto.is_encrypted_db_file(safety), "the safety copy is encrypted too")
conn = database.connect(db, data_key=key)
after = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
check(before == 2 and after == 1, "restore rolled 2 entries back to 1")
conn.close()

print("5. Restore refuses a backup from a DIFFERENT book (no data touched)")
db2 = os.path.join(tmp, "other.db")
conn2, key2 = make_protected_book(db2, "different passphrase")
conn2.execute("INSERT INTO journal_entries (date, description, created_at) "
              "VALUES ('2025-09-09', 'Other book', '2025-09-09T00:00:00')")
conn2.commit()
b_other = backup.backup(db_path=db2, backup_dir=bdir, create=True)
conn2.close()
# Try to restore book2's backup over book1 using book1's key -> must refuse.
with open(db, "rb") as f:
    db_before = f.read()
try:
    backup.restore(b_other, db_path=db, data_key=key)
    check(False, "wrong-book backup was rejected")
except ValueError:
    check(True, "wrong-book backup raises ValueError before touching disk")
with open(db, "rb") as f:
    db_after = f.read()
check(db_before == db_after, "the live book file was left completely untouched")

print("6. The unencrypted (Open) path is unchanged")
pdb = os.path.join(tmp, "open.db")
pconn = database.connect(pdb)            # no key
database.init_db(pconn)
seed.seed_accounts(pconn)
pconn.commit()
pconn.close()
pbdir = os.path.join(tmp, "pbackups")
os.makedirs(pbdir)
pb = backup.backup(db_path=pdb, backup_dir=pbdir, create=True)
with open(pb, "rb") as f:
    check(f.read(16).startswith(b"SQLite format 3"),
          "Open-book backup is a plain SQLite copy")
check(backup.is_current_state_backed_up(pdb, pbdir),
      "Open-book dedup (no key) recognises the just-made backup")
# restore without a key still works
r, s = backup.restore(pb, db_path=pdb)
check(os.path.exists(pdb), "Open-book restore completes")

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All backup at-rest checks passed.")
