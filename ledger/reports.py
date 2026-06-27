# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Financial reports.

These are the reports your tax expert will actually want:

    * Trial Balance   -- proves the books are in balance
    * Income Statement (Profit & Loss) -- did the business make money?
    * Balance Sheet   -- what the business owns and owes
    * General Ledger  -- every transaction, account by account

All reporting functions take an optional date range so you can produce,
for example, a full-year income statement or a single-quarter one.
"""

from .accounts import list_accounts


def _round(x):
    return round(float(x) + 1e-9, 2)


def _account_movements(conn, start=None, end=None):
    """
    Return a dict keyed by account id with summed debits and credits
    within the date range. The date filter applies to the journal
    entry date.
    """
    sql = """
        SELECT jl.account_id,
               SUM(jl.debit)  AS debit,
               SUM(jl.credit) AS credit
          FROM journal_lines jl
          JOIN journal_entries je ON je.id = jl.entry_id
    """
    params = []
    clauses = []
    if start:
        clauses.append("je.date >= ?")
        params.append(start)
    if end:
        clauses.append("je.date <= ?")
        params.append(end)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " GROUP BY jl.account_id"

    movements = {}
    for row in conn.execute(sql, params).fetchall():
        movements[row["account_id"]] = {
            "debit": _round(row["debit"] or 0),
            "credit": _round(row["credit"] or 0),
        }
    return movements


def trial_balance(conn, start=None, end=None):
    """
    Build a trial balance: every account with a non-zero balance, shown
    in its natural debit or credit column. Total debits must equal
    total credits -- if they do not, the books are broken.
    """
    movements = _account_movements(conn, start, end)
    rows = []
    total_debit = 0.0
    total_credit = 0.0

    for acct in list_accounts(conn, include_inactive=True):
        mv = movements.get(acct["id"])
        if not mv:
            continue
        net = _round(mv["debit"] - mv["credit"])
        if net == 0:
            continue
        # Positive net = debit-side balance; negative = credit-side.
        if net > 0:
            debit_col, credit_col = net, 0.0
            total_debit += net
        else:
            debit_col, credit_col = 0.0, -net
            total_credit += -net
        rows.append({
            "code": acct["code"],
            "name": acct["name"],
            "type": acct["type"],
            "debit": debit_col,
            "credit": credit_col,
        })

    return {
        "rows": rows,
        "total_debit": _round(total_debit),
        "total_credit": _round(total_credit),
        "balanced": _round(total_debit) == _round(total_credit),
        "start": start,
        "end": end,
    }


def income_statement(conn, start=None, end=None):
    """
    Income statement / Profit & Loss for the period.

    Net profit = total income - total expenses.
    Income accounts are credit-normal, expense accounts debit-normal,
    so each is shown as a positive "amount" the intuitive way.
    """
    movements = _account_movements(conn, start, end)
    income, expense = [], []
    total_income = 0.0
    total_expense = 0.0

    for acct in list_accounts(conn, include_inactive=True):
        mv = movements.get(acct["id"])
        if not mv:
            continue
        if acct["type"] == "INCOME":
            amount = _round(mv["credit"] - mv["debit"])
            if amount == 0:
                continue
            income.append({"code": acct["code"], "name": acct["name"],
                            "amount": amount})
            total_income += amount
        elif acct["type"] == "EXPENSE":
            amount = _round(mv["debit"] - mv["credit"])
            if amount == 0:
                continue
            expense.append({"code": acct["code"], "name": acct["name"],
                            "amount": amount})
            total_expense += amount

    total_income = _round(total_income)
    total_expense = _round(total_expense)
    return {
        "income": income,
        "expense": expense,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_income": _round(total_income - total_expense),
        "start": start,
        "end": end,
    }


def balance_sheet(conn, start=None, end=None):
    """
    Balance sheet as of the `end` date (the `start` date is accepted for
    interface symmetry but a balance sheet is cumulative, so normally
    only `end` matters; pass start=None to include all history).

    The fundamental equation that must hold:

        Assets = Liabilities + Equity

    Net income for the period that has not been closed into Retained
    Earnings is shown as "Current period net income" inside equity, so
    the statement always balances.
    """
    # Balance sheet is cumulative up to `end`; ignore `start`.
    movements = _account_movements(conn, None, end)
    assets, liabilities, equity = [], [], []
    total_assets = 0.0
    total_liabilities = 0.0
    total_equity = 0.0

    for acct in list_accounts(conn, include_inactive=True):
        mv = movements.get(acct["id"])
        if not mv:
            continue
        if acct["type"] == "ASSET":
            amount = _round(mv["debit"] - mv["credit"])
            if amount == 0:
                continue
            assets.append({"code": acct["code"], "name": acct["name"],
                           "amount": amount})
            total_assets += amount
        elif acct["type"] == "LIABILITY":
            amount = _round(mv["credit"] - mv["debit"])
            if amount == 0:
                continue
            liabilities.append({"code": acct["code"], "name": acct["name"],
                                "amount": amount})
            total_liabilities += amount
        elif acct["type"] == "EQUITY":
            amount = _round(mv["credit"] - mv["debit"])
            if amount == 0:
                continue
            equity.append({"code": acct["code"], "name": acct["name"],
                           "amount": amount})
            total_equity += amount

    # Income and expenses that have not been closed into equity still
    # belong to the owner -- fold them in as current-period net income.
    pnl = income_statement(conn, None, end)
    net_income = pnl["net_income"]
    if net_income != 0:
        equity.append({
            "code": "----",
            "name": "Current period net income",
            "amount": net_income,
        })
        total_equity += net_income

    total_assets = _round(total_assets)
    total_liabilities = _round(total_liabilities)
    total_equity = _round(total_equity)
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "total_liabilities_and_equity": _round(total_liabilities + total_equity),
        "balanced": total_assets == _round(total_liabilities + total_equity),
        "end": end,
    }


def general_ledger(conn, start=None, end=None, account_code=None):
    """
    The general ledger: for each account, a running list of every line
    that hit it within the date range, with a running balance.

    If `account_code` is given, only that account is returned.
    """
    accts = list_accounts(conn, include_inactive=True)
    if account_code:
        accts = [a for a in accts if a["code"] == account_code]
        if not accts:
            raise ValueError(f"No account with code '{account_code}'.")

    sql = """
        SELECT je.date, je.description, je.reference,
               jl.debit, jl.credit
          FROM journal_lines jl
          JOIN journal_entries je ON je.id = jl.entry_id
         WHERE jl.account_id = ?
    """
    base_params = []
    if start:
        sql += " AND je.date >= ?"
        base_params.append(start)
    if end:
        sql += " AND je.date <= ?"
        base_params.append(end)
    sql += " ORDER BY je.date, je.id"

    result = []
    for acct in accts:
        lines = conn.execute(sql, [acct["id"], *base_params]).fetchall()
        if not lines:
            continue
        running = 0.0
        movements = []
        sign = 1 if acct["normal_balance"] == "DEBIT" else -1
        for ln in lines:
            running += sign * (ln["debit"] - ln["credit"])
            movements.append({
                "date": ln["date"],
                "description": ln["description"],
                "reference": ln["reference"],
                "debit": _round(ln["debit"]),
                "credit": _round(ln["credit"]),
                "balance": _round(running),
            })
        result.append({
            "code": acct["code"],
            "name": acct["name"],
            "type": acct["type"],
            "normal_balance": acct["normal_balance"],
            "movements": movements,
            "ending_balance": _round(running),
        })
    return result


# ----------------------------------------------------------------------
# Bank reconciliation
# ----------------------------------------------------------------------
#
# Reconciliation compares what Ledger thinks happened in an account
# against what the bank statement says. It is deliberately framed in
# plain "money in / money out" terms rather than debits and credits, so
# someone learning the books can check it against a statement without
# having to think in accounting vocabulary.
#
# For each account it shows four numbers a bank statement also shows:
#
#     Beginning balance  +  Money in  -  Money out  =  Ending balance
#
# "Money in" is whatever increases the account, "money out" is whatever
# decreases it. For a normal bank account (an asset) money in is a
# deposit and money out is a withdrawal; for a liability it is the
# other way round. Either way the relationship above always holds, which
# is what lets the tool point at exactly which figure is off when a
# statement does not tie out.
#
# This is a READ-ONLY view. It never changes the books.


def reconciliation(conn, start=None, end=None):
    """
    Per-account reconciliation figures for asset and liability accounts.

    For each account returns the Ledger view of:
        beginning  -- balance carried INTO the period (before `start`)
        money_in   -- amounts that increased the account during the period
        money_out  -- amounts that decreased the account during the period
        ending     -- balance at the end of the period (== beginning + in - out)

    Balances are shown the natural way (a positive asset balance is
    money you have; a positive liability balance is money you owe), so
    they line up with what a bank or credit-card statement shows.

    The date range works like the other reports: `start`/`end` are
    inclusive ISO dates, and either may be omitted. With no `start`, the
    beginning balance is zero and the period covers everything up to
    `end` (i.e. reconciling from the very beginning of the books).
    """
    # Movements within the period being reconciled.
    period = _account_movements(conn, start, end)
    # Cumulative movements from the beginning of the books through `end`.
    # Subtracting the period from this leaves everything strictly BEFORE
    # `start` -- the balance carried into the period. This reuses the
    # same tested movement query rather than inventing new balance math.
    through_end = _account_movements(conn, None, end)

    out = []
    for acct in list_accounts(conn, include_inactive=False):
        if acct["type"] not in ("ASSET", "LIABILITY"):
            continue

        per = period.get(acct["id"], {"debit": 0.0, "credit": 0.0})
        cum = through_end.get(acct["id"], {"debit": 0.0, "credit": 0.0})

        before_debit = _round(cum["debit"] - per["debit"])
        before_credit = _round(cum["credit"] - per["credit"])

        # +1 for debit-normal accounts (assets), -1 for credit-normal
        # (liabilities). This is what turns raw debits/credits into the
        # intuitive "money in / money out" the user sees.
        sign = 1 if acct["normal_balance"] == "DEBIT" else -1

        beginning = _round(sign * (before_debit - before_credit))
        if sign > 0:
            money_in = _round(per["debit"])
            money_out = _round(per["credit"])
        else:
            money_in = _round(per["credit"])
            money_out = _round(per["debit"])
        ending = _round(beginning + money_in - money_out)

        out.append({
            "code": acct["code"],
            "name": acct["name"],
            "type": acct["type"],
            "normal_balance": acct["normal_balance"],
            "beginning": beginning,
            "money_in": money_in,
            "money_out": money_out,
            "ending": ending,
        })

    return {"accounts": out, "start": start, "end": end}


# The four comparable figures, in display order. Used by the comparison
# below and by the formatter, so the wording stays in one place.
RECON_FIELDS = (
    ("beginning", "Beginning balance"),
    ("money_in", "Money in"),
    ("money_out", "Money out"),
    ("ending", "Ending balance"),
)


def reconcile_against_statement(ledger, bank_inputs, tol=0.005):
    """
    Compare Ledger figures against the numbers a user typed in from
    their bank statement, and work out what matches.

    Parameters
    ----------
    ledger : dict
        The result of reconciliation() above.
    bank_inputs : dict
        Maps an account code to a dict of the statement figures the user
        entered, e.g. {"1100": {"beginning": 2000, "money_in": 500,
        "money_out": 300, "ending": 2200}}. Any field may be missing or
        None, meaning "the user left this box blank" -- blank fields are
        not counted for or against reconciliation.
    tol : float
        How close two numbers must be to count as matching (default half
        a cent, so ordinary rounding never causes a false mismatch).

    Returns
    -------
    dict with:
        rows          -- one entry per asset/liability account, each with
                         per-field ledger value, statement value (or
                         None), difference (statement - ledger, or None),
                         and a per-field `match` flag; plus `checked`
                         (did the user enter anything for this account?)
                         and `reconciled` (checked and every entered
                         field matches).
        n_checked     -- how many accounts the user entered figures for
        n_reconciled  -- how many of those fully reconcile
        start, end    -- echoed from the ledger data
    """
    rows = []
    n_checked = 0
    n_reconciled = 0

    for acct in ledger["accounts"]:
        entered = bank_inputs.get(acct["code"], {}) or {}
        fields = {}
        any_entered = False
        all_match = True

        for key, _label in RECON_FIELDS:
            ledger_val = acct[key]
            stmt_val = entered.get(key, None)
            if stmt_val is None or stmt_val == "":
                fields[key] = {
                    "ledger": ledger_val,
                    "statement": None,
                    "difference": None,
                    "match": None,
                }
                continue
            stmt_val = round(float(stmt_val) + 1e-9, 2)
            diff = round(stmt_val - ledger_val + 1e-9, 2)
            matched = abs(diff) < tol
            any_entered = True
            if not matched:
                all_match = False
            fields[key] = {
                "ledger": ledger_val,
                "statement": stmt_val,
                "difference": diff,
                "match": matched,
            }

        checked = any_entered
        reconciled = checked and all_match
        if checked:
            n_checked += 1
        if reconciled:
            n_reconciled += 1

        rows.append({
            "code": acct["code"],
            "name": acct["name"],
            "type": acct["type"],
            "fields": fields,
            "checked": checked,
            "reconciled": reconciled,
        })

    return {
        "rows": rows,
        "n_checked": n_checked,
        "n_reconciled": n_reconciled,
        "start": ledger.get("start"),
        "end": ledger.get("end"),
    }
