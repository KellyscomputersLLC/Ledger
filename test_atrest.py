# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Standalone test of the at-rest encryption core (database.py + crypto.py).

Runs without tkinter: it exercises only the database/crypto layers, the way
the GUI eventually will. Run from the folder containing `ledger/`:

    python3 test_atrest.py
"""
import os
import sys
import tempfile
import sqlite3

from ledger import crypto, database, seed

problems = []


def check(cond, msg):
    if cond:
        print("  ok:", msg)
    else:
        print("  FAIL:", msg)
        problems.append(msg)


tmp = tempfile.mkdtemp()
vault, _code = crypto.create_vault("correct horse")
KEY = crypto.unlock(vault, "correct horse")
other_vault, _ = crypto.create_vault("a different secret")
WRONG = crypto.unlock(other_vault, "a different secret")

print("1. Create an encrypted book from scratch")
enc_path = os.path.join(tmp, "books.db")
conn = database.connect(enc_path, data_key=KEY)
database.init_db(conn)
seed.seed_accounts(conn)          # real schema + default accounts
conn.commit()
check(os.path.exists(enc_path), "encrypted file written on commit")
check(crypto.is_encrypted_db_file(enc_path),
      "file carries the encrypted-book header")
with open(enc_path, "rb") as f:
    on_disk = f.read()
check(not on_disk.startswith(b"SQLite format 3"),
      "on-disk file is NOT a plaintext SQLite database")
# The default seed includes an account named 'Checking Account' -- prove that
# readable string is nowhere in the encrypted bytes.
check(b"Checking" not in on_disk,
      "no plaintext account text leaks into the encrypted file")
n_accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
check(n_accounts > 0, "accounts seeded in memory (%d)" % n_accounts)
conn.close()

print("2. Reopen with the correct key")
conn = database.connect(enc_path, data_key=KEY)
database.init_db(conn)            # idempotent; mirrors the real open path
got = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
check(got == n_accounts, "same account count after reopen (%d)" % got)

print("3. A change is persisted, encrypted, on commit")
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-02-01', 'Test entry', '2025-02-01T00:00:00')")
conn.commit()
conn.close()
conn = database.connect(enc_path, data_key=KEY)
desc = conn.execute("SELECT description FROM journal_entries").fetchone()[0]
check(desc == "Test entry", "committed change survives reopen")
conn.close()

print("4. The wrong key cannot open it")
try:
    database.connect(enc_path, data_key=WRONG)
    check(False, "wrong key was rejected")
except ValueError:
    check(True, "wrong key raises ValueError (no data revealed)")

print("5. Tampering is detected")
bad_path = os.path.join(tmp, "tampered.db")
with open(enc_path, "rb") as f:
    data = bytearray(f.read())
data[-1] ^= 0x01                  # flip one bit in the ciphertext/tag
with open(bad_path, "wb") as f:
    f.write(data)
try:
    database.connect(bad_path, data_key=KEY)
    check(False, "tampered file was rejected")
except ValueError:
    check(True, "tampered file raises ValueError (authentication caught it)")

print("6. The unencrypted (Open) path is unchanged")
plain_path = os.path.join(tmp, "open.db")
conn = database.connect(plain_path)            # no key
database.init_db(conn)
seed.seed_accounts(conn)
conn.commit()
conn.close()
with open(plain_path, "rb") as f:
    head = f.read(16)
check(head.startswith(b"SQLite format 3"),
      "Open book is a real on-disk SQLite file")
raw = sqlite3.connect(plain_path)              # a plain reader can open it
cnt = raw.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
raw.close()
check(cnt > 0, "Open book is readable by a plain SQLite connection")

print("7. Protect an existing plaintext book in place")
conv_path = os.path.join(tmp, "convert.db")
conn = database.connect(conv_path)
database.init_db(conn)
seed.seed_accounts(conn)
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-03-03', 'Before protect', '2025-03-03T00:00:00')")
conn.commit()
conn.close()
v2, _ = crypto.create_vault("protect me")
k2 = crypto.unlock(v2, "protect me")
database.encrypt_file_in_place(conv_path, k2)
check(crypto.is_encrypted_db_file(conv_path),
      "converted file is now encrypted")
conn = database.connect(conv_path, data_key=k2)
d = conn.execute("SELECT description FROM journal_entries").fetchone()[0]
check(d == "Before protect", "data intact after protect-in-place")
conn.close()

print("8. Turn protection off (decrypt in place)")
database.decrypt_file_in_place(conv_path, k2)
with open(conv_path, "rb") as f:
    check(f.read(16).startswith(b"SQLite format 3"),
          "decrypted file is a plaintext SQLite database again")
raw = sqlite3.connect(conv_path)
d = raw.execute("SELECT description FROM journal_entries").fetchone()[0]
raw.close()
check(d == "Before protect", "data intact after un-protect")

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All at-rest core checks passed.")
