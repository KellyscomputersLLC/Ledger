# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Command-line interface for Ledger.

Run `python -m ledger.cli --help` for the full command list, or
see the README for a worked example.

Design note: transaction entry uses a small shorthand so you do not
have to think in raw debits and credits for everyday events. For
example:

    ledger entry --date 2025-01-03 --desc "January rent" \\
        --debit 6400:1500 --credit 1000:1500

means "increase Rent expense by 1500, decrease Checking by 1500".
You can pass multiple --debit / --credit flags for split transactions.
"""

import argparse
import os
import sys

from . import (database, seed, accounts, transactions, reports,
               formatting, backup, profile, about)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _open(args):
    """Open and initialise the database for a command."""
    conn = database.connect(args.db) if args.db else database.connect()
    database.init_db(conn)
    return conn


def _parse_leg(text):
    """Parse a 'CODE:AMOUNT' string into (code, amount)."""
    if ":" not in text:
        raise SystemExit(f"Bad leg '{text}'. Expected format CODE:AMOUNT, "
                         f"e.g. 6400:1500")
    code, _, amount = text.partition(":")
    try:
        amount = float(amount)
    except ValueError:
        raise SystemExit(f"Bad amount in '{text}'. '{amount}' is not a number.")
    return code.strip(), amount


# --------------------------------------------------------------------------
# command implementations
# --------------------------------------------------------------------------

def cmd_init(args):
    conn = _open(args)
    count = seed.seed_accounts(conn)
    if count:
        print(f"Initialised ledger and added {count} default accounts.")
    else:
        print("Ledger already initialised; chart of accounts is in place.")
    print("Run 'accounts' to see the chart of accounts.")


def cmd_accounts(args):
    conn = _open(args)
    rows = accounts.list_accounts(conn, include_inactive=args.all)
    if not rows:
        print("No accounts yet. Run 'init' to create the default chart.")
        return
    print(f"{'Code':<8}{'Name':<34}{'Type':<12}{'Normal':<8}{'Active'}")
    print("-" * 70)
    current_type = None
    for r in rows:
        if r["type"] != current_type:
            current_type = r["type"]
        active = "yes" if r["active"] else "no"
        print(f"{r['code']:<8}{r['name']:<34}{r['type']:<12}"
              f"{r['normal_balance']:<8}{active}")


def cmd_add_account(args):
    conn = _open(args)
    try:
        accounts.add_account(conn, args.code, args.name, args.type)
    except accounts.AccountError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Added account {args.code} {args.name} ({args.type.upper()}).")


def cmd_rename_account(args):
    conn = _open(args)
    try:
        accounts.rename_account(conn, args.code, args.name)
    except accounts.AccountError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Renamed account {args.code} to '{args.name}'.")


def cmd_deactivate_account(args):
    conn = _open(args)
    try:
        accounts.set_account_active(conn, args.code, False)
    except accounts.AccountError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Deactivated account {args.code}.")


def cmd_entry(args):
    conn = _open(args)
    lines = []
    for leg in args.debit or []:
        code, amount = _parse_leg(leg)
        lines.append({"code": code, "debit": amount, "credit": 0})
    for leg in args.credit or []:
        code, amount = _parse_leg(leg)
        lines.append({"code": code, "debit": 0, "credit": amount})
    try:
        entry_id = transactions.add_entry(
            conn, args.date, args.desc, lines, reference=args.ref
        )
    except transactions.TransactionError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Recorded journal entry #{entry_id}: {args.desc}")


def cmd_void(args):
    conn = _open(args)
    try:
        transactions.void_entry(conn, args.id)
    except transactions.TransactionError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Voided journal entry #{args.id}.")


def cmd_journal(args):
    conn = _open(args)
    entries = transactions.list_entries(conn, start=args.start, end=args.end)
    if not entries:
        print("No journal entries in that range.")
        return
    for item in entries:
        e = item["entry"]
        ref = f"  (ref: {e['reference']})" if e["reference"] else ""
        print(f"#{e['id']}  {e['date']}  {e['description']}{ref}")
        for ln in item["lines"]:
            if ln["debit"]:
                print(f"      Dr  {ln['code']} {ln['name']:<32}"
                      f"{ln['debit']:>12,.2f}")
        for ln in item["lines"]:
            if ln["credit"]:
                print(f"          Cr  {ln['code']} {ln['name']:<28}"
                      f"{ln['credit']:>12,.2f}")
        print()


def cmd_trial_balance(args):
    conn = _open(args)
    header = profile.profile_header_lines(conn)
    tb = reports.trial_balance(conn, start=args.start, end=args.end)
    print(formatting.format_trial_balance(tb, header))


def cmd_income(args):
    conn = _open(args)
    header = profile.profile_header_lines(conn)
    inc = reports.income_statement(conn, start=args.start, end=args.end)
    print(formatting.format_income_statement(
        inc, header, personal=profile.is_personal(conn)))


def cmd_balance_sheet(args):
    conn = _open(args)
    header = profile.profile_header_lines(conn)
    bs = reports.balance_sheet(conn, start=args.start, end=args.end)
    print(formatting.format_balance_sheet(bs, header))


def cmd_ledger(args):
    conn = _open(args)
    header = profile.profile_header_lines(conn)
    try:
        gl = reports.general_ledger(conn, start=args.start, end=args.end,
                                    account_code=args.account)
    except ValueError as e:
        raise SystemExit(f"Error: {e}")
    print(formatting.format_general_ledger(gl, header))


def cmd_business_info(args):
    """Show or update the business profile."""
    conn = _open(args)
    kind_arg = getattr(args, "kind", None)
    # If any field flag was given, this is an update; otherwise just show.
    updating = any(v is not None for v in
                   (args.name, args.address, args.contact, args.tagline,
                    kind_arg))
    if updating:
        current = profile.get_profile(conn)
        profile.save_profile(
            conn,
            name=args.name if args.name is not None else current["name"],
            address=(args.address if args.address is not None
                     else current["address"]),
            contact=(args.contact if args.contact is not None
                     else current["contact"]),
            tagline=(args.tagline if args.tagline is not None
                     else current["tagline"]),
            kind=kind_arg if kind_arg is not None else current["kind"],
        )
        print("Profile updated.")
    p = profile.get_profile(conn)
    use = "personal use" if p["kind"] == "personal" else "a business"
    print(f"\nProfile for this ledger (set up for {use}):")
    print(f"  Name:    {p['name'] or '(not set)'}")
    print(f"  Tagline: {p['tagline'] or '(not set)'}")
    print(f"  Address: {p['address'] or '(not set)'}")
    print(f"  Contact: {p['contact'] or '(not set)'}")


def cmd_about(args):
    """Show the program's attribution and version."""
    print(about.about_text())


def cmd_backup(args):
    db_path = args.db or database.DEFAULT_DB_PATH
    # --to lets you save the backup somewhere else (a USB drive, a
    # cloud-synced folder, etc.). Without it, the default is a folder named
    # for the business inside the Documents folder.
    backup_dir = args.to
    if backup_dir:
        try:
            dest = backup.backup(db_path=db_path, backup_dir=backup_dir)
        except FileNotFoundError as e:
            raise SystemExit(f"Error: {e}")
        except OSError as e:
            raise SystemExit(f"Error: could not save to '{backup_dir}': {e}")
        backup.remember_location(backup_dir)
        print(f"Backup saved to:\n  {dest}")
    else:
        # Default: Documents/Ledger Backups/<business name>/
        name = ""
        try:
            conn = database.connect(db_path)
            database.init_db(conn)
            name = profile.get_profile(conn)["name"]
        except Exception:
            name = ""
        if not name:
            name = os.path.splitext(os.path.basename(db_path))[0]
        target = backup.business_backup_dir(name)
        try:
            dest = backup.backup(db_path=db_path, backup_dir=target,
                                 create=True)
        except FileNotFoundError as e:
            raise SystemExit(f"Error: {e}")
        except OSError as e:
            raise SystemExit(f"Error: could not save to '{target}': {e}")
        print(f"Backup saved to:\n  {dest}")
        print("\nThis is on the same computer as your data (in your "
              "Documents).\nFor real safety, also back up to a USB drive "
              "or cloud folder: use  backup --to <folder>.")


def cmd_list_backups(args):
    backups = backup.list_backups()
    if not backups:
        print("No backups found yet. Run 'backup' to create one.")
        return
    print("Backups (newest first):")
    for path in backups:
        size_kb = os.path.getsize(path) / 1024
        print(f"  {path}  ({size_kb:.0f} KB)")


def cmd_restore(args):
    db_path = args.db or database.DEFAULT_DB_PATH
    try:
        restored_from, safety_copy = backup.restore(args.file, db_path=db_path)
    except FileNotFoundError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Restored your ledger from:\n  {restored_from}")
    if safety_copy:
        print(f"\nYour previous data was saved first, just in case, to:\n"
              f"  {safety_copy}")


# --------------------------------------------------------------------------
# argument parser
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="ledger",
        description="A small-business double-entry accounting tool.",
    )
    p.add_argument("--db", help="Path to ledger database "
                                "(default: ~/.ledger/ledger.db)")
    sub = p.add_subparsers(dest="command", required=True)

    # init
    s = sub.add_parser("init", help="Create the database and default "
                                    "chart of accounts.")
    s.set_defaults(func=cmd_init)

    # accounts
    s = sub.add_parser("accounts", help="List the chart of accounts.")
    s.add_argument("--all", action="store_true",
                   help="Include inactive accounts.")
    s.set_defaults(func=cmd_accounts)

    # add-account
    s = sub.add_parser("add-account", help="Add a new account.")
    s.add_argument("code", help="Account code, e.g. 6310")
    s.add_argument("name", help="Account name, e.g. 'Software Subscriptions'")
    s.add_argument("type", help="ASSET, LIABILITY, EQUITY, INCOME or EXPENSE")
    s.set_defaults(func=cmd_add_account)

    # rename-account
    s = sub.add_parser("rename-account", help="Rename an account.")
    s.add_argument("code")
    s.add_argument("name")
    s.set_defaults(func=cmd_rename_account)

    # deactivate-account
    s = sub.add_parser("deactivate-account",
                       help="Hide an account from normal listings.")
    s.add_argument("code")
    s.set_defaults(func=cmd_deactivate_account)

    # entry
    s = sub.add_parser("entry", help="Record a journal entry.")
    s.add_argument("--date", required=True, help="YYYY-MM-DD")
    s.add_argument("--desc", required=True, help="What the entry is for")
    s.add_argument("--debit", action="append", metavar="CODE:AMOUNT",
                   help="A debit leg, e.g. 6400:1500 (repeatable)")
    s.add_argument("--credit", action="append", metavar="CODE:AMOUNT",
                   help="A credit leg, e.g. 1000:1500 (repeatable)")
    s.add_argument("--ref", help="Optional reference (invoice/check number)")
    s.set_defaults(func=cmd_entry)

    # void
    s = sub.add_parser("void", help="Delete a journal entry by id.")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_void)

    # journal
    s = sub.add_parser("journal", help="List journal entries.")
    s.add_argument("--start", help="YYYY-MM-DD")
    s.add_argument("--end", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_journal)

    # trial-balance
    s = sub.add_parser("trial-balance", help="Trial balance report.")
    s.add_argument("--start", help="YYYY-MM-DD")
    s.add_argument("--end", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_trial_balance)

    # income
    s = sub.add_parser("income", help="Income statement (profit & loss).")
    s.add_argument("--start", help="YYYY-MM-DD")
    s.add_argument("--end", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_income)

    # balance-sheet
    s = sub.add_parser("balance-sheet", help="Balance sheet report.")
    s.add_argument("--start", help="YYYY-MM-DD (usually omitted)")
    s.add_argument("--end", help="YYYY-MM-DD (as-of date)")
    s.set_defaults(func=cmd_balance_sheet)

    # ledger
    s = sub.add_parser("ledger", help="General ledger detail.")
    s.add_argument("--account", help="Limit to one account code")
    s.add_argument("--start", help="YYYY-MM-DD")
    s.add_argument("--end", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_ledger)

    # backup
    s = sub.add_parser("backup",
                       help="Save a timestamped copy of your data.")
    s.add_argument("--to", metavar="FOLDER",
                   help="Save the backup to this folder instead of the "
                        "standard one (e.g. a USB drive or cloud folder)")
    s.set_defaults(func=cmd_backup)

    # backups (list)
    s = sub.add_parser("backups",
                       help="List all backup copies that have been made.")
    s.set_defaults(func=cmd_list_backups)

    # restore
    s = sub.add_parser("restore",
                       help="Restore your data from a backup copy.")
    s.add_argument("file", help="Path to the backup file to restore from "
                                "(see 'backups' for the list)")
    s.set_defaults(func=cmd_restore)

    # business-info
    s = sub.add_parser("business-info",
                       help="Show or update this ledger's business "
                            "profile (shown as a header on reports).")
    s.add_argument("--name", help="Set the business name")
    s.add_argument("--tagline", help="Set the tagline / slogan")
    s.add_argument("--address", help="Set the address")
    s.add_argument("--contact", help="Set the contact details")
    s.add_argument("--kind", choices=("business", "personal"),
                   help="Whether these books are for a business or for "
                        "personal use (only changes the wording shown)")
    s.set_defaults(func=cmd_business_info)

    # about
    s = sub.add_parser("about",
                       help="Show the program's version and attribution.")
    s.set_defaults(func=cmd_about)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
