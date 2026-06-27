# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""The in-process loopback: the computer that hosts the books can also use
them, going through its own engine. This proves a LoopbackClient wrapped in the
ordinary RemoteGateway does real bookkeeping against the engine (so the GUI's
tabs work unchanged in host mode), that a token minted for the already-signed-in
owner needs no second login, and that edits made this way are what a separate
(remote-style) client sees -- i.e. one authoritative set of books, no drift."""

import os
import tempfile
import shutil

from ledger import (crypto, database, seed, service, roles, users, host,
                    gateway)

OWNER_PW = "OwnerPass-123"
STAFF_PW = "StaffPass-123"


def run():
    d = tempfile.mkdtemp(prefix="ledger-loopback-")
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
        conn.commit()

        engine = host.HostEngine(conn, crypto.load_vault(path), key, path)

        # The owner is already authenticated locally -> mint a token, no login.
        token = host.issue_local_token(engine, "ben", roles.OWNER)
        local = gateway.RemoteGateway(host.LoopbackClient(engine, token))
        assert local.whoami()["username"] == "ben"
        print("1. minted owner token works with no second sign-in: OK")

        # Real bookkeeping through the ordinary gateway (what the tabs use).
        accts = local.list_accounts()
        assert accts and isinstance(accts, list)
        cash = "1000"   # Checking Account
        rev = "4000"    # Sales Revenue
        local.record_entry(date="2026-02-01", description="Loopback sale",
                           lines=[{"code": cash, "debit": 250, "credit": 0},
                                  {"code": rev, "debit": 0, "credit": 250}])
        mine = local.list_entries()
        assert any(e["entry"]["description"] == "Loopback sale" for e in mine)
        print("2. bookkeeping through the loopback gateway works: OK")

        # A second client (a remote sam, same engine) sees the same books --
        # the host's local edits are not a private copy.
        r = engine.handle({"op": "login",
                           "args": {"username": "sam", "password": STAFF_PW}})
        sam = gateway.RemoteGateway(
            host.LoopbackClient(engine, r["result"]["token"]))
        theirs = sam.list_entries()
        assert any(e["entry"]["description"] == "Loopback sale"
                   for e in theirs), \
            "the second client should see the owner's entry"
        print("3. a second client sees the same live books (no drift): OK")

        # And the reverse: sam (staff) records, owner sees it.
        sam.record_entry(date="2026-02-02", description="Sam entry",
                         lines=[{"code": cash, "debit": 40, "credit": 0},
                                {"code": rev, "debit": 0, "credit": 40}])
        assert any(e["entry"]["description"] == "Sam entry"
                   for e in local.list_entries())
        print("4. the owner sees the other client's entry too: OK")

        # Role enforcement still applies through the loopback (staff cannot
        # manage users).
        try:
            sam.list_users()
            staff_blocked = False
        except gateway.GatewayError as ex:
            staff_blocked = (ex.code == "forbidden")
        assert staff_blocked, "staff should not be able to list users"
        assert any(u["username"] == "sam" for u in local.list_users())
        print("5. role rules still enforced through the engine: OK")

        host.issue_local_token  # touch for symmetry
        print("All loopback (use-while-hosting) checks passed.")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    run()
