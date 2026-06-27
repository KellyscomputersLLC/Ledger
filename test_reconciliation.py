# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Test of the bank reconciliation figures.

The point of this test is the tricky part: the BEGINNING balance of a
reconciliation period must include all history from before the period,
not just the activity inside it. So we build a January, then reconcile
February, and check that February's beginning balance is January's
ending balance -- for both an asset (checking) and a liability (card).
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledger import database, seed, transactions, reports

tmp = tempfile.mkdtemp()
conn = database.connect(os.path.join(tmp, "recon_test.db"))
database.init_db(conn)
seed.seed_accounts(conn)

def entry(date_str, desc, debits, credits):
    lines = [{"code": c, "debit": a, "credit": 0} for c, a in debits]
    lines += [{"code": c, "debit": 0, "credit": a} for c, a in credits]
    transactions.add_entry(conn, date_str, desc, lines)

# --- January (BEFORE the period we will reconcile) -----------------------
entry("2025-01-05", "Owner invests startup capital",
      [("1000", 15000)], [("3000", 15000)])
entry("2025-01-10", "Buy a laptop",
      [("1500", 2200)], [("1000", 2200)])
entry("2025-01-15", "Office supplies on the credit card",
      [("6300", 350)], [("2100", 350)])
# After January:
#   Checking (1000): 15000 - 2200 = 12,800
#   Credit card owed (2100): 350

# --- February (the period we reconcile) ----------------------------------
entry("2025-02-08", "Consulting job, paid to checking",
      [("1000", 3000)], [("4100", 3000)])
entry("2025-02-12", "Pay February rent from checking",
      [("6400", 1200)], [("1000", 1200)])
entry("2025-02-18", "More supplies on the credit card",
      [("6300", 100)], [("2100", 100)])
entry("2025-02-25", "Pay down part of the credit card from checking",
      [("2100", 200)], [("1000", 200)])

problems = []

recon = reports.reconciliation(conn, start="2025-02-01", end="2025-02-28")
by_code = {a["code"]: a for a in recon["accounts"]}

# --- Checking: an ASSET (money in = deposits, money out = withdrawals) ---
chk = by_code["1000"]
print("Checking:", chk["beginning"], chk["money_in"], chk["money_out"], chk["ending"])
# Beginning must carry January's ending balance, not start from zero:
if chk["beginning"] != 12800.00: problems.append(f"checking beginning {chk['beginning']} != 12800")
if chk["money_in"]  != 3000.00:  problems.append(f"checking money_in {chk['money_in']} != 3000")
# money out = rent 1200 + card payment 200
if chk["money_out"] != 1400.00:  problems.append(f"checking money_out {chk['money_out']} != 1400")
if chk["ending"]    != 14400.00: problems.append(f"checking ending {chk['ending']} != 14400")

# --- Credit card: a LIABILITY (money in = new charges, out = payments) ---
card = by_code["2100"]
print("Card:    ", card["beginning"], card["money_in"], card["money_out"], card["ending"])
# Beginning carries January's 350 owed:
if card["beginning"] != 350.00: problems.append(f"card beginning {card['beginning']} != 350")
# For a liability, a new charge INCREASES what you owe -> money in
if card["money_in"]  != 100.00: problems.append(f"card money_in {card['money_in']} != 100")
# a payment DECREASES what you owe -> money out
if card["money_out"] != 200.00: problems.append(f"card money_out {card['money_out']} != 200")
if card["ending"]    != 250.00: problems.append(f"card ending {card['ending']} != 250")

# --- The identity Beginning + In - Out = Ending must hold for every row --
for a in recon["accounts"]:
    expect = round(a["beginning"] + a["money_in"] - a["money_out"], 2)
    if a["ending"] != expect:
        problems.append(f"{a['code']} identity broken: {a['ending']} != {expect}")

# --- No start date = reconcile from the beginning of the books -----------
recon_all = reports.reconciliation(conn, start=None, end="2025-02-28")
chk_all = {a["code"]: a for a in recon_all["accounts"]}["1000"]
if chk_all["beginning"] != 0.00: problems.append("no-start beginning should be 0")
if chk_all["ending"]    != 14400.00: problems.append("no-start ending should still be 14400")
print("From inception, checking ending:", chk_all["ending"])

# --- It is READ-ONLY: running it must not change any balances ------------
tb_before = reports.trial_balance(conn)["total_debit"]
reports.reconciliation(conn, start="2025-02-01", end="2025-02-28")
tb_after = reports.trial_balance(conn)["total_debit"]
if tb_before != tb_after: problems.append("reconciliation changed the books!")
else: print("Reconciliation did not alter the books: OK")

# --- Comparison against a statement: one matches, one is wrong, one blank -
bank_inputs = {
    # Checking matches Ledger exactly -> should reconcile
    "1000": {"beginning": 12800, "money_in": 3000, "money_out": 1400, "ending": 14400},
    # Card: user's ending is wrong by 50 -> should NOT reconcile, diff -50
    "2100": {"beginning": 350, "money_in": 100, "money_out": 200, "ending": 200},
    # (every other account left blank)
}
cmp = reports.reconcile_against_statement(recon, bank_inputs)
status = {r["code"]: r for r in cmp["rows"]}
if not status["1000"]["reconciled"]: problems.append("checking should reconcile")
if status["2100"]["reconciled"]: problems.append("card should NOT reconcile (ending wrong)")
card_end = status["2100"]["fields"]["ending"]
if card_end["difference"] != -50.00:
    problems.append(f"card ending difference {card_end['difference']} != -50")
if cmp["n_checked"] != 2: problems.append(f"n_checked {cmp['n_checked']} != 2")
if cmp["n_reconciled"] != 1: problems.append(f"n_reconciled {cmp['n_reconciled']} != 1")
print(f"Comparison: {cmp['n_reconciled']} of {cmp['n_checked']} accounts reconciled")

print()
if problems:
    print("PROBLEMS:"); [print("  -", p) for p in problems]; sys.exit(1)
else:
    print("All reconciliation checks passed.")
