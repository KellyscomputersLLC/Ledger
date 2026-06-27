# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
The host engine: a single request -> response seam that wraps Ledger's data
layer with authentication and per-role authorization.

This is the heart of the "host" model. On the main office computer, a host
process opens the books ONCE (the owner unlocks them at startup) and keeps the
data key in memory. Other computers connect as clients. Every request a client
makes is run *here*, on the host, against the host's open book, with the
client's role enforced -- and the client never receives the data key. That is
what turns single-machine roles (which only gray out buttons) into real
enforcement: an employee's computer simply does not have the data or the key,
so there is nothing to bypass.

There is deliberately NO networking in this module. It is the in-process core:
a `HostEngine` that takes a request dict and returns a response dict. A later
slice wraps this in a socket server with an encrypted channel; the client then
sends those same request dicts over the wire. Keeping the engine transport-free
means the hard part -- auth, routing, and role enforcement -- is built and
tested before any networking complexity is added.

Request shape (a plain dict, JSON-safe):
    {"op": "record_entry", "token": "<from login>", "args": {...}}
Login is the one request that carries no token:
    {"op": "login", "args": {"username": "...", "password": "..."}}

Response shape (also JSON-safe):
    {"ok": True,  "result": <any>}
    {"ok": False, "error": "<human message>", "code": "<short machine code>"}

Why a token instead of sending the password every time: verifying a password
runs scrypt, which is intentionally slow. Doing that on every request would be
far too slow. So a client logs in once (one scrypt), the host issues a random
session token, and later requests carry the token -- a fast dictionary lookup.
"""

import secrets
import threading
import time

from . import crypto
from . import roles
from . import users
from . import accounts
from . import transactions
from . import reports
from . import profile
from . import service


PROTOCOL_VERSION = 1

# How long a session token stays valid without use. Refreshed on every request,
# so an actively-used client stays signed in; an idle one is dropped.
TOKEN_TTL_SECONDS = 8 * 60 * 60  # one working day

# Operations a user flagged to change their password is still allowed to call
# (besides login/logout, which are handled before the gate): check who they
# are, and change the password itself. Everything else is refused until done.
_PW_CHANGE_EXEMPT_OPS = {"whoami", "change_own_password"}


class HostError(Exception):
    """A request that could not be served. `code` is a short, stable machine
    string (the human-readable text may change; the code should not)."""

    def __init__(self, message, code="error"):
        super().__init__(message)
        self.code = code


def ok(result=None):
    """A success response."""
    return {"ok": True, "result": result}


def err(message, code="error"):
    """A failure response."""
    return {"ok": False, "error": str(message), "code": code}


def _row(r):
    """A sqlite Row (or dict, or None) -> a plain dict, for JSON-safe output."""
    return dict(r) if r is not None else None


class HostEngine:
    """Holds the single open book and serves authenticated, authorized
    requests against it.

    Construct it with an already-open book: the host process unlocks the book
    at startup (the owner provides the passphrase), then hands the open
    connection, vault, data key, and path to the engine. The engine does not
    unlock anything itself -- it only verifies that a logging-in user's
    password fits THEIR slot, which proves who they are without ever handing
    the data key back to the client.
    """

    def __init__(self, conn, vault, data_key, db_path):
        self.conn = conn
        self.vault = vault
        self.data_key = data_key
        self.db_path = db_path
        # Bring an older multi-user book's tables up to date before serving any
        # request that reads the user list (a no-op on current books).
        try:
            users.migrate(conn)
        except Exception:
            pass
        # One lock serializes all access to the in-memory SQLite connection,
        # which is not safe to use from several threads at once. A small
        # business host sees little concurrency, so a single lock is plenty.
        self._lock = threading.Lock()
        # token -> {"username", "role", "last_seen"}
        self._tokens = {}
        self._build_registry()

    # -- tokens / sessions ---------------------------------------------------

    def _issue_token(self, username, role):
        token = secrets.token_urlsafe(24)
        self._tokens[token] = {
            "username": username, "role": role, "last_seen": time.time()}
        return token

    def session_count(self):
        """How many sessions are currently active -- used for the host's live
        'N connected' display. Counts every signed-in token, including the
        host computer's own in-process (loopback) session."""
        now = time.time()
        return sum(1 for info in self._tokens.values()
                   if now - info.get("last_seen", 0) <= TOKEN_TTL_SECONDS)

    def _session_for(self, token):
        """Resolve a token to a fresh Session, or raise HostError. Refreshes
        the token's last-seen time so active clients stay signed in."""
        info = self._tokens.get(token)
        if not info:
            raise HostError("Please sign in.", code="auth_required")
        if time.time() - info["last_seen"] > TOKEN_TTL_SECONDS:
            self._tokens.pop(token, None)
            raise HostError("Your session has expired. Please sign in again.",
                            code="auth_expired")
        info["last_seen"] = time.time()
        return service.Session(self.conn, info["username"], info["role"],
                               vault=self.vault, data_key=self.data_key,
                               db_path=self.db_path)

    def active_sessions(self):
        """How many tokens are currently issued (for host-side display)."""
        return len(self._tokens)

    def logout(self, token):
        """Drop a token. Always succeeds (unknown tokens are ignored)."""
        with self._lock:
            self._tokens.pop(token, None)
        return ok({"signed_out": True})

    # -- the single entry point ---------------------------------------------

    def handle(self, request):
        """Take a request dict and return a response dict. Never raises:
        every failure becomes an `err(...)` response so the transport layer
        can simply send whatever this returns."""
        try:
            if not isinstance(request, dict):
                return err("Malformed request.", code="bad_request")
            op = request.get("op")
            if not op:
                return err("Missing operation.", code="bad_request")

            # Login is special: it carries no token and issues one.
            if op == "login":
                return self._do_login(request.get("args") or {})
            if op == "logout":
                return self.logout(request.get("token"))

            entry = self._ops.get(op)
            if entry is None:
                return err("Unknown operation: %r" % op, code="unknown_op")
            required_action, handler = entry

            with self._lock:
                session = self._session_for(request.get("token"))
                # A user flagged to change their password -- a one-time
                # password not yet replaced, or one past the rotation age --
                # may do nothing but change it (or check who they are / sign
                # out) until they do. Enforced HERE on the host so a remote
                # client cannot skip it.
                if op not in _PW_CHANGE_EXEMPT_OPS \
                        and service.password_change_required(session):
                    return err("Set a new password before continuing.",
                               code="password_change_required")
                if required_action is not None and \
                        not session.can(required_action):
                    return err("Your role can't do that.", code="forbidden")
                result = handler(session, request.get("args") or {})
            return ok(result)

        except HostError as e:
            return err(e, code=e.code)
        except service.NotAllowed as e:
            return err(e, code="forbidden")
        except (accounts.AccountError, transactions.TransactionError,
                ValueError) as e:
            # Expected, user-correctable problems (bad account, unbalanced
            # entry, bad date, ...). Pass the message through.
            return err(e, code="rejected")
        except Exception:
            # Anything else is a host-side fault; do not leak internals.
            return err("The host could not complete that request.",
                       code="error")

    # -- login ---------------------------------------------------------------

    def _do_login(self, args):
        username = users.normalize_username(args.get("username", ""))
        password = args.get("password", "")
        if not username or not password:
            return err("Enter a username and password.", code="bad_request")
        with self._lock:
            # Verify the password fits THIS user's slot -- unlock_as never
            # tries other slots, so one person's password cannot open another
            # person's access. We discard the key it returns; the host already
            # holds the data key. This is authentication, not key delivery.
            try:
                crypto.unlock_as(self.vault, username, password)
            except Exception:
                return err("That username and password don't match.",
                           code="bad_credentials")
            user = users.get_user(self.conn, username)
            if not user:
                return err("That username and password don't match.",
                           code="bad_credentials")
            if not user.get("active", True):
                return err("That account has been deactivated.",
                           code="inactive")
            token = self._issue_token(username, user["role"])
            sess = service.Session(self.conn, username, user["role"],
                                   vault=self.vault, data_key=self.data_key,
                                   db_path=self.db_path)
            return ok({
                "token": token,
                "username": username,
                "role": user["role"],
                "role_label": roles.label(user["role"]),
                "must_change_pw": bool(user.get("must_change_pw")),
                # 'first_login' | 'expired' | None -- so a client knows to
                # force a password change before letting the person work.
                "change_required": service.password_change_required(sess),
                "protocol": PROTOCOL_VERSION,
            })

    # -- operation registry --------------------------------------------------

    def _build_registry(self):
        """Map each operation name to (required_action_or_None, handler).

        `required_action is None` means "any signed-in user". Otherwise the
        session's role must permit that action, checked centrally in handle()
        before the handler runs -- so a handler can assume it is authorized.
        """
        self._ops = {
            # read / everyday (any signed-in user)
            "whoami":        (None, self._op_whoami),
            "host_status":   (None, self._op_host_status),
            "list_accounts": (None, self._op_list_accounts),
            "get_profile":   (None, self._op_get_profile),
            "list_entries":  (roles.VIEW_JOURNAL, self._op_list_entries),
            "record_entry":  (roles.RECORD_ENTRY, self._op_record_entry),
            "report":        (roles.VIEW_REPORTS, self._op_report),
            # owner + manager
            "reconcile":     (roles.RECONCILE, self._op_reconcile),
            "void_entry":    (roles.VOID_ENTRY, self._op_void_entry),
            "view_audit":    (roles.VIEW_AUDIT, self._op_view_audit),
            # the roster, for owner + manager (a manager uses it to find the
            # staff member whose password they're resetting)
            "list_people":   (roles.VIEW_AUDIT, self._op_list_people),
            "add_account":   (roles.MANAGE_ACCOUNTS, self._op_add_account),
            "rename_account": (roles.MANAGE_ACCOUNTS,
                               self._op_rename_account),
            "set_account_active": (roles.MANAGE_ACCOUNTS,
                                   self._op_set_account_active),
            "save_profile":  (roles.EDIT_PROFILE, self._op_save_profile),
            # owner only
            "list_users":    (roles.MANAGE_USERS, self._op_list_users),
            "add_user":      (roles.MANAGE_USERS, self._op_add_user),
            # owner + manager (a manager may reset a *staff* password only;
            # that narrower limit is enforced in service.reset_password).
            "reset_password": (roles.RESET_PASSWORD, self._op_reset_password),
            "change_role":   (roles.MANAGE_USERS, self._op_change_role),
            "set_user_active": (roles.MANAGE_USERS, self._op_set_user_active),
            "remove_user":   (roles.MANAGE_USERS, self._op_remove_user),
            "change_own_password": (None, self._op_change_own_password),
        }

    # A name -> report-function map, all returning JSON-safe plain dicts.
    _REPORTS = {
        "trial_balance": reports.trial_balance,
        "income_statement": reports.income_statement,
        "balance_sheet": reports.balance_sheet,
        "general_ledger": reports.general_ledger,
        "reconciliation": reports.reconciliation,
    }

    def _svc(self, session):
        """A service.Session for the requesting user, carrying the host's
        vault and key so user-administration (which rewraps login slots) can
        run on the host."""
        return service.Session(self.conn, session.username, session.role,
                               vault=self.vault, data_key=self.data_key,
                               db_path=self.db_path)

    # -- handlers ------------------------------------------------------------
    # Each handler runs already-authorized, under the engine lock, against the
    # host's open book. Write handlers also record an audit entry, so the
    # host's audit log is the authoritative record of what clients did.

    def _op_whoami(self, session, args):
        return {"username": session.username, "role": session.role,
                "role_label": roles.label(session.role)}

    def _op_host_status(self, session, args):
        """Lightweight status for any signed-in user: how many sessions are
        currently active. The app uses this to show 'N connected' while it is
        working against the host as a local client."""
        return {"session_count": self.session_count()}

    def _op_list_accounts(self, session, args):
        include_inactive = bool(args.get("include_inactive"))
        rows = accounts.list_accounts(self.conn,
                                      include_inactive=include_inactive)
        return [_row(a) for a in rows]

    def _op_list_entries(self, session, args):
        start = args.get("start") or None
        end = args.get("end") or None
        out = []
        for item in transactions.list_entries(self.conn, start=start, end=end):
            out.append({"entry": _row(item["entry"]),
                        "lines": [_row(ln) for ln in item["lines"]]})
        return out

    def _op_record_entry(self, session, args):
        date_str = args.get("date", "")
        description = args.get("description", "")
        lines = args.get("lines") or []
        reference = args.get("reference") or None
        # add_entry validates (balanced, valid accounts, valid date) and
        # commits -- which, on an encrypted book, also writes the encrypted
        # file to disk.
        entry_id = transactions.add_entry(self.conn, date_str, description,
                                          lines, reference=reference)
        users.log_action(self.conn, session.username, "record_entry",
                         "entry #%s: %s" % (entry_id, description))
        self.conn.commit()
        return {"entry_id": entry_id}

    def _op_void_entry(self, session, args):
        entry_id = int(args.get("entry_id"))
        transactions.void_entry(self.conn, entry_id)
        users.log_action(self.conn, session.username, "void_entry",
                         "entry #%s" % entry_id)
        self.conn.commit()
        return {"entry_id": entry_id}

    def _op_view_audit(self, session, args):
        limit = int(args.get("limit", 200))
        rows = users.list_audit(self.conn, limit=limit)
        return [_row(a) for a in rows]

    def _op_list_users(self, session, args):
        return [_row(u) for u in users.list_users(self.conn)]

    def _op_list_people(self, session, args):
        # The roster for owner + manager. Managers use it to find the staff
        # member whose password they're resetting; the reset itself stays
        # staff-only in service.reset_password.
        return [_row(u) for u in users.list_users(self.conn)]

    # -- reports & profile ---------------------------------------------------

    def _op_report(self, session, args):
        name = args.get("name")
        fn = self._REPORTS.get(name)
        if fn is None:
            raise HostError("Unknown report: %r" % name, code="rejected")
        start = args.get("start") or None
        end = args.get("end") or None
        if name == "general_ledger":
            return fn(self.conn, start=start, end=end,
                      account_code=args.get("account_code"))
        return fn(self.conn, start=start, end=end)

    def _op_reconcile(self, session, args):
        start = args.get("start") or None
        end = args.get("end") or None
        bank_inputs = args.get("bank_inputs") or {}
        ledger = reports.reconciliation(self.conn, start=start, end=end)
        return reports.reconcile_against_statement(ledger, bank_inputs)

    def _op_get_profile(self, session, args):
        return _row(profile.get_profile(self.conn))

    def _op_save_profile(self, session, args):
        profile.save_profile(
            self.conn,
            name=args.get("name", ""),
            address=args.get("address", ""),
            contact=args.get("contact", ""),
            tagline=args.get("tagline", ""))
        users.log_action(self.conn, session.username, "edit_profile", "")
        self.conn.commit()
        return _row(profile.get_profile(self.conn))

    # -- account management --------------------------------------------------

    def _op_add_account(self, session, args):
        code = args.get("code", "")
        name = args.get("name", "")
        acct_type = args.get("acct_type") or args.get("type", "")
        accounts.add_account(self.conn, code, name, acct_type)
        users.log_action(self.conn, session.username, "add_account",
                         "%s %s" % (code, name))
        self.conn.commit()
        return _row(accounts.get_account(self.conn, code))

    def _op_rename_account(self, session, args):
        code = args.get("code", "")
        new_name = args.get("new_name", "")
        accounts.rename_account(self.conn, code, new_name)
        users.log_action(self.conn, session.username, "rename_account",
                         "%s -> %s" % (code, new_name))
        self.conn.commit()
        return _row(accounts.get_account(self.conn, code))

    def _op_set_account_active(self, session, args):
        code = args.get("code", "")
        active = bool(args.get("active"))
        accounts.set_account_active(self.conn, code, active)
        users.log_action(self.conn, session.username,
                         "activate_account" if active else "deactivate_account",
                         code)
        self.conn.commit()
        return _row(accounts.get_account(self.conn, code))

    # -- user management (runs through the service, which authorizes and
    #    audits on its own, so these handlers do not log again) --------------

    def _op_add_user(self, session, args):
        uname = service.add_user(
            self._svc(session),
            args.get("username", ""), args.get("role", ""),
            args.get("password", ""),
            display_name=args.get("display_name", ""),
            must_change=bool(args.get("must_change", False)))
        return {"username": uname}

    def _op_reset_password(self, session, args):
        service.reset_password(
            self._svc(session), args.get("username", ""),
            args.get("new_password", ""),
            must_change=bool(args.get("must_change", False)))
        return {"username": users.normalize_username(args.get("username", ""))}

    def _op_change_role(self, session, args):
        service.change_role(self._svc(session), args.get("username", ""),
                            args.get("role", ""))
        return {"username": users.normalize_username(args.get("username", ""))}

    def _op_set_user_active(self, session, args):
        service.set_active(self._svc(session), args.get("username", ""),
                           bool(args.get("active")))
        return {"username": users.normalize_username(args.get("username", ""))}

    def _op_remove_user(self, session, args):
        service.remove_user(self._svc(session), args.get("username", ""))
        return {"username": users.normalize_username(args.get("username", ""))}

    def _op_change_own_password(self, session, args):
        """The signed-in user changes their own password over the wire, giving
        their current one as confirmation. Clears any 'must change' flag and
        resets the rotation clock, so the requirement lifts once they comply."""
        old = args.get("old_password", "")
        new = args.get("new_password", "")
        service.change_own_password(session, old, new)
        users.set_must_change(self.conn, session.username, False)
        return {"changed": True}


class LoopbackClient:
    """An in-process stand-in for HostClient that talks straight to a
    HostEngine in this same process -- no socket, no TLS. It lets the computer
    doing the hosting also use the books: it goes through the one authoritative
    engine, exactly like a remote client, so the local user and every connected
    computer read and write the same live set of books with no drift.

    The owner already authenticated locally, so their session token is minted
    directly (see issue_local_token) and there is no second sign-in. The
    interface matches the parts of HostClient that RemoteGateway relies on, so
    the same gateway works against it unchanged."""

    def __init__(self, engine, token):
        self._engine = engine
        self.token = token

    def request(self, op, **args):
        return self._engine.handle(
            {"op": op, "token": self.token, "args": args})

    def login(self, username, password):
        resp = self._engine.handle(
            {"op": "login", "token": None,
             "args": {"username": username, "password": password}})
        if resp.get("ok"):
            self.token = (resp.get("result") or {}).get("token")
        return resp

    def logout(self):
        if self.token is None:
            return {"ok": True, "result": {"signed_out": True}}
        resp = self._engine.handle(
            {"op": "logout", "token": self.token, "args": {}})
        self.token = None
        return resp

    def close(self):
        self.token = None


def issue_local_token(engine, username, role):
    """Mint a session token for a user the in-process caller has already
    authenticated locally (the owner who started hosting). Used to build a
    LoopbackClient without a second password prompt. In-process only -- never
    exposed over the wire."""
    return engine._issue_token(username, role)
