# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Standalone test of the service layer (service.py): sessions, the
authorization gate, and user administration. No tkinter, no networking.

Run from the folder containing `ledger/`:
    python3 test_service.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

from ledger import crypto, database, seed, roles, users, service

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


def fresh_protected_book():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "biz.db")
    vault, recovery = crypto.create_vault("owner-passphrase")
    crypto.save_vault(path, vault)
    key = crypto.unlock(vault, "owner-passphrase")
    conn = database.connect(path, data_key=key)
    database.init_db(conn)
    seed.seed_accounts(conn)
    conn.commit()
    return conn, vault, key, path


def session_for(conn, vault, key, path, username, role):
    return service.Session(conn, username, role,
                           vault=vault, data_key=key, db_path=path)


print("1. enable_multiuser registers the owner under a chosen username")
conn, vault, key, path = fresh_protected_book()
owner = service.Session(conn, "owner", roles.OWNER,
                        vault=vault, data_key=key, db_path=path)
service.enable_multiuser(owner, "owner-passphrase", "ben", display_name="Ben")
check(users.multiuser_enabled(conn), "multi-user is now enabled")
check(owner.username == "ben" and owner.role == roles.OWNER,
      "session became the owner 'ben'")
# The owner's passphrase still unlocks, now via the 'ben' slot; old 'owner'
# label is gone.
labels = {s["label"] for s in crypto.list_slots(vault)}
check("ben" in labels and "owner" not in labels, "login slot relabelled to 'ben'")
check(crypto.unlock(vault, "owner-passphrase") == key,
      "owner passphrase still unlocks the books")

print("2. Owner adds a manager and a staff member, with login passwords")
service.add_user(owner, "manny", roles.MANAGER, "manager-pass-1", "Manny")
service.add_user(owner, "sam", roles.STAFF, "staff-pass-1", "Sam")
check(crypto.unlock(vault, "manager-pass-1") == key,
      "the manager's password unlocks the books (slot created)")
check(crypto.unlock(vault, "staff-pass-1") == key,
      "the staff password unlocks the books")
check(users.get_user(conn, "manny")["role"] == roles.MANAGER,
      "manager record created with the right role")
# The vault on disk was updated too.
check(crypto.verify(crypto.load_vault(path), "staff-pass-1"),
      "the saved vault file includes the new slot")

print("3. Authorization gate: only the owner can manage users")
manager = session_for(conn, vault, key, path, "manny", roles.MANAGER)
staff = session_for(conn, vault, key, path, "sam", roles.STAFF)
for sess, who in ((manager, "manager"), (staff, "staff")):
    try:
        service.add_user(sess, "intruder", roles.STAFF, "x" * 8)
        check(False, "%s blocked from adding users" % who)
    except service.NotAllowed:
        check(True, "%s cannot add users" % who)
check(users.get_user(conn, "intruder") is None, "no stray user was created")

print("4. Weak passwords are refused")
try:
    service.add_user(owner, "weakling", roles.STAFF, "short")
    check(False, "weak password refused")
except ValueError:
    check(True, "passwords under 8 chars are refused")
check(users.get_user(conn, "weakling") is None, "no record left from a refusal")

print("5. Owner resets a forgotten staff password")
service.reset_password(owner, "sam", "new-staff-pass-2")
check(not crypto.verify(vault, "staff-pass-1"), "old staff password no longer works")
check(crypto.unlock(vault, "new-staff-pass-2") == key, "new staff password works")

print("6. Roles can change, but the last owner is protected")
service.change_role(owner, "sam", roles.MANAGER)
check(users.get_user(conn, "sam")["role"] == roles.MANAGER, "sam promoted")
try:
    service.change_role(owner, "ben", roles.STAFF)
    check(False, "last-owner demotion refused")
except ValueError:
    check(True, "cannot demote the only owner")

print("7. A user changes their own password (needs the current one)")
service.change_own_password(manager, "manager-pass-1", "manager-pass-2")
check(crypto.unlock(vault, "manager-pass-2") == key, "manager's new password works")
try:
    service.change_own_password(manager, "wrong-old", "another-pass-3")
    check(False, "wrong current password refused")
except ValueError:
    check(True, "changing own password needs the correct current one")

print("8. Removing a user revokes their login")
service.add_user(owner, "temp", roles.STAFF, "temp-pass-1")
check(crypto.verify(vault, "temp-pass-1"), "temp can log in before removal")
service.remove_user(owner, "temp")
check(users.get_user(conn, "temp") is None, "temp record removed")
check(not crypto.verify(vault, "temp-pass-1"),
      "temp's password no longer opens the books (slot revoked)")

print("9. add_user rolls back the record if the login slot can't be saved")
_orig = crypto.add_slot
crypto.add_slot = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
try:
    service.add_user(owner, "ghost", roles.STAFF, "ghost-pass-1")
    check(False, "failure surfaced")
except RuntimeError:
    check(True, "a slot-save failure raises")
finally:
    crypto.add_slot = _orig
check(users.get_user(conn, "ghost") is None,
      "the user record was rolled back, no half-made account")

print("10. Audit log: owner/manager can read it, staff cannot")
audit_owner = service.view_audit(owner)
check(len(audit_owner) > 0, "owner can read the audit log")
mgr = session_for(conn, vault, key, path, "sam", roles.MANAGER)  # sam is mgr now
check(len(service.view_audit(mgr)) > 0, "manager can read the audit log")
staff2 = session_for(conn, vault, key, path, "x", roles.STAFF)
try:
    service.view_audit(staff2)
    check(False, "staff blocked from the audit log")
except service.NotAllowed:
    check(True, "staff cannot read the audit log")
# A couple of recorded actions are present.
actions = {e["action"] for e in audit_owner}
print("11. Per-user login (unlock_as) can't be used to impersonate")
# 'ben' is owner, 'sam' is a manager now, both on the same data key.
check(crypto.unlock_as(vault, "ben", "owner-passphrase") == key,
      "owner logs in with their own username + passphrase")
try:
    crypto.unlock_as(vault, "ben", "new-staff-pass-2")  # sam's password
    check(False, "another user's password rejected for 'ben'")
except ValueError:
    check(True, "one user's password cannot open another user's account")
try:
    crypto.unlock_as(vault, "nobody", "new-staff-pass-2")
    check(False, "unknown username rejected")
except ValueError:
    check(True, "unknown username is rejected")
conn.close()

print("12. One-time password + forced password change at first sign-in")
conn2, vault2, key2, path2 = fresh_protected_book()
owner2 = service.Session(conn2, "owner", roles.OWNER,
                         vault=vault2, data_key=key2, db_path=path2)
service.enable_multiuser(owner2, "owner-passphrase", "boss")
temp = crypto.generate_temp_password()
service.add_user(owner2, "newhire", roles.STAFF, temp, must_change=True)
check(users.get_user(conn2, "newhire")["must_change_pw"] is True,
      "new user is flagged to change password at first sign-in")
v = crypto.load_vault(path2)
check(crypto.unlock_as(v, "newhire", temp) == key2,
      "one-time password signs in (exact)")
check(crypto.unlock_as(v, "newhire", temp.lower()) == key2,
      "one-time password is case-insensitive")
# First sign-in: they set their own password; flag clears, temp stops working.
newhire = service.Session(conn2, "newhire", roles.STAFF,
                          vault=crypto.load_vault(path2), data_key=key2,
                          db_path=path2)
service.complete_first_login(newhire, "my-own-password")
check(users.get_user(conn2, "newhire")["must_change_pw"] is False,
      "the flag clears after they set their own password")
v = crypto.load_vault(path2)
check(crypto.unlock_as(v, "newhire", "my-own-password") == key2,
      "their chosen password works")
try:
    crypto.unlock_as(v, "newhire", temp)
    check(False, "old one-time password rejected")
except ValueError:
    check(True, "the one-time password no longer works")
# A too-short first-login password is refused.
try:
    service.complete_first_login(newhire, "short")
    check(False, "weak first-login password refused")
except ValueError:
    check(True, "first-login password must meet the minimum length")

print()
print("password rotation (90-day expiry)")
# Fresh after setting their own password: no change required.
check(service.password_change_required(newhire) is None,
      "no change required right after setting a password")
# A one-time-password user is flagged for first-login change.
temp2 = crypto.generate_temp_password()
service.add_user(owner2, "tempbob", roles.STAFF, temp2, must_change=True)
tempbob = service.Session(conn2, "tempbob", roles.STAFF,
                          vault=crypto.load_vault(path2), data_key=key2,
                          db_path=path2)
check(service.password_change_required(tempbob) == "first_login",
      "a one-time password requires a first-login change")
# Age the newhire's password past the limit -> expired.
old = (datetime.now()
       - timedelta(days=service.PASSWORD_MAX_AGE_DAYS + 1)).isoformat(
           timespec="seconds")
users.stamp_password_set(conn2, "newhire", when=old)
check(service.password_change_required(newhire) == "expired",
      "a password older than the limit is expired")
# Just under the limit is still fine.
recent = (datetime.now()
          - timedelta(days=service.PASSWORD_MAX_AGE_DAYS - 1)).isoformat(
              timespec="seconds")
users.stamp_password_set(conn2, "newhire", when=recent)
check(service.password_change_required(newhire) is None,
      "a password just under the limit is still valid")
# Setting a new password clears the expiry.
users.stamp_password_set(conn2, "newhire", when=old)
service.complete_first_login(newhire, "fresh-password-9")
check(service.password_change_required(newhire) is None,
      "setting a new password clears the expiry")

conn2.close()

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All service-layer checks passed.")
