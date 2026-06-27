# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Plain-text formatting for reports.

Kept separate from reports.py so the report functions return pure data
(easy to test, easy to repurpose into CSV or HTML later) while this
module handles turning that data into something readable in a terminal
or a file you can hand to your tax expert.
"""

WIDTH = 64


def _money(x):
    """Format a number as money with thousands separators."""
    return f"{x:,.2f}"


def _line(char="-", width=None):
    return char * (width if width is not None else WIDTH)


def _period(start, end):
    if start and end:
        return f"{start} to {end}"
    if end:
        return f"through {end}"
    if start:
        return f"from {start}"
    return "all dates"


def _business_header(header_lines, width=None):
    """
    Render the business profile lines as a centered block to sit at the
    very top of a report. `header_lines` is the list returned by
    profile.profile_header_lines(); if it is empty, this returns an
    empty list so the report simply has no business header.
    """
    if not header_lines:
        return []
    w = width if width is not None else WIDTH
    block = []
    for line in header_lines:
        block.append(str(line).center(w))
    block.append("")  # a blank line between the business block and the report
    return block


def format_trial_balance(tb, header_lines=None):
    out = []
    out.extend(_business_header(header_lines))
    out.append(_line("="))
    out.append("TRIAL BALANCE".center(WIDTH))
    out.append(_period(tb["start"], tb["end"]).center(WIDTH))
    out.append(_line("="))
    out.append(f"{'Account':<34}{'Debit':>14}{'Credit':>16}")
    out.append(_line())
    for r in tb["rows"]:
        label = f"{r['code']} {r['name']}"
        debit = _money(r["debit"]) if r["debit"] else ""
        credit = _money(r["credit"]) if r["credit"] else ""
        out.append(f"{label:<34}{debit:>14}{credit:>16}")
    out.append(_line())
    out.append(f"{'TOTALS':<34}{_money(tb['total_debit']):>14}"
               f"{_money(tb['total_credit']):>16}")
    out.append(_line("="))
    status = "IN BALANCE" if tb["balanced"] else "*** OUT OF BALANCE ***"
    out.append(status.center(WIDTH))
    return "\n".join(out)


def format_income_statement(inc, header_lines=None, personal=False):
    out = []
    out.extend(_business_header(header_lines))
    out.append(_line("="))
    out.append("INCOME STATEMENT".center(WIDTH))
    # "Profit & Loss" is the business term; for personal books the
    # friendlier "Income & Expenses" reads better and means the same.
    subtitle = "(Income & Expenses)" if personal else "(Profit & Loss)"
    out.append(subtitle.center(WIDTH))
    out.append(_period(inc["start"], inc["end"]).center(WIDTH))
    out.append(_line("="))

    out.append("INCOME")
    for r in inc["income"]:
        out.append(f"  {r['code']} {r['name']:<40}{_money(r['amount']):>16}")
    out.append(f"{'  Total Income':<48}{_money(inc['total_income']):>16}")
    out.append("")

    out.append("EXPENSES")
    for r in inc["expense"]:
        out.append(f"  {r['code']} {r['name']:<40}{_money(r['amount']):>16}")
    out.append(f"{'  Total Expenses':<48}{_money(inc['total_expense']):>16}")
    out.append(_line())

    label = "NET INCOME" if inc["net_income"] >= 0 else "NET LOSS"
    out.append(f"{label:<48}{_money(inc['net_income']):>16}")
    out.append(_line("="))
    return "\n".join(out)


def format_balance_sheet(bs, header_lines=None):
    out = []
    out.extend(_business_header(header_lines))
    out.append(_line("="))
    out.append("BALANCE SHEET".center(WIDTH))
    out.append((f"as of {bs['end']}" if bs["end"] else "as of today").center(WIDTH))
    out.append(_line("="))

    out.append("ASSETS")
    for r in bs["assets"]:
        out.append(f"  {r['code']} {r['name']:<40}{_money(r['amount']):>16}")
    out.append(f"{'  Total Assets':<48}{_money(bs['total_assets']):>16}")
    out.append("")

    out.append("LIABILITIES")
    for r in bs["liabilities"]:
        out.append(f"  {r['code']} {r['name']:<40}{_money(r['amount']):>16}")
    out.append(f"{'  Total Liabilities':<48}{_money(bs['total_liabilities']):>16}")
    out.append("")

    out.append("EQUITY")
    for r in bs["equity"]:
        out.append(f"  {r['code']} {r['name']:<40}{_money(r['amount']):>16}")
    out.append(f"{'  Total Equity':<48}{_money(bs['total_equity']):>16}")
    out.append(_line())

    out.append(f"{'TOTAL LIABILITIES & EQUITY':<48}"
               f"{_money(bs['total_liabilities_and_equity']):>16}")
    out.append(_line("="))
    status = "IN BALANCE" if bs["balanced"] else "*** OUT OF BALANCE ***"
    out.append(status.center(WIDTH))
    return "\n".join(out)


def format_general_ledger(gl, header_lines=None):
    # The general ledger is a five-column report (date, description, debit,
    # credit, running balance), so it uses a wider layout than the other
    # reports -- with money columns sized for real business amounts -- and its
    # own separators at that width, so the balance column always ends flush
    # with the lines instead of running past them.
    w = 80  # 11 + 29 + 13 + 13 + 14; money columns leave a gap even at 7 figures
    out = []
    out.extend(_business_header(header_lines, w))
    out.append(_line("=", w))
    out.append("GENERAL LEDGER".center(w))
    out.append(_line("=", w))
    if not gl:
        out.append("(no activity)".center(w))
        return "\n".join(out)
    for acct in gl:
        out.append("")
        out.append(f"{acct['code']} {acct['name']}  [{acct['type']}]")
        out.append(_line("-", w))
        out.append(f"{'Date':<11}{'Description':<29}{'Debit':>13}"
                   f"{'Credit':>13}{'Balance':>14}")
        for m in acct["movements"]:
            desc = m["description"][:28]
            debit = _money(m["debit"]) if m["debit"] else ""
            credit = _money(m["credit"]) if m["credit"] else ""
            out.append(f"{m['date']:<11}{desc:<29}{debit:>13}"
                       f"{credit:>13}{_money(m['balance']):>14}")
        out.append(f"{'Ending balance':<66}"
                   f"{_money(acct['ending_balance']):>14}")
    out.append(_line("=", w))
    return "\n".join(out)


def format_reconciliation(compared, header_lines=None):
    """
    Render a reconciliation comparison as plain text for saving and
    handing to a tax expert.

    `compared` is the result of
    reports.reconcile_against_statement(). Only accounts the user
    actually entered statement figures for are shown. The output is
    intentionally ASCII-only so the saved file opens cleanly on Windows
    as well as Linux.
    """
    from datetime import date

    out = []
    out.extend(_business_header(header_lines))
    out.append(_line("="))
    out.append("BANK RECONCILIATION".center(WIDTH))
    out.append(_period(compared.get("start"), compared.get("end")).center(WIDTH))
    out.append(_line("="))

    checked_rows = [r for r in compared["rows"] if r["checked"]]
    if not checked_rows:
        out.append("")
        out.append("No statement figures were entered, so there is "
                   "nothing to".center(WIDTH))
        out.append("reconcile yet. Enter your bank statement numbers "
                   "first.".center(WIDTH))
        out.append("")
        out.append(_line("="))
        return "\n".join(out)

    for r in checked_rows:
        status = "reconciled" if r["reconciled"] else "NOT reconciled"
        out.append("")
        out.append(f"{r['code']}  {r['name']}")
        out.append(f"  Status: {status}")
        out.append("  " + _line()[2:])
        out.append(f"  {'':<19}{'Ledger':>13}{'Statement':>13}"
                   f"{'Difference':>13}")
        for key, label in [("beginning", "Beginning balance"),
                           ("money_in", "Money in"),
                           ("money_out", "Money out"),
                           ("ending", "Ending balance")]:
            f = r["fields"][key]
            ledger = _money(f["ledger"])
            if f["statement"] is None:
                stmt = "--"
                diff = ""
                flag = ""
            else:
                stmt = _money(f["statement"])
                diff = _money(f["difference"])
                flag = "" if f["match"] else "   <-- differs"
            out.append(f"  {label:<19}{ledger:>13}{stmt:>13}{diff:>13}{flag}")

    out.append("")
    out.append(_line("="))
    out.append(f"Reconciled: {compared['n_reconciled']} of "
               f"{compared['n_checked']} account(s) checked.")
    out.append(f"Run on {date.today().isoformat()}.")
    out.append(_line("="))
    return "\n".join(out)
