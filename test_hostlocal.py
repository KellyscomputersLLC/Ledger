# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""End-to-end check for in-app hosting (start_local_host / stop_local_host):
build a protected multi-user book the way the app would, start hosting it on a
thread-safe connection, connect a real client over TLS, sign in, run an
operation, then stop hosting and confirm the port is released. Headless; no
GUI. Advertising is left off here so the test does not depend on the fixed
discovery port being free -- discovery itself is covered by test_host_discovery.
"""

import os
import socket
import tempfile
import shutil

from ledger import (crypto, database, seed, service, roles, users,
                    host_main, hostnet)

OWNER_PW = "OwnerPass-123"
STAFF_PW = "StaffPass-123"


def _build_book(path):
    """Create an encrypted, multi-user book (owner 'ben', staff 'sam'),
    commit it, and close -- mirroring the state the app leaves on disk before
    it starts hosting."""
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
    conn.close()        # the app would close its single-thread conn here
    return key


def run():
    d = tempfile.mkdtemp(prefix="ledger-hostlocal-")
    path = os.path.join(d, "books.db")
    server = conn = None
    try:
        key = _build_book(path)

        # 1. Start hosting on an ephemeral port (advertise off for the test).
        server, conn = host_main.start_local_host(
            path, key, port=0, bind="127.0.0.1", advertise=False)
        assert server.port > 0
        print("1. start_local_host opens a thread-safe host on the book: OK")

        # 2. A real client connects over TLS (trust-on-first-use), signs in,
        #    and runs an operation -- proving the in-app host actually serves.
        client = hostnet.HostClient("127.0.0.1", server.port,
                                    pinned_fingerprint=None)
        fp = client.connect()
        assert fp, "no fingerprint from the host"
        login = client.login("ben", OWNER_PW)
        assert login.get("ok"), login
        assert login["result"]["role"] == roles.OWNER
        who = client.request("whoami")
        assert who.get("ok"), who
        accts = client.request("list_accounts")
        assert accts.get("ok") and isinstance(accts["result"], list)
        assert len(accts["result"]) > 0
        # The client-mode Security tab relies on these over-the-wire ops:
        # listing users and reading the activity log. Prove they work.
        ulist = client.request("list_users")
        assert ulist.get("ok"), ulist
        names = {u.get("username") for u in ulist["result"]}
        assert {"ben", "sam"} <= names, names
        audit = client.request("view_audit", limit=50)
        assert audit.get("ok") and isinstance(audit["result"], list), audit
        client.logout()
        client.close()
        print("2. a client connects, signs in, lists users, reads the log: OK")

        # 3. A wrong password is refused by the in-app host.
        c2 = hostnet.HostClient("127.0.0.1", server.port,
                                pinned_fingerprint=fp)
        c2.connect()
        bad = c2.login("ben", "not-the-password")
        assert not bad.get("ok") and bad.get("code") == "bad_credentials", bad
        c2.close()
        print("3. wrong credentials are refused over the wire: OK")

        # 4. Stop hosting; the port is released so nothing accepts there now.
        held_port = server.port
        host_main.stop_local_host(server, conn)
        server = conn = None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        refused = False
        try:
            s.connect(("127.0.0.1", held_port))
        except OSError:
            refused = True
        finally:
            s.close()
        assert refused, "port still accepting after stop_local_host"
        print("4. stop_local_host stops serving and releases the port: OK")

        # 5. Hosting an unprotected book is refused with a clear error.
        plain = os.path.join(d, "plain.db")
        pc = database.connect(plain)
        database.init_db(pc)
        pc.commit()
        pc.close()
        try:
            host_main.start_local_host(plain, None, port=0)
            raise AssertionError("expected a refusal for an unprotected book")
        except ValueError:
            pass
        print("5. an unprotected book is refused for hosting: OK")

        print("All in-app hosting checks passed.")
    finally:
        if server is not None or conn is not None:
            host_main.stop_local_host(server, conn)
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    run()
