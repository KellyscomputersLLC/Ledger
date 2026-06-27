# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Cross-version / cross-capability restore behaviour (backup.py + crypto.py).
No tkinter needed.

The matrix this pins down:

  backup type      target book      expected
  --------------   --------------   ------------------------------------------
  encrypted        Open (no key)    REFUSED, nothing touched  (the fixed gap)
  plaintext        Open (no key)    allowed (normal restore)
  plaintext        Protected        REFUSED (doesn't match the key)
  encrypted (else) Protected        REFUSED (different book's key)
  encrypted (same) Protected        allowed, data restored
  future-format    any              clear "update Ledger" error on open

Plus: the encrypted-file header check is library-free (it never calls a
crypto primitive), which is why the encrypted->Open refusal works even on a
computer without the cryptography library.

Run from the folder containing `ledger/`:
    python3 test_cross_version.py
"""
import os
import sys
import tempfile
import shutil

from ledger import crypto, database, seed, backup

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


def new_book(p, with_entry="Entry"):
    c = database.connect(p)
    database.init_db(c)
    seed.seed_accounts(c)
    c.execute("INSERT INTO journal_entries (date, description, created_at) "
              "VALUES ('2025-01-01', ?, 't')", (with_entry,))
    c.commit()
    return c


def protect(c, p, secret):
    v, _ = crypto.create_vault(secret)
    crypto.save_vault(p, v)
    k = crypto.unlock(v, secret)
    c.commit(); c.close()
    database.encrypt_file_in_place(p, k)
    return database.connect(p, data_key=k), k


tmp = tempfile.mkdtemp()
bdir_A = os.path.join(tmp, "bkA"); os.makedirs(bdir_A)
bdir_P = os.path.join(tmp, "bkP"); os.makedirs(bdir_P)

# A protected book "A" and an encrypted backup of it.
A = os.path.join(tmp, "A.db")
ca = new_book(A, "Book A data")
ca, ka = protect(ca, A, "passphrase A")
enc_backup_A = backup.backup(db_path=A, backup_dir=bdir_A, create=True)
ca.close()

# A plaintext backup (from an Open book).
P = os.path.join(tmp, "P.db")
cp = new_book(P, "Plain data"); cp.close()
plain_backup = backup.backup(db_path=P, backup_dir=bdir_P, create=True)


print("1. The encrypted-file header check is library-free and accurate")
check(crypto.is_encrypted_db_file(enc_backup_A), "encrypted backup detected")
check(not crypto.is_encrypted_db_file(plain_backup),
      "plaintext backup not misdetected")
# looks_like_encrypted_db works on raw bytes with no crypto call:
with open(plain_backup, "rb") as fh:
    check(not crypto.looks_like_encrypted_db(fh.read(16)),
          "plaintext header bytes are not flagged as encrypted")


print("2. Encrypted backup -> Open book (no key): REFUSED, nothing touched")
openbk = os.path.join(tmp, "open.db")
co = new_book(openbk, "Open book data"); co.close()
with open(openbk, "rb") as fh:
    before = fh.read()
try:
    backup.restore(enc_backup_A, db_path=openbk, data_key=None)
    check(False, "encrypted->Open was refused")
except ValueError as e:
    check("unencrypted" in str(e), "refused with a clear message")
with open(openbk, "rb") as fh:
    check(fh.read() == before, "the Open book file was left untouched")


print("3. Plaintext backup -> Open book (no key): allowed (normal restore)")
r, safety = backup.restore(plain_backup, db_path=openbk, data_key=None)
co = database.connect(openbk)
d = co.execute("SELECT description FROM journal_entries").fetchone()[0]
check(d == "Plain data", "plaintext restore into an Open book works")
co.close()


print("4. Plaintext backup -> Protected book: REFUSED")
B = os.path.join(tmp, "B.db")
cb = new_book(B, "Book B data")
cb, kb = protect(cb, B, "passphrase B")
with open(B, "rb") as fh:
    b_before = fh.read()
try:
    backup.restore(plain_backup, db_path=B, data_key=kb)
    check(False, "plaintext->Protected was refused")
except ValueError:
    check(True, "plaintext->Protected refused")
with open(B, "rb") as fh:
    check(fh.read() == b_before, "Protected book untouched")


print("5. A different book's encrypted backup -> Protected book: REFUSED")
try:
    backup.restore(enc_backup_A, db_path=B, data_key=kb)   # A's backup, B's key
    check(False, "different-book encrypted backup refused")
except ValueError:
    check(True, "different-book encrypted backup refused (wrong key)")
with open(B, "rb") as fh:
    check(fh.read() == b_before, "Protected book still untouched")
cb.close()


print("6. The matching encrypted backup -> its own Protected book: allowed")
# Change A, then restore A's earlier backup into A.
ca = database.connect(A, data_key=ka)
ca.execute("INSERT INTO journal_entries (date, description, created_at) "
           "VALUES ('2025-02-02', 'extra', 't')")
ca.commit()
n_before = ca.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
ca.close()
backup.restore(enc_backup_A, db_path=A, data_key=ka)
ca = database.connect(A, data_key=ka)
n_after = ca.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
check(n_before == 2 and n_after == 1, "restoring own backup rolled data back")
ca.close()


print("7. A future-format encrypted file gives a clear 'update' error")
future = os.path.join(tmp, "future.db")
# Forge a blob with our magic but a higher version byte.
blob = crypto.ENC_DB_MAGIC + bytes([crypto.ENC_DB_VERSION + 1]) + b"whatever"
with open(future, "wb") as fh:
    fh.write(blob)
check(crypto.is_encrypted_db_file(future), "still recognised as our file")
try:
    crypto.decrypt_db_bytes(ka, blob)
    check(False, "future-format raised")
except ValueError as e:
    check("newer version" in str(e).lower() or "format" in str(e).lower(),
          "future-format gives a clear update message")


print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All cross-version restore checks passed.")
