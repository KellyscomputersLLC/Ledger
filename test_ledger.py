# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
End-to-end test of Ledger.

Runs a realistic first month of a small consulting business through the
system and checks that:
  * every journal entry balances
  * the trial balance balances
  * the balance sheet balances (Assets = Liabilities + Equity)
  * net income flows correctly into the balance sheet
  * an intentionally unbalanced entry is rejected
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledger import database, seed, accounts, transactions, reports, paths

# --- Cross-platform paths sanity check -----------------------------------
# The paths module should hand back a usable per-user data folder on
# whatever operating system this is (Linux or Windows).
dd = paths.data_dir()
assert os.path.isdir(dd), f"data_dir() did not create a usable folder: {dd}"
assert paths.default_db_path().endswith("ledger.db")
assert os.path.isdir(paths.backups_dir())
print(f"Paths module OK (data folder: {dd})")

from ledger import database, seed, accounts, transactions, reports

# Use a throwaway database file.
tmp = tempfile.mkdtemp()
db_path = os.path.join(tmp, "test.db")

conn = database.connect(db_path)
database.init_db(conn)
n = seed.seed_accounts(conn)
print(f"Seeded {n} accounts.")
assert n == len(seed.DEFAULT_ACCOUNTS)

# Seeding again should insert nothing (idempotent).
assert seed.seed_accounts(conn) == 0
print("Re-seeding is idempotent: OK")

# --- A realistic first month ---------------------------------------------
entries = [
    ("2025-01-01", "Owner invests startup capital",
     [{"code": "1000", "debit": 15000}], [{"code": "3000", "credit": 15000}]),
    ("2025-01-02", "Buy a laptop for the business",
     [{"code": "1500", "debit": 2200}], [{"code": "1000", "credit": 2200}]),
    ("2025-01-03", "Pay January office rent",
     [{"code": "6400", "debit": 1200}], [{"code": "1000", "credit": 1200}]),
    ("2025-01-05", "Buy office supplies on the company credit card",
     [{"code": "6300", "debit": 350}], [{"code": "2100", "credit": 350}]),
    ("2025-01-10", "Invoice Acme Corp for consulting",
     [{"code": "1200", "debit": 8000}], [{"code": "4100", "credit": 8000}]),
    ("2025-01-15", "Pay business insurance premium",
     [{"code": "6200", "debit": 600}], [{"code": "1000", "credit": 600}]),
    ("2025-01-20", "Acme Corp pays their invoice",
     [{"code": "1000", "debit": 8000}], [{"code": "1200", "credit": 8000}]),
    ("2025-01-25", "Pay part of the credit card balance",
     [{"code": "2100", "debit": 350}], [{"code": "1000", "credit": 350}]),
    ("2025-01-28", "Second consulting job, paid immediately",
     [{"code": "1000", "debit": 3000}], [{"code": "4100", "credit": 3000}]),
    ("2025-01-31", "Owner draws some money out",
     [{"code": "3100", "debit": 1000}], [{"code": "1000", "credit": 1000}]),
]

for date_str, desc, debits, credits in entries:
    lines = []
    for d in debits:
        lines.append({"code": d["code"], "debit": d["debit"], "credit": 0})
    for c in credits:
        lines.append({"code": c["code"], "debit": 0, "credit": c["credit"]})
    eid = transactions.add_entry(conn, date_str, desc, lines)
    print(f"  entry #{eid}: {desc}")

print()

# --- Check: unbalanced entry must be rejected ----------------------------
try:
    transactions.add_entry(conn, "2025-01-31", "Bad entry",
                           [{"code": "1000", "debit": 100, "credit": 0},
                            {"code": "4100", "debit": 0, "credit": 90}])
    print("FAIL: unbalanced entry was accepted")
    sys.exit(1)
except transactions.TransactionError as e:
    print(f"Unbalanced entry correctly rejected: {e}")

# --- Check: entry referencing unknown account rejected -------------------
try:
    transactions.add_entry(conn, "2025-01-31", "Bad account",
                           [{"code": "9999", "debit": 100, "credit": 0},
                            {"code": "4100", "debit": 0, "credit": 100}])
    print("FAIL: entry with unknown account was accepted")
    sys.exit(1)
except transactions.TransactionError as e:
    print(f"Unknown-account entry correctly rejected: {e}")

print()

# --- Trial balance must balance ------------------------------------------
tb = reports.trial_balance(conn)
print(f"Trial balance: total debits {tb['total_debit']:.2f}, "
      f"total credits {tb['total_credit']:.2f}")
assert tb["balanced"], "Trial balance does not balance!"
print("Trial balance balances: OK")

# --- Income statement ----------------------------------------------------
inc = reports.income_statement(conn, start="2025-01-01", end="2025-01-31")
print(f"\nIncome: {inc['total_income']:.2f}  "
      f"Expenses: {inc['total_expense']:.2f}  "
      f"Net income: {inc['net_income']:.2f}")
# Income = 8000 + 3000 = 11000; Expenses = 1200 + 350 + 600 = 2150
assert inc["total_income"] == 11000.00
assert inc["total_expense"] == 2150.00
assert inc["net_income"] == 8850.00
print("Income statement figures correct: OK")

# --- Balance sheet must balance ------------------------------------------
bs = reports.balance_sheet(conn, end="2025-01-31")
print(f"\nAssets: {bs['total_assets']:.2f}")
print(f"Liabilities: {bs['total_liabilities']:.2f}")
print(f"Equity: {bs['total_equity']:.2f}")
print(f"Liabilities + Equity: {bs['total_liabilities_and_equity']:.2f}")
assert bs["balanced"], "Balance sheet does not balance!"
print("Balance sheet balances (Assets = Liabilities + Equity): OK")

# Verify the actual numbers by hand:
# Checking: 15000 -2200 -1200 -600 +8000 -350 +3000 -1000 = 20650
# Equipment: 2200
# AR: 8000 - 8000 = 0
# Total assets = 20650 + 2200 = 22850
assert bs["total_assets"] == 22850.00, bs["total_assets"]
# Credit card: 350 - 350 = 0  -> no liabilities
assert bs["total_liabilities"] == 0.00
# Equity: Owner's capital 15000 - draw 1000 + net income 8850 = 22850
assert bs["total_equity"] == 22850.00, bs["total_equity"]
print("Balance sheet figures correct: OK")

# --- General ledger ------------------------------------------------------
gl = reports.general_ledger(conn, account_code="1000")
checking = gl[0]
print(f"\nChecking account ending balance: "
      f"{checking['ending_balance']:.2f}")
assert checking["ending_balance"] == 20650.00, checking["ending_balance"]
print("General ledger running balance correct: OK")

# --- Void an entry and re-check balance ----------------------------------
all_entries = transactions.list_entries(conn)
last_id = all_entries[0]["entry"]["id"]
transactions.void_entry(conn, last_id)
tb2 = reports.trial_balance(conn)
assert tb2["balanced"], "Trial balance broken after void!"
print("Trial balance still balances after voiding an entry: OK")

print("\nAll checks passed.")
