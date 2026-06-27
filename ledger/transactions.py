# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Journal entries -- the double-entry core of the system.

Every financial event is recorded as one journal entry made up of two
or more lines. The unbreakable rule of double-entry bookkeeping:

    total debits == total credits

for every single entry. This module refuses to record anything that
violates that rule, which is what keeps the books in balance and the
reports trustworthy.
"""

from datetime import date as _date

from .database import now_iso


class TransactionError(Exception):
    """Raised when a journal entry is invalid."""


def _validate_date(date_str):
    """Ensure the date is a real date in ISO (YYYY-MM-DD) format."""
    try:
        _date.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise TransactionError(
            f"Invalid date '{date_str}'. Use YYYY-MM-DD format."
        )
    return date_str


def _round(amount):
    """Round to cents. Money should never carry sub-cent noise."""
    return round(float(amount) + 1e-9, 2)


def add_entry(conn, date_str, description, lines, reference=None):
    """
    Record one journal entry.

    Parameters
    ----------
    date_str : str
        Date of the entry, 'YYYY-MM-DD'.
    description : str
        Plain-language description ("Pay January rent").
    lines : list of dict
        Each dict is {'code': <account code>, 'debit': x, 'credit': y}.
        Each line must have a positive amount on exactly one side.
    reference : str, optional
        Invoice number, check number, etc.

    Returns
    -------
    int
        The id of the new journal entry.
    """
    date_str = _validate_date(date_str)
    description = (description or "").strip()
    if not description:
        raise TransactionError("Entry description cannot be empty.")
    if not lines or len(lines) < 2:
        raise TransactionError(
            "An entry needs at least two lines (one debit and one credit)."
        )

    total_debit = 0.0
    total_credit = 0.0
    resolved = []

    for i, line in enumerate(lines, start=1):
        code = str(line.get("code", "")).strip()
        debit = _round(line.get("debit", 0) or 0)
        credit = _round(line.get("credit", 0) or 0)

        if debit < 0 or credit < 0:
            raise TransactionError(f"Line {i}: amounts cannot be negative.")
        if debit > 0 and credit > 0:
            raise TransactionError(
                f"Line {i}: a line is either a debit or a credit, not both."
            )
        if debit == 0 and credit == 0:
            raise TransactionError(f"Line {i}: line has no amount.")

        acct = conn.execute(
            "SELECT * FROM accounts WHERE code = ?", (code,)
        ).fetchone()
        if not acct:
            raise TransactionError(f"Line {i}: no account with code '{code}'.")
        if not acct["active"]:
            raise TransactionError(
                f"Line {i}: account '{code}' ({acct['name']}) is inactive."
            )

        total_debit += debit
        total_credit += credit
        resolved.append((acct["id"], debit, credit))

    total_debit = _round(total_debit)
    total_credit = _round(total_credit)

    # The rule that makes it double-entry:
    if total_debit != total_credit:
        raise TransactionError(
            f"Entry does not balance: debits {total_debit:.2f} "
            f"!= credits {total_credit:.2f}."
        )

    cur = conn.execute(
        "INSERT INTO journal_entries (date, description, reference, created_at) "
        "VALUES (?, ?, ?, ?)",
        (date_str, description, reference, now_iso()),
    )
    entry_id = cur.lastrowid
    for account_id, debit, credit in resolved:
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, debit, credit) "
            "VALUES (?, ?, ?, ?)",
            (entry_id, account_id, debit, credit),
        )
    conn.commit()
    return entry_id


def void_entry(conn, entry_id):
    """
    Delete a journal entry and its lines. Use sparingly -- in a real
    bookkeeping workflow you would usually post a reversing entry
    instead so the history is preserved. This is here for fixing
    plain data-entry mistakes before they reach your tax expert.
    """
    entry = conn.execute(
        "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not entry:
        raise TransactionError(f"No journal entry with id {entry_id}.")
    conn.execute("DELETE FROM journal_lines WHERE entry_id = ?", (entry_id,))
    conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
    conn.commit()


def list_entries(conn, start=None, end=None):
    """Return journal entries within an optional date range, with their
    lines attached. Newest entries first."""
    sql = "SELECT * FROM journal_entries"
    params = []
    clauses = []
    if start:
        clauses.append("date >= ?")
        params.append(_validate_date(start))
    if end:
        clauses.append("date <= ?")
        params.append(_validate_date(end))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date DESC, id DESC"

    entries = []
    for entry in conn.execute(sql, params).fetchall():
        lines = conn.execute(
            """SELECT jl.debit, jl.credit, a.code, a.name, a.type
                 FROM journal_lines jl
                 JOIN accounts a ON a.id = jl.account_id
                WHERE jl.entry_id = ?
                ORDER BY jl.debit DESC""",
            (entry["id"],),
        ).fetchall()
        entries.append({"entry": entry, "lines": lines})
    return entries
