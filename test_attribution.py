# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Attribution is centralized: changing about.BUILT_BY / about.SUCCESSOR
updates every user-facing credit at once. No tkinter needed.

Run from the folder containing `ledger/`:
    python3 test_attribution.py
"""
import sys
import importlib
from ledger import about

problems = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        problems.append(msg)


# Start from a clean module state regardless of import order elsewhere.
importlib.reload(about)

print("1. Current attribution names the original builder")
check(about.SUCCESSOR is None, "SUCCESSOR starts unset")
check(about.builder_name() == about.BUILT_BY, "builder_name is the builder")
check(about.builder_phrase() == "Designed and built by " + about.BUILT_BY,
      "phrase reads 'Designed and built by ...'")
check(about.BUILT_BY in about.about_text(), "About text credits the builder")
check(about.builder_phrase() in about.about_text(),
      "About text uses the attribution phrase")
check(about.attribution_line() == about.builder_phrase(),
      "the one-line attribution matches the phrase")

print("2. Setting a successor updates every derived string at once")
about.SUCCESSOR = "Example FL Software Co"
check(about.builder_name() == "Example FL Software Co",
      "builder_name becomes the successor")
phrase = about.builder_phrase()
check("Originally built by " + about.BUILT_BY in phrase
      and "now maintained by Example FL Software Co" in phrase,
      "phrase shifts to 'Originally built by ... now maintained by ...'")
check(phrase in about.about_text(), "About text reflects the new phrase")
check(about.attribution_line() == phrase, "header line reflects it too")

print("3. The original builder is still acknowledged after transition")
check(about.BUILT_BY in about.builder_phrase(),
      "the original builder is not erased, just credited historically")

# leave module state clean for any later import in the same process
about.SUCCESSOR = None

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All attribution-centralization checks passed.")
