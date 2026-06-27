# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""Host-side enforcement of a required password change. A user flagged to
change their password (a one-time password, or one past the rotation age) must
do nothing on the host but change it -- this proves the host refuses other work
until they comply, that the change itself works over the same request channel,
and that the requirement then lifts. Headless: drives the engine directly."""

import os
import tempfile
import shutil

from ledger import crypto, database, seed, service, roles, users, host

OWNER_PW = "OwnerPass-123"
STAFF_PW = "StaffPass-123"
NEW_PW = "BrandNewStaffPass-456"


def run():
    d = tempfile.mkdtemp(prefix="ledger-pwwire-")
    path = os.path.join(d, "books.db")
    try:
        vault, _rec = crypto.create_vault(OWNER_PW)
        crypto.save_vault(path, vault)
        key = crypto.unlock(vault, OWNER_PW)
        conn = database.connect(path, data_key=key)
        database.init_db(conn)
        seed.seed_accounts(conn)
        conn.commit()
        setup = service.Session(conn, "owner", roles.OWNER,
                                vault=crypto.load_vault(path), data_key=key,
                                db_path=path)
        service.enable_multiuser(setup, OWNER_PW, "ben")
        owner = service.Session(conn, "ben", roles.OWNER,
                                vault=crypto.load_vault(path), data_key=key,
                                db_path=path)
        service.add_user(owner, "sam", roles.STAFF, STAFF_PW)
        users.set_must_change(conn, "sam", True)       # one-time password
        conn.commit()

        engine = host.HostEngine(conn, crypto.load_vault(path), key, path)

        def call(op, token=None, **args):
            return engine.handle({"op": op, "token": token, "args": args})

        # Login still succeeds and reports the must-change flag.
        r = call("login", username="sam", password=STAFF_PW)
        assert r["ok"] and r["result"]["must_change_pw"] is True, r
        assert r["result"]["change_required"] == "first_login", r
        tok = r["result"]["token"]
        print("1. flagged user can log in; host reports must_change_pw: OK")

        # Normal work is refused until the password is changed...
        r = call("list_accounts", token=tok)
        assert not r["ok"] and r["code"] == "password_change_required", r
        r = call("record_entry", token=tok, date="2026-01-01",
                 description="x", lines=[])
        assert not r["ok"] and r["code"] == "password_change_required", r
        # ...but whoami still works (so the client can show who they are).
        assert call("whoami", token=tok)["ok"]
        print("2. all work refused (password_change_required); whoami ok: OK")

        # A wrong current password or too-short new one is rejected, and the
        # requirement is still in force.
        r = call("change_own_password", token=tok, old_password="wrong",
                 new_password=NEW_PW)
        assert not r["ok"] and r["code"] == "rejected", r
        r = call("change_own_password", token=tok, old_password=STAFF_PW,
                 new_password="x")
        assert not r["ok"], r
        assert not call("list_accounts", token=tok)["ok"]
        print("3. bad old / short new rejected; still gated: OK")

        # The correct change succeeds and immediately lifts the gate.
        r = call("change_own_password", token=tok, old_password=STAFF_PW,
                 new_password=NEW_PW)
        assert r["ok"] and r["result"]["changed"] is True, r
        assert call("list_accounts", token=tok)["ok"]
        print("4. correct change succeeds and unblocks work: OK")

        # The new password now works on a fresh login (flag cleared); the old
        # one no longer does.
        r = call("login", username="sam", password=NEW_PW)
        assert r["ok"] and r["result"]["must_change_pw"] is False, r
        assert r["result"]["change_required"] is None, r
        assert call("list_accounts", token=r["result"]["token"])["ok"]
        r = call("login", username="sam", password=STAFF_PW)
        assert not r["ok"], "old password should no longer work"
        print("5. new password works, flag cleared, old password dead: OK")

        # The owner (not flagged) is never gated.
        r = call("login", username="ben", password=OWNER_PW)
        assert r["ok"] and call("list_accounts",
                                token=r["result"]["token"])["ok"]
        print("6. an un-flagged user is never gated: OK")

        print("All host password-change enforcement checks passed.")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    run()
