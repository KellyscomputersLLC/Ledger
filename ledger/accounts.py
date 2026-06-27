# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Chart of accounts management.

Functions for looking at and maintaining the list of accounts. The
chart of accounts is the backbone of the whole system: every journal
line points at one of these accounts.
"""

from .seed import NORMAL_BALANCE

VALID_TYPES = set(NORMAL_BALANCE.keys())


class AccountError(Exception):
    """Raised when an account operation is invalid."""


def list_accounts(conn, include_inactive=False):
    """Return all accounts ordered by code."""
    sql = "SELECT * FROM accounts"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY code"
    return conn.execute(sql).fetchall()


def get_account(conn, code):
    """Look up a single account by its code. Returns a Row or None."""
    return conn.execute(
        "SELECT * FROM accounts WHERE code = ?", (code,)
    ).fetchone()


def add_account(conn, code, name, acct_type):
    """
    Add a new account to the chart. `acct_type` must be one of
    ASSET, LIABILITY, EQUITY, INCOME, EXPENSE. The normal balance is
    derived automatically from the type.
    """
    acct_type = acct_type.upper().strip()
    code = code.strip()
    name = name.strip()

    if acct_type not in VALID_TYPES:
        raise AccountError(
            f"Invalid account type '{acct_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_TYPES))}"
        )
    if not code:
        raise AccountError("Account code cannot be empty.")
    if not name:
        raise AccountError("Account name cannot be empty.")
    if get_account(conn, code):
        raise AccountError(f"Account code '{code}' already exists.")

    conn.execute(
        "INSERT INTO accounts (code, name, type, normal_balance, active) "
        "VALUES (?, ?, ?, ?, 1)",
        (code, name, acct_type, NORMAL_BALANCE[acct_type]),
    )
    conn.commit()


def set_account_active(conn, code, active):
    """Activate or deactivate an account. Deactivated accounts are
    hidden from normal listings but their history is preserved."""
    acct = get_account(conn, code)
    if not acct:
        raise AccountError(f"No account with code '{code}'.")
    conn.execute(
        "UPDATE accounts SET active = ? WHERE code = ?",
        (1 if active else 0, code),
    )
    conn.commit()


def rename_account(conn, code, new_name):
    """Change an account's display name. Code and type are unchanged."""
    acct = get_account(conn, code)
    if not acct:
        raise AccountError(f"No account with code '{code}'.")
    new_name = new_name.strip()
    if not new_name:
        raise AccountError("Account name cannot be empty.")
    conn.execute(
        "UPDATE accounts SET name = ? WHERE code = ?", (new_name, code)
    )
    conn.commit()
