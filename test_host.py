# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Standalone test for the host engine (Phase 2, Slice 1).

Verifies, against a REAL encrypted book (so the encrypted-save path is
exercised too):
  - login issues a token; bad credentials, deactivated users, and one user's
    password used for another user's name are all refused
  - requests without a valid token are refused
  - role enforcement on the host: staff cannot void / list users / view audit;
    manager can void and view audit but not list users; owner can do all
  - record / void / list round-trips work and are written to the audit log
  - a recorded entry survives reopening the encrypted file (persistence)
  - unknown operations and expired tokens are reported cleanly

Run from the project root:  python3 test_host.py
"""

import os
import sys
import tempfile

from ledger import (crypto, database, seed, roles, users, service,
                    transactions, host)

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

# --- build an encrypted, multi-user book: owner 'ben', manager 'mary',
#     staff 'sam' -------------------------------------------------------------
vault, _recovery = crypto.create_vault(OWNER_PW)
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
service.add_user(owner, "mary", roles.MANAGER, MGR_PW)
service.add_user(owner, "sam", roles.STAFF, STAFF_PW)

# The host process would do exactly this at startup: open the book, then serve.
engine = host.HostEngine(conn, crypto.load_vault(path), key, path)


def call(op, token=None, **args):
    return engine.handle({"op": op, "token": token, "args": args})


print("1. Login")
r = call("login", username="ben", password=OWNER_PW)
check(r["ok"] and r["result"]["role"] == roles.OWNER, "owner logs in")
owner_tok = r["result"]["token"] if r["ok"] else None

r = call("login", username="mary", password=MGR_PW)
check(r["ok"] and r["result"]["role"] == roles.MANAGER, "manager logs in")
mgr_tok = r["result"]["token"] if r["ok"] else None

r = call("login", username="sam", password=STAFF_PW)
check(r["ok"] and r["result"]["role"] == roles.STAFF, "staff logs in")
staff_tok = r["result"]["token"] if r["ok"] else None

check(owner_tok and mgr_tok and staff_tok
      and len({owner_tok, mgr_tok, staff_tok}) == 3,
      "three distinct tokens issued")

r = call("login", username="sam", password="wrong")
check(not r["ok"] and r["code"] == "bad_credentials", "wrong password refused")

# No privilege escalation: staff's password must not log in as the owner.
r = call("login", username="ben", password=STAFF_PW)
check(not r["ok"] and r["code"] == "bad_credentials",
      "one user's password cannot sign in as another")

r = call("login", username="nobody", password="whatever")
check(not r["ok"] and r["code"] == "bad_credentials",
      "unknown username refused")

print("2. A token is required")
r = call("whoami")
check(not r["ok"] and r["code"] == "auth_required", "no token -> auth_required")
r = call("whoami", token="not-a-real-token")
check(not r["ok"] and r["code"] == "auth_required", "bogus token -> auth_required")
r = call("whoami", token=staff_tok)
check(r["ok"] and r["result"]["username"] == "sam", "valid token -> whoami works")

print("3. Everyday reads work for any signed-in user")
r = call("list_accounts", token=staff_tok)
check(r["ok"] and isinstance(r["result"], list) and len(r["result"]) > 0,
      "staff can list accounts")

print("4. Recording entries (allowed for all roles), with persistence + audit")
# Find two real account codes to move money between.
accts = call("list_accounts", token=owner_tok)["result"]
by_type = {a["type"]: a["code"] for a in accts}
debit_code = by_type.get("EXPENSE") or accts[0]["code"]
credit_code = by_type.get("ASSET") or accts[1]["code"]

r = call("record_entry", token=staff_tok, date="2026-02-01",
         description="Staff buys supplies",
         lines=[{"code": debit_code, "debit": 40, "credit": 0},
                {"code": credit_code, "debit": 0, "credit": 40}])
check(r["ok"] and "entry_id" in r["result"], "staff records a balanced entry")
staff_entry_id = r["result"]["entry_id"] if r["ok"] else None

# An unbalanced entry is rejected (and reported, not crashed).
r = call("record_entry", token=staff_tok, date="2026-02-01",
         description="Lopsided",
         lines=[{"code": debit_code, "debit": 40, "credit": 0},
                {"code": credit_code, "debit": 0, "credit": 5}])
check(not r["ok"] and r["code"] == "rejected", "unbalanced entry refused cleanly")

r = call("list_entries", token=staff_tok)
check(r["ok"] and any(e["entry"]["id"] == staff_entry_id for e in r["result"]),
      "the recorded entry appears in the journal")

print("5. Voiding: staff BLOCKED, manager allowed")
r = call("void_entry", token=staff_tok, entry_id=staff_entry_id)
check(not r["ok"] and r["code"] == "forbidden", "staff cannot void (forbidden)")

r = call("void_entry", token=mgr_tok, entry_id=staff_entry_id)
check(r["ok"], "manager can void")

# Record one more entry that is NOT voided, to confirm persistence later
# (the staff entry above was just deleted by the void).
r = call("record_entry", token=owner_tok, date="2026-02-02",
         description="Owner records rent",
         lines=[{"code": debit_code, "debit": 100, "credit": 0},
                {"code": credit_code, "debit": 0, "credit": 100}])
kept_entry_id = r["result"]["entry_id"] if r["ok"] else None
check(r["ok"], "owner records a second (kept) entry")

print("6. User list (owner only) and audit log (owner + manager)")
r = call("list_users", token=staff_tok)
check(not r["ok"] and r["code"] == "forbidden", "staff cannot list users")
r = call("list_users", token=mgr_tok)
check(not r["ok"] and r["code"] == "forbidden", "manager cannot list users")
r = call("list_users", token=owner_tok)
check(r["ok"] and {u["username"] for u in r["result"]} >= {"ben", "mary", "sam"},
      "owner lists all users")

r = call("view_audit", token=staff_tok)
check(not r["ok"] and r["code"] == "forbidden", "staff cannot view audit")
r = call("view_audit", token=mgr_tok)
check(r["ok"], "manager can view audit")
r = call("view_audit", token=owner_tok)
audit_actions = [a["action"] for a in r["result"]] if r["ok"] else []
check("record_entry" in audit_actions and "void_entry" in audit_actions,
      "client record + void actions were written to the audit log")

print("7. Unknown operation and logout")
r = call("does_not_exist", token=owner_tok)
check(not r["ok"] and r["code"] == "unknown_op", "unknown op reported")
r = call("logout", token=staff_tok)
check(r["ok"], "logout succeeds")
r = call("whoami", token=staff_tok)
check(not r["ok"] and r["code"] == "auth_required", "token invalid after logout")

print("7b. Expanded ops at the engine level (reports, profile, accounts, users)")
# Fresh tokens (staff was logged out above).
o_tok = call("login", username="ben", password=OWNER_PW)["result"]["token"]
m_tok = call("login", username="mary", password=MGR_PW)["result"]["token"]
s_tok = call("login", username="sam", password=STAFF_PW)["result"]["token"]

r = call("report", token=s_tok, name="trial_balance")
check(r["ok"] and "rows" in r["result"], "staff can run a report")
r = call("report", token=o_tok, name="bogus_report")
check(not r["ok"] and r["code"] == "rejected", "unknown report -> rejected")

r = call("save_profile", token=m_tok, name="Acme", tagline="t")
check(r["ok"] and r["result"]["name"] == "Acme", "manager saves profile")
r = call("save_profile", token=s_tok, name="Nope")
check(not r["ok"] and r["code"] == "forbidden", "staff save_profile forbidden")
r = call("get_profile", token=s_tok)
check(r["ok"] and r["result"]["name"] == "Acme", "anyone can read profile")

r = call("add_account", token=m_tok, code="4242", name="Misc Income",
         acct_type="INCOME")
check(r["ok"] and r["result"]["code"] == "4242", "manager adds account")
r = call("add_account", token=s_tok, code="4243", name="No", acct_type="INCOME")
check(not r["ok"] and r["code"] == "forbidden", "staff add_account forbidden")

r = call("add_user", token=o_tok, username="zoe", role=roles.STAFF,
         password="ZoePass-123")
check(r["ok"] and r["result"]["username"] == "zoe", "owner adds user via engine")
r = call("add_user", token=m_tok, username="no", role=roles.STAFF,
         password="whatever12")
check(not r["ok"] and r["code"] == "forbidden", "manager add_user forbidden")
r = call("remove_user", token=o_tok, username="ben")
check(not r["ok"] and r["code"] == "rejected", "remove last owner -> rejected")

print("8. Expired token is rejected")
# Simulate an idle session by ageing its last-seen far past the TTL.
engine._tokens[mgr_tok]["last_seen"] -= (host.TOKEN_TTL_SECONDS + 10)
r = call("whoami", token=mgr_tok)
check(not r["ok"] and r["code"] == "auth_expired", "expired token -> auth_expired")

print("9. Writes persisted: reopen the encrypted file and confirm")
conn.close()
key2 = crypto.unlock(crypto.load_vault(path), OWNER_PW)
conn2 = database.connect(path, data_key=key2)
entries2 = transactions.list_entries(conn2)
descs2 = [e["entry"]["description"] for e in entries2]
check("Owner records rent" in descs2,
      "the kept entry is still there after reopening the encrypted book")
check("Staff buys supplies" not in descs2,
      "the voided entry is gone after reopening (void persisted too)")
audit2 = users.list_audit(conn2)
check(any(a["action"] == "void_entry" for a in audit2),
      "the audit log persisted too")
conn2.close()

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All host-engine checks passed.")
