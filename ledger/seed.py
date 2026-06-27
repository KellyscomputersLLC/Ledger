# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Default chart of accounts for a small business.

This is a deliberately general-purpose chart that fits most service and
light-product businesses. Account codes follow the standard convention:

    1000-1999  Assets
    2000-2999  Liabilities
    3000-3999  Equity
    4000-4999  Income
    5000-5999  Cost of goods sold
    6000-6999  Operating expenses

You can add, rename, or deactivate accounts later with the `account`
commands -- but it is best to settle the chart with your tax expert
before you enter a lot of transactions.
"""

# Each tuple: (code, name, type)
# normal_balance is derived from type in seed_accounts() below.
DEFAULT_ACCOUNTS = [
    # --- Assets ---
    ("1000", "Checking Account",            "ASSET"),
    ("1010", "Savings Account",             "ASSET"),
    ("1050", "Petty Cash",                  "ASSET"),
    ("1200", "Accounts Receivable",         "ASSET"),
    ("1500", "Equipment",                   "ASSET"),
    ("1510", "Furniture & Fixtures",        "ASSET"),
    ("1600", "Accumulated Depreciation",    "ASSET"),

    # --- Liabilities ---
    ("2000", "Accounts Payable",            "LIABILITY"),
    ("2100", "Credit Card Payable",         "LIABILITY"),
    ("2200", "Sales Tax Payable",           "LIABILITY"),
    ("2300", "Payroll Liabilities",         "LIABILITY"),
    ("2500", "Loans Payable",               "LIABILITY"),

    # --- Equity ---
    ("3000", "Owner's Capital",             "EQUITY"),
    ("3100", "Owner's Draw",                "EQUITY"),
    ("3900", "Retained Earnings",           "EQUITY"),

    # --- Income ---
    ("4000", "Sales Revenue",               "INCOME"),
    ("4100", "Service Revenue",             "INCOME"),
    ("4900", "Other Income",                "INCOME"),

    # --- Cost of goods sold ---
    ("5000", "Cost of Goods Sold",          "EXPENSE"),
    ("5100", "Merchant & Payment Fees",     "EXPENSE"),

    # --- Operating expenses ---
    ("6000", "Advertising & Marketing",     "EXPENSE"),
    ("6100", "Bank Fees",                   "EXPENSE"),
    ("6200", "Insurance",                   "EXPENSE"),
    ("6300", "Office Supplies",             "EXPENSE"),
    ("6400", "Rent",                        "EXPENSE"),
    ("6500", "Utilities",                   "EXPENSE"),
    ("6600", "Wages & Salaries",            "EXPENSE"),
    ("6700", "Professional Fees",           "EXPENSE"),
    ("6800", "Travel",                      "EXPENSE"),
    ("6900", "Meals",                       "EXPENSE"),
    ("6950", "Vehicle Expenses",            "EXPENSE"),
    ("6970", "Repairs & Maintenance",       "EXPENSE"),
    ("6980", "Depreciation Expense",        "EXPENSE"),
    ("6990", "Miscellaneous Expense",       "EXPENSE"),
]

# Which side an account type normally sits on.
NORMAL_BALANCE = {
    "ASSET":     "DEBIT",
    "LIABILITY": "CREDIT",
    "EQUITY":    "CREDIT",
    "INCOME":    "CREDIT",
    "EXPENSE":   "DEBIT",
}


def seed_accounts(conn):
    """
    Insert the default chart of accounts. Existing accounts (matched by
    code) are left untouched, so this is safe to run more than once.
    Returns the number of accounts actually inserted.
    """
    inserted = 0
    for code, name, acct_type in DEFAULT_ACCOUNTS:
        exists = conn.execute(
            "SELECT 1 FROM accounts WHERE code = ?", (code,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO accounts (code, name, type, normal_balance, active) "
            "VALUES (?, ?, ?, ?, 1)",
            (code, name, acct_type, NORMAL_BALANCE[acct_type]),
        )
        inserted += 1
    conn.commit()
    return inserted
