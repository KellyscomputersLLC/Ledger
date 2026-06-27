# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Who is allowed to do what, for business books shared by more than one person.

This module is deliberately just a table and a lookup -- no database, no
network, no secrets -- so the rules are easy to read, easy to test, and easy
to change in one place.

IMPORTANT, and stated plainly: on a single shared computer these roles are
enforced by the application only. Anyone who can log in holds the same data
key once unlocked, so a determined, technically capable user could bypass
these checks. On a single machine, roles guard against *accidents* and give an
audit trail of who did what -- not against a determined insider. Real
enforcement (where an employee's computer never holds the data or the key)
comes with the host/client model, where the host runs these same checks on its
side and a client cannot get around them.
"""

# --- the three roles -------------------------------------------------------

OWNER = "owner"
MANAGER = "manager"
STAFF = "staff"

ROLES = (OWNER, MANAGER, STAFF)

_LABELS = {OWNER: "Owner", MANAGER: "Manager", STAFF: "Staff"}

_DESCRIPTIONS = {
    OWNER: "Full control, including managing people and the books themselves.",
    MANAGER: "Day-to-day bookkeeping and reports; can reset staff passwords, "
             "but cannot add, remove, or re-role people.",
    STAFF: "Record entries and view reports.",
}


# --- the things a person might be allowed to do ----------------------------

RECORD_ENTRY = "record_entry"          # add a journal entry
VOID_ENTRY = "void_entry"              # void/reverse an entry
VIEW_JOURNAL = "view_journal"          # see the journal
VIEW_REPORTS = "view_reports"          # trial balance, P&L, balance sheet, GL
RECONCILE = "reconcile"                # bank reconciliation
MANAGE_ACCOUNTS = "manage_accounts"    # add / edit / deactivate accounts
EDIT_PROFILE = "edit_profile"          # business info shown on reports
MAKE_BACKUP = "make_backup"            # create a backup
RESTORE_BACKUP = "restore_backup"      # overwrite the books from a backup
MANAGE_PROTECTION = "manage_protection"  # turn encryption on / off
MANAGE_USERS = "manage_users"          # add / remove / re-role people
RESET_PASSWORD = "reset_password"      # reset a password (no old one needed)
VIEW_AUDIT = "view_audit"              # read the audit log

ALL_ACTIONS = (
    RECORD_ENTRY, VOID_ENTRY, VIEW_JOURNAL, VIEW_REPORTS, RECONCILE,
    MANAGE_ACCOUNTS, EDIT_PROFILE, MAKE_BACKUP, RESTORE_BACKUP,
    MANAGE_PROTECTION, MANAGE_USERS, RESET_PASSWORD, VIEW_AUDIT,
)


# --- the matrix ------------------------------------------------------------
#
# Owner can do everything. Manager runs the books day to day and can reset a
# staff member's password to help an employee back into their account, but
# cannot otherwise manage people (add / remove / re-role), restore over the
# books, or turn protection off. Staff record entries and look at reports.
# Change these sets to change the policy; nothing else in the program
# hard-codes who-can-do-what.

_MATRIX = {
    OWNER: set(ALL_ACTIONS),
    MANAGER: {
        RECORD_ENTRY, VOID_ENTRY, VIEW_JOURNAL, VIEW_REPORTS, RECONCILE,
        MANAGE_ACCOUNTS, EDIT_PROFILE, MAKE_BACKUP, VIEW_AUDIT,
        RESET_PASSWORD,
    },
    STAFF: {
        RECORD_ENTRY, VIEW_JOURNAL, VIEW_REPORTS,
    },
}


def can(role, action):
    """True if `role` is allowed to do `action`. Unknown roles can do
    nothing (fail closed)."""
    return action in _MATRIX.get(role, set())


def is_valid_role(role):
    return role in ROLES


def label(role):
    """A friendly, capitalised name for a role."""
    return _LABELS.get(role, str(role).title())


def description(role):
    return _DESCRIPTIONS.get(role, "")


def assignable_roles():
    """Roles an owner may hand out. (Owner is included so an owner can promote
    someone to owner; the application decides whether to allow removing the
    last owner.)"""
    return list(ROLES)
