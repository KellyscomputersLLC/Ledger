# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Minimal headless GUI smoke test - dialogs stubbed (no user to click)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
test_db = os.path.join(tmp, "gui_test.db")
from ledger import database
database.DEFAULT_DB_PATH = test_db
from ledger import gui, accounts, transactions, backup as backup_mod, profile

# Stub modal dialogs: in headless tests there's no user to click them.
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: print("  [dialog-error]", a[1] if len(a)>1 else a)
gui.messagebox.askyesno = lambda *a, **k: True
# The encryption setup is a modal dialog (tested separately). First-run setup
# runs it during construction, so stub it at the class level before building
# the app, not just on the instance afterwards.
gui.LedgerApp._setup_protection = lambda self, *a, **k: "open"

app = gui.LedgerApp()
app.update()
problems = []

accts = accounts.list_accounts(app.conn)
print(f"Accounts loaded: {len(accts)}")
if len(accts) != 34: problems.append(f"expected 34 accounts, got {len(accts)}")

et = app.tab_entry
et.refresh()
et.date_var.set("2025-01-01")
et.desc_var.set("Owner startup capital")
choices = app.account_choices()
checking = next(c for c in choices if c.startswith("1000"))
capital = next(c for c in choices if c.startswith("3000"))
et.line_widgets[0]["account"].set(checking)
et.line_widgets[0]["debit"].set("5000")
et.line_widgets[1]["account"].set(capital)
et.line_widgets[1]["credit"].set("5000")
et._update_totals()
app.update()
et._record()
app.update()
entries = transactions.list_entries(app.conn)
print(f"Entries after recording: {len(entries)}")
if len(entries) != 1: problems.append(f"expected 1 entry, got {len(entries)}")

# Second entry: a split, on the credit card
et.date_var.set("2025-01-05")
et.desc_var.set("Supplies and a monitor on the card")
supplies = next(c for c in choices if c.startswith("6300"))
equip = next(c for c in choices if c.startswith("1500"))
card = next(c for c in choices if c.startswith("2100"))
et.line_widgets[0]["account"].set(supplies); et.line_widgets[0]["debit"].set("150")
et.line_widgets[1]["account"].set(equip); et.line_widgets[1]["debit"].set("400")
et.line_widgets[2]["account"].set(card); et.line_widgets[2]["credit"].set("550")
et._update_totals(); app.update(); et._record(); app.update()
print(f"Entries after split entry: {len(transactions.list_entries(app.conn))}")

# --- Business Info tab: save a profile ---
bt = app.tab_business
bt.refresh()
bt.name_var.set("Kelly's Computers LLC")
bt.tagline_var.set("Technology help you can trust")
bt.address_text.insert("1.0", "123 Main Street\nMorrisville, VT 05661")
bt.contact_text.insert("1.0", "(802) 555-0142")
bt._save()
app.update()
saved = profile.get_profile(app.conn)
if saved["name"] != "Kelly's Computers LLC":
    problems.append("business profile name not saved")
else:
    print("Business profile saved via GUI")

rt = app.tab_reports
for rn in ("Trial Balance", "Income Statement", "Balance Sheet", "General Ledger"):
    rt.report_var.set(rn)
    rt._generate()
    app.update()
    content = rt.text.get("1.0", "end").strip()
    if not content: problems.append(f"{rn} empty")
    else: print(f"{rn}: {len(content)} chars")
rt.report_var.set("Trial Balance"); rt._generate(); app.update()
tb_text = rt.text.get("1.0", "end")
if "IN BALANCE" not in tb_text:
    problems.append("TB not IN BALANCE")
else: print("Trial balance reports IN BALANCE")
# The business name should now appear in the report header
if "Kelly's Computers LLC" not in tb_text:
    problems.append("business header not on report")
else:
    print("Business header appears on report")

app.tab_backup._make_backup()
app.update()
nb = len(backup_mod.list_backups())
print(f"Backups: {nb}")
if nb < 1: problems.append("no backup file")

# --- Backup tab: back up to a custom folder (simulating a USB drive) ---
import tempfile as _tf
usb_sim = _tf.mkdtemp()  # a real folder that stands in for a USB drive
bk_tab = app.tab_backup
bk_tab._do_backup_to_folder(usb_sim, remember=True)
app.update()
usb_files = [f for f in os.listdir(usb_sim) if f.startswith("ledger_backup_")]
if not usb_files:
    problems.append("backup to custom folder did not create a file")
else:
    print(f"Backup to custom folder worked: {usb_files[0]}")
# the custom location should now be remembered
if backup_mod.get_last_location() != usb_sim:
    problems.append("custom backup location not remembered")
else:
    print("Custom backup location remembered")
# refresh should now show the 'back up again' button
bk_tab.refresh()
app.update()
if not bk_tab._again_shown:
    problems.append("'back up to last location' button not shown")
else:
    print("'Back up to last location' button appears after first use")
# backing up to a folder that doesn't exist must fail cleanly
import shutil as _sh
gone = _tf.mkdtemp(); _sh.rmtree(gone)  # a path guaranteed not to exist
try:
    backup_mod.backup(db_path=app.db_path, backup_dir=gone)
    problems.append("backup to missing folder did not raise")
except FileNotFoundError:
    print("Backup to a missing folder correctly refused")

# --- Accounts tab: add an account ---
app.tab_accounts.refresh()
app.tab_accounts.code_var.set("6310")
app.tab_accounts.name_var.set("Software Subscriptions")
app.tab_accounts.type_var.set("EXPENSE")
app.tab_accounts._add_account()
app.update()
if len(accounts.list_accounts(app.conn)) != 35:
    problems.append("add-account via GUI failed")
else:
    print("Added account via GUI: now 35 accounts")

# --- Accounts tab: rename an account ---
at = app.tab_accounts
at.refresh()
# Select the Checking Account row in the tree, then rename it.
for iid in at.tree.get_children():
    if at.tree.item(iid, "values")[0] == "1000":
        at.tree.selection_set(iid)
        break
at.rename_var.set("TD Business Checking")
at._rename_account()
app.update()
renamed = accounts.get_account(app.conn, "1000")
if renamed["name"] != "TD Business Checking":
    problems.append(f"rename failed, name is {renamed['name']}")
else:
    print("Renamed account 1000 via GUI")

# --- Accounts tab: deactivate then reactivate an account ---
at.refresh(); app.update()
for iid in at.tree.get_children():
    if at.tree.item(iid, "values")[0] == "6310":
        at.tree.selection_set(iid); break
at._deactivate_account(); app.update()
if "6310" in [a["code"] for a in accounts.list_accounts(app.conn)]:
    problems.append("deactivate did not remove 6310 from active accounts")
elif any(c.startswith("6310") for c in app.account_choices()):
    problems.append("deactivated account still appears in the entry picker")
else:
    print("Deactivated 6310: gone from active list and entry picker")
at.show_inactive_var.set(True); at.refresh(); app.update()
shown = [at.tree.item(i, "values")[0] for i in at.tree.get_children()]
if "6310" not in shown:
    problems.append("inactive account not shown when 'show inactive' is on")
else:
    print("Inactive account visible when 'show inactive' is on")
for iid in at.tree.get_children():
    if at.tree.item(iid, "values")[0] == "6310":
        at.tree.selection_set(iid); break
at._reactivate_account(); app.update()
if "6310" not in [a["code"] for a in accounts.list_accounts(app.conn)]:
    problems.append("reactivate did not restore 6310")
else:
    print("Reactivated 6310: back in active list")
at.show_inactive_var.set(False); at.refresh(); app.update()

# --- Reconcile tab: feed Ledger's own figures back and confirm match ---
from ledger import reports as _rep
rc = app.tab_reconcile
rc.refresh(); app.update()
_led = _rep.reconciliation(app.conn)
_chk = {a["code"]: a for a in _led["accounts"]}["1000"]
for _k in ("beginning", "money_in", "money_out", "ending"):
    rc.rows["1000"]["vars"][_k].set(str(_chk[_k]))
rc._compare(); app.update()
if rc.rows["1000"]["status"].cget("text") != "reconciled":
    problems.append("checking did not reconcile in GUI")
elif "reconciled" not in rc.summary_var.get():
    problems.append("reconcile summary missing")
else:
    print("Reconcile tab: checking reconciles against its own figures")

# --- About window opens and closes ---
app._show_about()
app.update()
# find and destroy the Toplevel so it doesn't block
import tkinter as tk
tops = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
if tops:
    print("About window opened")
    for w in tops: w.destroy()
else:
    problems.append("About window did not open")
app.update()

for i in range(7):
    app.tabs.select(i); app.update()
print("All 7 tabs visited without error")

app.destroy()
print()
if problems:
    print("PROBLEMS:"); [print("  -", p) for p in problems]; sys.exit(1)
else:
    print("All GUI smoke checks passed.")

