# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Reproduces the exact sequence of database/backup/crypto calls the GUI makes
in slice 3 -- without tkinter, which isn't available in every environment.

This does NOT exercise the Tk widgets (run test_gui.py on a desktop for that).
It proves the *choreography* the GUI performs is sound:

  * create a new book, then protect it (the _setup_protection ->
    _encrypt_open_book_at_rest path),
  * reopen a protected book with a key (the _open_database path),
  * the on-close autosave dedup with its commit-then-check (which re-nonces),
  * restore + reopen-with-known-key (the _restore path), including the
    wrong-book refusal.

Run from the folder containing `ledger/`:
    python3 test_gui_choreography.py
"""
import os
import sys
import tempfile

from ledger import crypto, database, seed, backup, profile

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "Kellys_Computers.db")
bdir = os.path.join(tmp, "book_backups")
os.makedirs(bdir)


# --- helpers that mirror what the GUI methods do -------------------------

def gui_create_new_book(p):
    """Mirrors _open_database() for a brand-new book: plaintext on disk,
    schema + seeded accounts."""
    conn = database.connect(p)                 # no key yet -> plaintext
    database.init_db(conn)
    seed.seed_accounts(conn)
    conn.commit()
    return conn


def gui_encrypt_open_book_at_rest(conn, p, key):
    """Mirrors _encrypt_open_book_at_rest(): commit, close, encrypt-in-place
    (verified), reopen as an in-memory encrypted connection."""
    try:
        conn.commit()
    except Exception:
        pass
    conn.close()
    database.encrypt_file_in_place(p, key)
    if crypto.is_encrypted_db_file(p):
        return database.connect(p, data_key=key)
    return database.connect(p)


print("1. Create a new book, then protect it (setup choreography)")
conn = gui_create_new_book(path)
# _setup_fresh_books records the kind on the new (still plaintext) book:
profile.save_profile(conn, kind="business")
conn.commit()
# _setup_protection: build the vault, hold the key, then encrypt at rest.
vault, recovery = crypto.create_vault("a strong passphrase")
crypto.save_vault(path, vault)
key = crypto.unlock(vault, "a strong passphrase")
conn = gui_encrypt_open_book_at_rest(conn, path, key)
check(crypto.is_protected(path), "vault file exists (is_protected True)")
check(crypto.is_encrypted_db_file(path), "data file is now encrypted at rest")
with open(path, "rb") as f:
    check(not f.read().startswith(b"SQLite format 3"),
          "data file is no longer a plaintext SQLite database")
check(profile.get_profile(conn)["kind"] == "business",
      "the kind chosen at setup survived encryption")
n_acct = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
check(n_acct > 0, "seeded accounts present after encryption (%d)" % n_acct)

print("2. The locked book's name falls back to its filename (manager view)")
# Mirrors _ledger_summary() for a protected file: no key, can't read inside.
stem = os.path.splitext(os.path.basename(path))[0]
check(crypto.is_protected(path) and stem == "Kellys_Computers",
      "manager would label the locked book by its file name")

print("3. Record an entry; on first close an encrypted backup is made")
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-04-01', 'First sale', '2025-04-01T00:00:00')")
conn.commit()                                  # flushes encrypted file
# _autosave_on_exit: commit, then dedup-check with the key.
conn.commit()
need_backup = not backup.is_current_state_backed_up(path, bdir, data_key=key)
check(need_backup, "before any backup, on-close sees data not yet backed up")
b1 = backup.backup(db_path=path, backup_dir=backup.auto_dir(bdir),
                   create=True, name_tag="_auto")
check(crypto.is_encrypted_db_file(b1), "the on-close backup is encrypted")

print("4. Closing again with no change makes NO duplicate backup")
conn.commit()                                  # re-nonces the live file
already = backup.is_current_state_backed_up(path, bdir, data_key=key)
check(already, "content dedup recognises the data is already backed up")

print("5. Restore the backup and reopen WITHOUT a fresh passphrase prompt")
conn.execute("INSERT INTO journal_entries (date, description, created_at) "
             "VALUES ('2025-04-02', 'Second sale', '2025-04-02T00:00:00')")
conn.commit()
before = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
conn.close()
restored_from, safety = backup.restore(b1, db_path=path, data_key=key)
# _restore reopens with the key already in memory (known_key) -> no prompt.
conn = database.connect(path, data_key=key)    # i.e. _open_database(known_key=key)
after = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
check(before == 2 and after == 1, "restore rolled the second sale back")
check(safety and crypto.is_encrypted_db_file(safety),
      "the pre-restore safety copy is encrypted")
conn.close()

print("6. Restoring a DIFFERENT book's backup is refused, data untouched")
other = os.path.join(tmp, "Other.db")
oc = gui_create_new_book(other)
ov, _ = crypto.create_vault("other secret")
crypto.save_vault(other, ov)
okey = crypto.unlock(ov, "other secret")
oc = gui_encrypt_open_book_at_rest(oc, other, okey)
ob = backup.backup(db_path=other, backup_dir=bdir, create=True)
oc.close()
with open(path, "rb") as f:
    before_bytes = f.read()
try:
    backup.restore(ob, db_path=path, data_key=key)   # wrong key for this backup
    check(False, "wrong-book restore was refused")
except ValueError:
    check(True, "wrong-book restore raised ValueError")
with open(path, "rb") as f:
    check(f.read() == before_bytes, "the live book file was left untouched")

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All GUI-choreography checks passed.")
