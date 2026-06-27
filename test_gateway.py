# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Standalone test for the gateway seam (Phase 3, Slice 1).

Proves that the GUI can be mode-agnostic: the same gateway calls return the
same shapes whether run locally or against the host over the network, and that
the remote path is enforced by the host (a tab written once works in both
modes, and role limits hold in client mode).

  - LocalGateway and RemoteGateway return identical shapes for the same reads
  - a write made through one gateway is visible through the other (same book)
  - RemoteGateway raises GatewayError('forbidden') when a role isn't permitted
  - RemoteGateway raises GatewayError('rejected') for a bad (unbalanced) entry

Run from the project root:  python3 test_gateway.py
"""

import os
import sys
import tempfile

from ledger import (crypto, database, seed, roles, service, host, hostnet,
                    gateway)

problems = []


def check(cond, label):
    print(("  ok: " if cond else "  FAIL: ") + label)
    if not cond:
        problems.append(label)


OWNER_PW = "OwnerPass-123"
STAFF_PW = "StaffPass-123"

d = tempfile.mkdtemp()
path = os.path.join(d, "books.db")
cert_path = os.path.join(d, "host_cert.pem")
key_path = os.path.join(d, "host_key.pem")

# --- encrypted multi-user book: owner ben, staff sam --------------------------
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
service.add_user(owner, "sam", roles.STAFF, STAFF_PW)

# --- host serving the same book, plus a local gateway over the same conn ------
engine = host.HostEngine(conn, crypto.load_vault(path), key, path)
server = hostnet.HostServer(engine, cert_path, key_path,
                            host="127.0.0.1", port=0)
server.start()
PORT = server.port

local = gateway.LocalGateway(conn, username="ben", role=roles.OWNER)

owner_client = hostnet.HostClient("127.0.0.1", PORT)
owner_client.connect()
owner_client.login("ben", OWNER_PW)
remote = gateway.RemoteGateway(owner_client)

try:
    print("1. whoami matches")
    lw, rw = local.whoami(), remote.whoami()
    check(lw["username"] == rw["username"] == "ben"
          and lw["role"] == rw["role"] == roles.OWNER
          and lw["role_label"] == rw["role_label"],
          "local and remote whoami agree")

    print("2. list_accounts returns identical shapes")
    la = local.list_accounts()
    ra = remote.list_accounts()
    check(la == ra and len(la) > 0,
          "local and remote account lists are identical")
    # keys present on each row match too
    check(set(la[0].keys()) == set(ra[0].keys()),
          "account row fields match exactly")

    by_type = {a["type"]: a["code"] for a in la}
    debit = by_type.get("EXPENSE") or la[0]["code"]
    credit = by_type.get("ASSET") or la[1]["code"]

    print("3. a write via one gateway is visible via the other")
    # record remotely...
    r = remote.record_entry("2026-04-01", "Recorded via host",
                            [{"code": debit, "debit": 12, "credit": 0},
                             {"code": credit, "debit": 0, "credit": 12}])
    rid = r["entry_id"]
    # ...and read it locally
    local_descs = [e["entry"]["description"] for e in local.list_entries()]
    check("Recorded via host" in local_descs,
          "entry recorded remotely is visible to the local gateway")

    # record locally...
    local.record_entry("2026-04-02", "Recorded via local",
                       [{"code": debit, "debit": 8, "credit": 0},
                        {"code": credit, "debit": 0, "credit": 8}])
    # ...and read it remotely; the two journals should be identical
    check(local.list_entries() == remote.list_entries(),
          "local and remote journals are identical after both writes")

    print("4. list shapes for users and audit match")
    check(local.list_users() == remote.list_users(),
          "user lists identical")
    check(local.view_audit() == remote.view_audit(),
          "audit lists identical")

    print("5. RemoteGateway is enforced by the host")
    staff_client = hostnet.HostClient("127.0.0.1", PORT,
                                      pinned_fingerprint=server.fingerprint())
    staff_client.connect()
    staff_client.login("sam", STAFF_PW)
    staff_remote = gateway.RemoteGateway(staff_client)

    # Staff CAN record...
    rr = staff_remote.record_entry("2026-04-03", "Staff entry",
                                   [{"code": debit, "debit": 5, "credit": 0},
                                    {"code": credit, "debit": 0, "credit": 5}])
    check("entry_id" in rr, "staff can record through the remote gateway")

    # ...but CANNOT void.
    forbidden = False
    try:
        staff_remote.void_entry(rid)
    except gateway.GatewayError as e:
        forbidden = (e.code == "forbidden")
    check(forbidden, "staff void raises GatewayError('forbidden')")

    # ...and CANNOT view the audit log.
    blocked = False
    try:
        staff_remote.view_audit()
    except gateway.GatewayError as e:
        blocked = (e.code == "forbidden")
    check(blocked, "staff view_audit raises GatewayError('forbidden')")

    print("6. A bad entry is reported as 'rejected', not a crash")
    rejected = False
    try:
        remote.record_entry("2026-04-04", "Unbalanced",
                            [{"code": debit, "debit": 5, "credit": 0},
                             {"code": credit, "debit": 0, "credit": 2}])
    except gateway.GatewayError as e:
        rejected = (e.code == "rejected")
    check(rejected, "unbalanced entry raises GatewayError('rejected')")

    # The local gateway maps the same failure the same way.
    rejected_local = False
    try:
        local.record_entry("2026-04-04", "Unbalanced",
                           [{"code": debit, "debit": 5, "credit": 0},
                            {"code": credit, "debit": 0, "credit": 2}])
    except gateway.GatewayError as e:
        rejected_local = (e.code == "rejected")
    check(rejected_local, "local gateway also maps a bad entry to 'rejected'")

    print("7. Reports: identical local vs remote")
    for rep in ("trial_balance", "income_statement", "balance_sheet"):
        check(local.report(rep) == remote.report(rep),
              "%s identical local vs remote" % rep)
    bad_report = False
    try:
        remote.report("not_a_report")
    except gateway.GatewayError as e:
        bad_report = (e.code == "rejected")
    check(bad_report, "unknown report -> GatewayError('rejected')")

    print("7b. Reconcile compare: identical local vs remote, staff blocked")
    bank = {a["code"]: {"beginning": 0, "money_in": 0, "money_out": 0,
                        "ending": 0}
            for a in local.list_accounts() if a["type"] in ("ASSET",
                                                             "LIABILITY")}
    lr = local.reconcile(bank)
    rr = remote.reconcile(bank)
    check(lr == rr and "rows" in rr and "n_checked" in rr,
          "reconcile compare identical local vs remote")
    blocked_rec = False
    try:
        staff_remote.reconcile(bank)
    except gateway.GatewayError as e:
        blocked_rec = (e.code == "forbidden")
    check(blocked_rec, "staff reconcile -> forbidden")

    print("8. Profile: save remotely, read locally")
    remote.save_profile(name="Kelly's Computers", tagline="We fix things",
                        address="123 Main St", contact="hello@example.com")
    p_local = local.get_profile()
    check(p_local["name"] == "Kelly's Computers"
          and p_local["tagline"] == "We fix things",
          "profile saved via host is visible locally")
    check(local.get_profile() == remote.get_profile(),
          "profile identical local vs remote")
    check(local.profile_header_lines() == remote.profile_header_lines()
          and "Kelly's Computers" in local.profile_header_lines(),
          "profile_header_lines identical and populated")
    check(local.is_personal() == remote.is_personal(),
          "is_personal identical local vs remote")

    print("9. Account management through the gateway")
    new = remote.add_account("4242", "Test Revenue", "INCOME")
    check(new["code"] == "4242", "owner adds an account via host")
    codes_local = {a["code"] for a in local.list_accounts()}
    check("4242" in codes_local, "new account visible locally")
    remote.rename_account("4242", "Renamed Revenue")
    check(any(a["code"] == "4242" and a["name"] == "Renamed Revenue"
              for a in local.list_accounts()),
          "rename via host visible locally")
    remote.set_account_active("4242", False)
    check(any(a["code"] == "4242" and not a["active"]
              for a in local.list_accounts(include_inactive=True)),
          "deactivate via host visible locally")
    # Staff cannot manage accounts.
    blocked_acct = False
    try:
        staff_remote.add_account("9999", "Nope", "EXPENSE")
    except gateway.GatewayError as e:
        blocked_acct = (e.code == "forbidden")
    check(blocked_acct, "staff add_account -> forbidden")

    print("10. User management through the gateway")
    pw = crypto.generate_temp_password()
    res = remote.add_user("dana", roles.STAFF, pw, must_change=True)
    check(res["username"] == "dana", "owner adds a user via host")
    unames = {u["username"] for u in local.list_users()}
    check("dana" in unames, "new user visible locally")
    remote.change_role("dana", roles.MANAGER)
    check(any(u["username"] == "dana" and u["role"] == roles.MANAGER
              for u in local.list_users()), "role change via host applied")
    remote.set_user_active("dana", False)
    check(any(u["username"] == "dana" and not u["active"]
              for u in local.list_users()), "deactivate user via host applied")
    remote.remove_user("dana")
    check("dana" not in {u["username"] for u in local.list_users()},
          "remove user via host applied")
    # Staff cannot manage users.
    blocked_user = False
    try:
        staff_remote.add_user("x", roles.STAFF, "whatever12")
    except gateway.GatewayError as e:
        blocked_user = (e.code == "forbidden")
    check(blocked_user, "staff add_user -> forbidden")
    # Last-owner guard surfaces as 'rejected', not a crash.
    last_owner = False
    try:
        remote.remove_user("ben")
    except gateway.GatewayError as e:
        last_owner = (e.code == "rejected")
    check(last_owner, "removing the last owner -> rejected")

    # The new login (dana) genuinely worked end-to-end: re-add and sign in.
    pw2 = crypto.generate_temp_password()
    remote.add_user("erin", roles.STAFF, pw2)
    erin = hostnet.HostClient("127.0.0.1", PORT,
                              pinned_fingerprint=server.fingerprint())
    erin.connect()
    erin_login = erin.login("erin", pw2)
    check(erin_login["ok"] and erin_login["result"]["role"] == roles.STAFF,
          "a user added via the gateway can actually sign in")
    erin.close()

    staff_client.close()
    owner_client.close()
finally:
    server.stop()

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All gateway checks passed.")
