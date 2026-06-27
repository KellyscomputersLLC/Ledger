# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Standalone test of the printing module (no tkinter, no real printer).

Run from the folder containing `ledger/`:
    python3 test_printing.py
"""
import sys
from ledger import printing

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


print("1. Empty text is rejected, not printed")
ok, msg = printing.print_text("")
check(ok is False and "nothing" in msg.lower(), "empty text returns (False, ...)")

print("2. Never raises, even with no printer available")
try:
    ok, msg = printing.print_text("the recovery code")
    check(isinstance(ok, bool) and isinstance(msg, str),
          "returns a (bool, str) pair without raising")
except Exception as e:
    check(False, "print_text raised: %r" % e)

print("3. A working print system reports success")
_orig_run = printing.subprocess.run
_orig_which = printing.shutil.which


class _OK:
    returncode = 0
    stderr = b""


printing.shutil.which = lambda name: "/usr/bin/" + name
printing.subprocess.run = lambda *a, **k: _OK()
ok, msg = printing.print_text("the recovery code")
check(ok is True, "rc=0 returns success")

print("4. A present-but-failing printer reports the reason, not success")


class _Fail:
    returncode = 1
    stderr = b"lp: no default destination"


printing.subprocess.run = lambda *a, **k: _Fail()
ok, msg = printing.print_text("the recovery code")
check(ok is False and "destination" in msg, "rc!=0 returns (False, stderr)")

printing.subprocess.run = _orig_run
printing.shutil.which = _orig_which

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All printing checks passed.")
