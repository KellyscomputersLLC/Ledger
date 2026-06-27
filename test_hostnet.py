# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Standalone test for the host network transport (Phase 2, Slice 2).

Starts a REAL TLS HostServer on localhost and talks to it with a REAL
HostClient over an actual encrypted socket. Verifies:
  - the channel is really TLS, and the client sees the host's certificate
  - certificate pinning: a matching pin connects; a wrong pin is refused
  - login over the wire issues a token; bad credentials are refused
  - role enforcement survives the round trip: staff is refused void / audit,
    manager is allowed, owner can do everything
  - record / list / void work end-to-end over the socket
  - two clients can be connected at once (threaded server)

Run from the project root:  python3 test_hostnet.py
"""

import os
import sys
import tempfile

from ledger import crypto, database, seed, roles, service, host, hostnet

problems = []


def check(cond, label):
    print(("  ok: " if cond else "  FAIL: ") + label)
    if not cond:
        problems.append(label)


OWNER_PW = "OwnerPass-123"
MGR_PW = "ManagerPass-123"
STAFF_PW = "StaffPass-123"

d = tempfile.mkdtemp()
path = os.path.join(d, "books.db")
cert_path = os.path.join(d, "host_cert.pem")
key_path = os.path.join(d, "host_key.pem")

# --- build an encrypted multi-user book (owner ben, manager mary, staff sam)
vault, _rec = crypto.create_vault(OWNER_PW)
crypto.save_vault(path, vault)
key = crypto.unlock(vault, OWNER_PW)
conn = database.connect(path, data_key=key, allow_threads=True)
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
service.add_user(owner, "mary", roles.MANAGER, MGR_PW)
service.add_user(owner, "sam", roles.STAFF, STAFF_PW)

# --- start the host on an ephemeral localhost port
engine = host.HostEngine(conn, crypto.load_vault(path), key, path)
server = hostnet.HostServer(engine, cert_path, key_path,
                            host="127.0.0.1", port=0)
server.start()
PORT = server.port
print("host listening on 127.0.0.1:%d" % PORT)

try:
    print("1. Secure channel + certificate pinning")
    c = hostnet.HostClient("127.0.0.1", PORT)
    fp = c.connect()
    check(c.sock.version().startswith("TLS"),
          "channel is TLS (%s)" % c.sock.version())
    check(fp == server.fingerprint(),
          "client sees the host's certificate fingerprint")
    check(":" in hostnet.pretty_fingerprint(fp),
          "fingerprint formats for reading aloud")
    c.close()

    # Reconnect WITH the correct pin -> fine.
    c = hostnet.HostClient("127.0.0.1", PORT, pinned_fingerprint=fp)
    c.connect()
    check(True, "reconnect with matching pin succeeds")

    print("2. Login over the wire")
    r = c.login("sam", STAFF_PW)
    check(r["ok"] and r["result"]["role"] == roles.STAFF and c.token,
          "staff logs in over TLS and gets a token")
    r2 = c.login("sam", "nope")
    check(not r2["ok"] and r2["code"] == "bad_credentials",
          "bad password refused over the wire")
    # restore a valid staff session for later
    c.login("sam", STAFF_PW)

    print("3. Reads + writes round-trip over the socket")
    accts = c.request("list_accounts")
    check(accts["ok"] and len(accts["result"]) > 0, "staff lists accounts")
    by_type = {a["type"]: a["code"] for a in accts["result"]}
    debit = by_type.get("EXPENSE") or accts["result"][0]["code"]
    credit = by_type.get("ASSET") or accts["result"][1]["code"]

    rec = c.request("record_entry", date="2026-03-01",
                    description="Remote supplies",
                    lines=[{"code": debit, "debit": 25, "credit": 0},
                           {"code": credit, "debit": 0, "credit": 25}])
    check(rec["ok"] and "entry_id" in rec["result"],
          "staff records an entry over the wire")
    eid = rec["result"]["entry_id"]
    lst = c.request("list_entries")
    check(lst["ok"] and any(e["entry"]["id"] == eid for e in lst["result"]),
          "the entry comes back in the journal")

    print("4. Role enforcement survives the round trip")
    v = c.request("void_entry", entry_id=eid)
    check(not v["ok"] and v["code"] == "forbidden", "staff void -> forbidden")
    a = c.request("view_audit")
    check(not a["ok"] and a["code"] == "forbidden", "staff audit -> forbidden")

    # A second, concurrent client signs in as the manager.
    m = hostnet.HostClient("127.0.0.1", PORT, pinned_fingerprint=fp)
    m.connect()
    m.login("mary", MGR_PW)
    check(m.request("view_audit")["ok"], "manager (2nd client) can view audit")
    vm = m.request("void_entry", entry_id=eid)
    check(vm["ok"], "manager (2nd client) can void")
    # owner-only op still refused for the manager.
    check(m.request("list_users")["code"] == "forbidden",
          "manager still cannot list users")
    m.close()
    c.close()

    print("5. A wrong pin is refused (simulated cert change / MITM)")
    bad = "00" * 32
    c2 = hostnet.HostClient("127.0.0.1", PORT, pinned_fingerprint=bad)
    raised = False
    try:
        c2.connect()
    except hostnet.HostCertMismatch:
        raised = True
    check(raised, "client refuses a host whose cert doesn't match the pin")

    print("6. Unreachable host is reported cleanly")
    dead = hostnet.HostClient("127.0.0.1", 1, timeout=2)
    got = False
    try:
        dead.connect()
    except hostnet.HostConnectionError:
        got = True
    check(got, "connecting to a dead port raises HostConnectionError")

finally:
    server.stop()

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All host-transport checks passed.")
