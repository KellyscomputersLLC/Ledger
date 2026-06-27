# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
The gateway seam (Phase 3, Slice 1).

The GUI needs to perform the same operations -- list accounts, record an
entry, void an entry, read the journal, view the audit log -- whether the
books are open ON THIS COMPUTER or live on a HOST that this computer connects
to as a client. A gateway is the single interface that hides that difference:

    LocalGateway   runs each operation directly against a local open book.
    RemoteGateway  performs each operation on the host, over the network,
                   via a HostClient.

Both return the SAME shapes (plain dicts and lists), so a tab written against
the gateway works in either mode without knowing which it is in. Where an
operation cannot be done, both raise GatewayError with a short `code`, so the
GUI handles failures the same way in both modes.

Enforcement note. RemoteGateway is enforced by the host: the host runs the
role checks and a client physically cannot do what its role forbids. The local
gateway does not re-check roles -- on a single computer the data and key are
right there, so enforcement is the GUI graying out controls (as it already
does), plus the audit log for accountability. This matches the honest model
we've used throughout: real enforcement comes from the host; the single-machine
case guards against mistakes and records who did what.
"""

from . import roles
from . import users
from . import accounts
from . import transactions
from . import reports
from . import profile
from . import service


class GatewayError(Exception):
    """An operation could not be completed. `code` is a short, stable machine
    string mirroring the host's error codes (e.g. 'forbidden', 'rejected')."""

    def __init__(self, message, code="error"):
        super().__init__(message)
        self.code = code


def _d(row):
    """A sqlite Row (or dict, or None) -> a plain dict."""
    return dict(row) if row is not None else None


class LocalGateway:
    """Operations performed directly against a local open book.

    Construct with the open connection and, for a shared book, the signed-in
    username and role (used for `whoami` and for stamping the audit log). For a
    personal or single-owner book these may be left as None.
    """

    is_remote = False

    def __init__(self, conn, username=None, role=None,
                 vault=None, data_key=None, db_path=None):
        self.conn = conn
        self.username = username
        self.role = role
        self.vault = vault
        self.data_key = data_key
        self.db_path = db_path

    def _svc(self):
        """A service.Session for user-administration on this local book."""
        return service.Session(self.conn, self.username, self.role,
                               vault=self.vault, data_key=self.data_key,
                               db_path=self.db_path)

    # -- identity ------------------------------------------------------------

    def whoami(self):
        return {"username": self.username, "role": self.role,
                "role_label": roles.label(self.role) if self.role else ""}

    def host_status(self):
        # Working locally (not against a host), there is only this one session.
        return {"session_count": 1}

    # -- accounts ------------------------------------------------------------

    def list_accounts(self, include_inactive=False):
        return [_d(a) for a in accounts.list_accounts(
            self.conn, include_inactive=include_inactive)]

    # -- journal -------------------------------------------------------------

    def list_entries(self, start=None, end=None):
        out = []
        for item in transactions.list_entries(self.conn, start=start, end=end):
            out.append({"entry": _d(item["entry"]),
                        "lines": [_d(ln) for ln in item["lines"]]})
        return out

    def record_entry(self, date, description, lines, reference=None):
        try:
            entry_id = transactions.add_entry(self.conn, date, description,
                                              lines, reference=reference)
        except (transactions.TransactionError, accounts.AccountError,
                ValueError) as e:
            raise GatewayError(e, code="rejected")
        self._audit("record_entry", "entry #%s: %s" % (entry_id, description))
        return {"entry_id": entry_id}

    def void_entry(self, entry_id):
        try:
            transactions.void_entry(self.conn, int(entry_id))
        except (transactions.TransactionError, ValueError) as e:
            raise GatewayError(e, code="rejected")
        self._audit("void_entry", "entry #%s" % entry_id)
        return {"entry_id": entry_id}

    # -- people / audit ------------------------------------------------------

    def list_users(self):
        return [_d(u) for u in users.list_users(self.conn)]

    def list_people(self):
        # The same roster as list_users, but the manager-facing path: the GUI's
        # "reset a staff password" helper uses it so a manager can find the
        # person. Locally the GUI gates access; over the wire this maps to a
        # VIEW_AUDIT-gated op (owner + manager). Resetting is still staff-only.
        return [_d(u) for u in users.list_users(self.conn)]

    def view_audit(self, limit=200):
        return [_d(a) for a in users.list_audit(self.conn, limit=limit)]

    # -- reports & profile ---------------------------------------------------

    _REPORTS = {
        "trial_balance": reports.trial_balance,
        "income_statement": reports.income_statement,
        "balance_sheet": reports.balance_sheet,
        "general_ledger": reports.general_ledger,
        "reconciliation": reports.reconciliation,
    }

    def report(self, name, start=None, end=None, account_code=None):
        fn = self._REPORTS.get(name)
        if fn is None:
            raise GatewayError("Unknown report: %r" % name, code="rejected")
        if name == "general_ledger":
            return fn(self.conn, start=start, end=end,
                      account_code=account_code)
        return fn(self.conn, start=start, end=end)

    def reconcile(self, bank_inputs, start=None, end=None):
        ledger = reports.reconciliation(self.conn, start=start, end=end)
        try:
            return reports.reconcile_against_statement(ledger, bank_inputs)
        except (ValueError, TypeError) as e:
            raise GatewayError(e, code="rejected")

    def get_profile(self):
        return _d(profile.get_profile(self.conn))

    def profile_header_lines(self):
        return profile.header_lines_from(self.get_profile())

    def is_personal(self):
        return (self.get_profile().get("kind") or "") == "personal"

    def save_profile(self, name="", address="", contact="", tagline=""):
        profile.save_profile(self.conn, name=name, address=address,
                             contact=contact, tagline=tagline)
        self._audit("edit_profile", "")
        return _d(profile.get_profile(self.conn))

    # -- account management --------------------------------------------------

    def add_account(self, code, name, acct_type):
        try:
            accounts.add_account(self.conn, code, name, acct_type)
        except (accounts.AccountError, ValueError) as e:
            raise GatewayError(e, code="rejected")
        self._audit("add_account", "%s %s" % (code, name))
        return _d(accounts.get_account(self.conn, code))

    def rename_account(self, code, new_name):
        try:
            accounts.rename_account(self.conn, code, new_name)
        except (accounts.AccountError, ValueError) as e:
            raise GatewayError(e, code="rejected")
        self._audit("rename_account", "%s -> %s" % (code, new_name))
        return _d(accounts.get_account(self.conn, code))

    def set_account_active(self, code, active):
        try:
            accounts.set_account_active(self.conn, code, bool(active))
        except (accounts.AccountError, ValueError) as e:
            raise GatewayError(e, code="rejected")
        self._audit("activate_account" if active else "deactivate_account",
                    code)
        return _d(accounts.get_account(self.conn, code))

    # -- user management -----------------------------------------------------

    def add_user(self, username, role, password, display_name="",
                 must_change=False):
        try:
            uname = service.add_user(self._svc(), username, role, password,
                                     display_name=display_name,
                                     must_change=must_change)
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        return {"username": uname}

    def reset_password(self, username, new_password, must_change=False):
        try:
            service.reset_password(self._svc(), username, new_password,
                                   must_change=must_change)
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        return {"username": users.normalize_username(username)}

    def change_role(self, username, role):
        try:
            service.change_role(self._svc(), username, role)
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        return {"username": users.normalize_username(username)}

    def set_user_active(self, username, active):
        try:
            service.set_active(self._svc(), username, bool(active))
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        return {"username": users.normalize_username(username)}

    def remove_user(self, username):
        try:
            service.remove_user(self._svc(), username)
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        return {"username": users.normalize_username(username)}

    def change_own_password(self, old_password, new_password):
        """The signed-in user changes their own password (current one given as
        confirmation). Clears any 'must change' flag."""
        try:
            service.change_own_password(self._svc(), old_password,
                                        new_password)
        except service.NotAllowed as e:
            raise GatewayError(e, code="forbidden")
        except ValueError as e:
            raise GatewayError(e, code="rejected")
        users.set_must_change(self.conn, self.username, False)
        return {"changed": True}

    # -- internal ------------------------------------------------------------

    def _audit(self, action, detail):
        """Record an action when this is a shared book (mirrors the host).
        Harmless no-op on books without an audit log."""
        if not self.username:
            self.conn.commit()
            return
        try:
            users.log_action(self.conn, self.username, action, detail)
        except Exception:
            pass
        self.conn.commit()


class RemoteGateway:
    """The same operations, performed on the host over the network.

    Construct with an already-connected, logged-in HostClient. Each method
    sends a request and returns the host's result, or raises GatewayError if
    the host refused (role not permitted, invalid entry, ...). Transport
    problems surface as the HostClient's own HostConnectionError.
    """

    is_remote = True

    def __init__(self, client):
        self.client = client

    def _call(self, op, **args):
        resp = self.client.request(op, **args)
        if not resp.get("ok"):
            raise GatewayError(resp.get("error", "The operation failed."),
                               code=resp.get("code", "error"))
        return resp.get("result")

    # -- identity ------------------------------------------------------------

    def whoami(self):
        return self._call("whoami")

    def host_status(self):
        return self._call("host_status")

    # -- accounts ------------------------------------------------------------

    def list_accounts(self, include_inactive=False):
        return self._call("list_accounts", include_inactive=include_inactive)

    # -- journal -------------------------------------------------------------

    def list_entries(self, start=None, end=None):
        return self._call("list_entries", start=start, end=end)

    def record_entry(self, date, description, lines, reference=None):
        return self._call("record_entry", date=date, description=description,
                          lines=lines, reference=reference)

    def void_entry(self, entry_id):
        return self._call("void_entry", entry_id=entry_id)

    # -- people / audit ------------------------------------------------------

    def list_users(self):
        return self._call("list_users")

    def list_people(self):
        return self._call("list_people")

    def view_audit(self, limit=200):
        return self._call("view_audit", limit=limit)

    # -- reports & profile ---------------------------------------------------

    def report(self, name, start=None, end=None, account_code=None):
        return self._call("report", name=name, start=start, end=end,
                          account_code=account_code)

    def reconcile(self, bank_inputs, start=None, end=None):
        return self._call("reconcile", bank_inputs=bank_inputs,
                          start=start, end=end)

    def get_profile(self):
        return self._call("get_profile")

    def profile_header_lines(self):
        return profile.header_lines_from(self.get_profile())

    def is_personal(self):
        return (self.get_profile().get("kind") or "") == "personal"

    def save_profile(self, name="", address="", contact="", tagline=""):
        return self._call("save_profile", name=name, address=address,
                          contact=contact, tagline=tagline)

    # -- account management --------------------------------------------------

    def add_account(self, code, name, acct_type):
        return self._call("add_account", code=code, name=name,
                          acct_type=acct_type)

    def rename_account(self, code, new_name):
        return self._call("rename_account", code=code, new_name=new_name)

    def set_account_active(self, code, active):
        return self._call("set_account_active", code=code, active=bool(active))

    # -- user management -----------------------------------------------------

    def add_user(self, username, role, password, display_name="",
                 must_change=False):
        return self._call("add_user", username=username, role=role,
                          password=password, display_name=display_name,
                          must_change=must_change)

    def reset_password(self, username, new_password, must_change=False):
        return self._call("reset_password", username=username,
                          new_password=new_password, must_change=must_change)

    def change_role(self, username, role):
        return self._call("change_role", username=username, role=role)

    def set_user_active(self, username, active):
        return self._call("set_user_active", username=username,
                          active=bool(active))

    def remove_user(self, username):
        return self._call("remove_user", username=username)

    def change_own_password(self, old_password, new_password):
        return self._call("change_own_password", old_password=old_password,
                          new_password=new_password)
