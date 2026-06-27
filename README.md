# Ledger

Double-entry bookkeeping for small businesses and personal finances. Ledger is
a calm desktop accounting program built for people who want trustworthy books
without a steep learning curve.

It keeps a chart of accounts, records balanced journal entries, and produces the
standard reports — Trial Balance, Income Statement (P&L), Balance Sheet, and
General Ledger — along with bank reconciliation, backups, and optional at-rest
encryption.

Ledger is free, open-source software (MIT licensed). Being open source does not
weaken its encryption: the security comes from your passphrase, not from secrecy
in the code.

## Features

- Double-entry accounting with database-level guards — every journal line is a
  debit or a credit, never both, never negative — so the books stay trustworthy
  even if application code has a bug.
- Tabs for Record Entry, Journal, Reports, Reconcile, Accounts, Backup, and
  Business Info.
- Business and personal books, each with its own data file. A sensible default
  chart of accounts is seeded on first run.
- Backups to a "Ledger Backups" folder in your Documents, plus "Back up to…" for
  a USB drive or cloud folder, and an automatic safety backup taken on close.
- Optional encryption at rest for the data file and its backups.

## Requirements

- **Python 3.11 or newer.** (3.11+ is required for encrypted books: the
  encrypted database is held in memory and serialized using features added in
  Python 3.11. Unencrypted books work on older versions, but 3.11+ is
  recommended for everyone.)
- **Tkinter** — the standard Python GUI toolkit.
- **The `cryptography` library** — needed only to create or open encrypted
  books. Ledger still runs without it for unencrypted ("Open") books.

### Install on Debian / Ubuntu (developed and tested on Debian with XFCE)

    sudo apt install python3-tk python3-cryptography

On Debian, a plain `pip install cryptography` is refused because the system
Python is externally managed — use the apt package above. Verify with:

    python3 -c "import tkinter, cryptography; print('ok')"

### Install on Windows

Install Python 3.11+ from python.org (Tkinter is included), then:

    pip install cryptography

## Running

From the folder that contains the `ledger/` package:

    python3 -m ledger

## Where your data lives

- **Data file:** `~/.ledger/` on Linux, `%APPDATA%\Ledger\` on Windows.
- **Backups:** `Documents/Ledger Backups/<business>/`, with `Manual Backups/`
  and `Automatic Backups/` subfolders. Automatic backups are kept for 30 days;
  manual backups are never pruned.

## Encryption — what it does and does not do

Ledger can encrypt a set of books "at rest." Business books are always protected;
personal books may be protected or left open. Encryption uses the audited
`cryptography` library (AES-256-GCM with scrypt key derivation) in a wrapped-key
design: one random data key encrypts the books, and that key is locked by your
passphrase and by a one-time recovery code. The data key lives only in memory
while the book is open and is never written to disk.

**It protects:** a stolen or copied data file, and a nosy person on the same
computer — without your passphrase they get unreadable bytes.

**It does not:**

- protect data while Ledger is open and unlocked;
- prevent a file from being deleted;
- act as ransomware protection (only an off-machine backup copy helps there);
- lock a folder at the operating-system level.

**Recovery.** When you turn on protection you are shown a single recovery code
**once**. It is the only way back in if you forget your passphrase. Write it on
paper and keep it somewhere safe — not on the computer, and don't photograph or
screenshot it. If you lose **both** your passphrase and the recovery code, no
one — including the program's authors — can recover the data.

Encryption alone is **not** PCI compliance. Compliance questions are for a
qualified professional.

## Tests

From the folder containing `ledger/`:

    python3 -m ledger.test_ledger
    python3 -m ledger.test_reconciliation
    xvfb-run python3 -m ledger.test_gui        # GUI smoke test (needs a display)

Standalone tests for the encryption work sit at the project root:

    python3 test_atrest.py            # at-rest encryption core
    python3 test_backup_atrest.py     # encrypted backups, dedup, restore
    python3 test_cross_version.py     # cross-version / cross-capability restore
    python3 test_protect_toggle.py    # turn protection on/off, crash recovery
    python3 test_gui_choreography.py  # the GUI's create/backup/restore sequence
    python3 test_printing.py          # recovery-code printing
    python3 test_attribution.py       # centralized attribution

## Scope

Ledger is a bookkeeping tool. It is not a substitute for advice from a qualified
accountant, tax professional, or attorney.

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2026 Kelly's Computers LLC.

## Credits

Designed and built by Kelly's Computers LLC.
