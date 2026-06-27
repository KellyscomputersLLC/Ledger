# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
The service layer -- the single doorway every data operation passes through.

Each call carries a `Session` (who is acting and what role they hold). The
service checks `roles.can(...)` BEFORE doing anything and writes an audit entry
AFTER, so authorization and accountability live in one place instead of being
scattered through the screens.

This is also the seam that makes the host/client model work later. On one
computer the service runs locally against the open book. In the host/client
model the *host* runs this very same service, and a client simply sends
requests to it -- so a client (an employee's computer) cannot get around these
checks, because the checks, the data, and the key all live on the host.

This first part covers user administration -- adding people, resetting
passwords, changing roles, removing people -- which ties together the user
records (users.py, in the encrypted book) and the login secrets (the vault
slots, crypto.py). Accounting operations will be routed through the same
`authorize` gate as each screen is connected up.
"""

from . import roles, users, crypto

MIN_PASSWORD_LEN = 8

# How long a password is good for on a shared (multi-user) book before the
# person is required to set a new one at sign-in. Three months.
PASSWORD_MAX_AGE_DAYS = 90


class NotAllowed(Exception):
    """Raised when the acting user's role does not permit an operation."""


class Session:
    """Who is acting on a set of books, and the handles needed to act.

    For a local (single-computer) session these all point at the open book.
    In the host/client model the host builds a Session like this for each
    request it serves.
    """

    def __init__(self, conn, username, role,
                 vault=None, data_key=None, db_path=None):
        self.conn = conn
        self.username = users.normalize_username(username)
        self.role = role
        self.vault = vault
        self.data_key = data_key
        self.db_path = db_path

    def can(self, action):
        return roles.can(self.role, action)


def is_multiuser_vault(vault):
    """True if this book uses username logins (multi-user). Readable from the
    vault file before the book is unlocked, so the program knows whether to
    show a username login or a single passphrase prompt."""
    return bool(vault.get("multiuser")) if vault else False


def find_owner_username(conn):
    """The username of an owner (the first active one), or None. Used to
    pre-fill the sign-in screen so the owner is never left guessing their
    username."""
    for u in users.list_users(conn, include_inactive=False):
        if u["role"] == roles.OWNER:
            return u["username"]
    return None


def authorize(session, action):
    """The gate. Raise NotAllowed unless the session's role permits `action`.
    Every privileged operation calls this first."""
    if not roles.can(session.role, action):
        raise NotAllowed(
            "A %s is not allowed to do this." % roles.label(session.role))


def _check_password(password):
    if password is None or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(
            "A password must be at least %d characters." % MIN_PASSWORD_LEN)


def _save_vault(session):
    if session.vault is None or session.db_path is None:
        raise RuntimeError("This session has no vault to update.")
    crypto.save_vault(session.db_path, session.vault)


# --- switching a single-owner book into multi-user mode --------------------

def enable_multiuser(session, owner_passphrase, owner_username,
                     display_name=""):
    """Turn a single-owner business book into a multi-user one.

    Registers the current owner as the first user under a username of their
    choice and makes their login slot match that username. The owner's
    passphrase is required (to re-wrap their login slot under the new
    username). After this, the book uses username logins.
    """
    if users.multiuser_enabled(session.conn):
        raise ValueError("These books already use multiple users.")
    if session.vault is None or session.data_key is None:
        raise RuntimeError("Multi-user needs an unlocked, protected book.")
    if not crypto.verify(session.vault, owner_passphrase):
        raise ValueError("That passphrase is not correct.")
    uname = users.normalize_username(owner_username)
    if not users.is_valid_username(uname):
        raise ValueError(
            "A username must be 1-32 characters: letters, numbers, and "
            ". _ - only.")

    users.create_user(session.conn, uname, roles.OWNER,
                      display_name=display_name, created_by=uname)
    # Make the login slot match the chosen username. A new book's owner slot
    # is labelled "owner"; if they chose a different username, add a slot
    # under it (same passphrase) and drop the old one.
    if uname != "owner":
        crypto.add_slot(session.vault, session.data_key, owner_passphrase,
                        uname, "user")
        crypto.remove_slot(session.vault, "owner")
    # Flag the vault as multi-user so the program knows to ask for a username
    # login next time, before it can open the (encrypted) book to read the
    # user list. These hold no secret (usernames are already slot labels).
    session.vault["multiuser"] = True
    session.vault["owner_username"] = uname
    _save_vault(session)
    # The acting session is now this owner.
    session.username = uname
    session.role = roles.OWNER
    users.log_action(session.conn, uname, "enable_multiuser", "")
    return uname


# --- managing people (owner only) ------------------------------------------

def add_user(session, username, role, password, display_name="",
             must_change=False):
    """Add a person: a user record (role) plus a login slot (password).
    Owner only. Rolls back the record if the login slot can't be saved, so a
    half-made account is never left behind.

    `must_change` requires the person to set their own password the first time
    they sign in (used with a generated one-time password)."""
    authorize(session, roles.MANAGE_USERS)
    _check_password(password)
    uname = users.normalize_username(username)
    # create_user validates the username/role and refuses duplicates.
    users.create_user(session.conn, uname, role,
                      display_name=display_name, created_by=session.username,
                      must_change=must_change)
    try:
        crypto.add_slot(session.vault, session.data_key, password, uname,
                        "user")
        _save_vault(session)
    except Exception:
        # Undo the record so we don't leave a user who cannot log in.
        try:
            session.conn.execute("DELETE FROM users WHERE username = ?",
                                 (uname,))
            session.conn.commit()
        except Exception:
            pass
        raise
    users.log_action(session.conn, session.username, "add_user",
                     "%s as %s" % (uname, role))
    return uname


def reset_password(session, username, new_password, must_change=False):
    """Set a new password for someone. An owner may reset anyone; a manager may
    reset a *staff* member's password -- to help an employee back into their
    account -- but not an owner's or another manager's. No old password is
    needed, because the session holds the data key. `must_change` requires them
    to set their own password at next sign-in (used with a generated one-time
    password). The reset is recorded in the audit log against whoever did it."""
    authorize(session, roles.RESET_PASSWORD)
    uname = users.normalize_username(username)
    target = users.get_user(session.conn, uname)
    if target is None:
        raise ValueError("No such user: %r" % uname)
    # A manager (anyone without full user management) is limited to staff
    # accounts. Fail closed if the target is an owner or another manager.
    if not roles.can(session.role, roles.MANAGE_USERS):
        if target.get("role") != roles.STAFF:
            raise NotAllowed(
                "A manager can reset a staff member's password, but not an "
                "owner's or another manager's.")
    _check_password(new_password)
    crypto.change_secret(session.vault, session.data_key, uname,
                         new_password, slot_type="user")
    _save_vault(session)
    users.set_must_change(session.conn, uname, must_change)
    users.stamp_password_set(session.conn, uname)
    users.log_action(session.conn, session.username, "reset_password", uname)


def change_role(session, username, role):
    """Change someone's role (owner only). The last owner is protected by
    users.set_role."""
    authorize(session, roles.MANAGE_USERS)
    users.set_role(session.conn, username, role)
    users.log_action(session.conn, session.username, "change_role",
                     "%s -> %s" % (users.normalize_username(username), role))


def set_active(session, username, active):
    """Activate or deactivate a person (owner only). Deactivating keeps their
    history and their record; the login flow refuses inactive users. To fully
    revoke access (remove their login slot), use remove_user."""
    authorize(session, roles.MANAGE_USERS)
    users.set_active(session.conn, username, active)
    users.log_action(session.conn, session.username,
                     "activate" if active else "deactivate",
                     users.normalize_username(username))


def remove_user(session, username):
    """Remove a person entirely (owner only): delete their record and their
    login slot, so their password no longer opens the books. The last owner
    is protected by users.delete_user."""
    authorize(session, roles.MANAGE_USERS)
    uname = users.normalize_username(username)
    users.delete_user(session.conn, uname)        # refuses the last owner
    crypto.remove_slot(session.vault, uname)
    _save_vault(session)
    users.log_action(session.conn, session.username, "remove_user", uname)


# --- self-service ----------------------------------------------------------

def change_own_password(session, old_password, new_password):
    """A logged-in user changes their own password. Requires their current
    password as a confirmation. Any role may do this for their own account."""
    if not crypto.verify(session.vault, old_password):
        raise ValueError("Your current password is not correct.")
    _check_password(new_password)
    crypto.change_secret(session.vault, session.data_key, session.username,
                         new_password, slot_type="user")
    _save_vault(session)
    users.stamp_password_set(session.conn, session.username)
    users.log_action(session.conn, session.username, "change_own_password", "")


def complete_first_login(session, new_password):
    """Set the signed-in user's own password and clear the 'must change'
    flag. Called when someone who was given a one-time password signs in for
    the first time. No old password is required -- they have just proved who
    they are by signing in -- but the new one must meet the minimum length."""
    _check_password(new_password)
    crypto.change_secret(session.vault, session.data_key, session.username,
                         new_password, slot_type="user")
    _save_vault(session)
    users.set_must_change(session.conn, session.username, False)
    users.stamp_password_set(session.conn, session.username)
    users.log_action(session.conn, session.username,
                     "first_login_password_set", "")


def password_change_required(session):
    """For a shared (multi-user) book, decide whether the signed-in user must
    set a new password before working. Returns:
        'first_login' -- they have a one-time password not yet replaced
        'expired'     -- their password is older than PASSWORD_MAX_AGE_DAYS
        None          -- no change needed (or no session: personal/single-owner
                         books have no per-user passwords).
    """
    if session is None or getattr(session, "username", None) is None:
        return None
    try:
        if not users.multiuser_enabled(session.conn):
            return None
        user = users.get_user(session.conn, session.username)
    except Exception:
        return None
    if not user:
        return None
    if user.get("must_change_pw"):
        return "first_login"
    age = users.password_age_days(session.conn, session.username)
    if age is not None and age >= PASSWORD_MAX_AGE_DAYS:
        return "expired"
    return None


# --- reading (gated where appropriate) -------------------------------------

def list_people(session):
    """List the users on these books. Visible to anyone who can manage users
    or view the audit log; otherwise just the caller's own entry."""
    if session.can(roles.MANAGE_USERS) or session.can(roles.VIEW_AUDIT):
        return users.list_users(session.conn)
    me = users.get_user(session.conn, session.username)
    return [me] if me else []


def view_audit(session, limit=200):
    """The audit log, for roles allowed to see it (owner and manager)."""
    authorize(session, roles.VIEW_AUDIT)
    return users.list_audit(session.conn, limit=limit)
