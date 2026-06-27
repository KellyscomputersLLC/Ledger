# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
About / attribution for Ledger.

This is the program's OWN information -- who designed and built it, and
the version. Unlike the business profile (which is the user's data and
lives in the data file), this is part of the application itself. It is
the same no matter whose books are open, and it shows on the About
screen.

If Ledger is ever passed to someone else to use, this attribution
stays with the program, while their own business profile stays with
their own data file. The two never mix.
"""

from . import __version__

# --- who built and maintains Ledger ---------------------------------------
#
# All user-facing attribution flows from the two names below, so changing who
# is credited is a one-place edit rather than a hunt through the program.
#
# BUILT_BY is the business that created Ledger. SUCCESSOR is for the planned
# transition: Kelly's Computers LLC is expected to close in 2027, with the
# project's ongoing development continuing under a new business. When that
# happens, set SUCCESSOR to the new name -- the About screen, the recovery-code
# warnings, and the printed recovery sheet all update at once, and the wording
# shifts to "Originally built by <BUILT_BY>, now maintained by <SUCCESSOR>".
# Until then, leave SUCCESSOR as None.
#
# (The source-file header comments and the Help text mention the name in plain
# prose and are edited directly; only the running, user-facing attribution is
# centralised here.)
BUILT_BY = "Kelly's Computers LLC"
SUCCESSOR = None


def builder_phrase():
    """The full attribution sentence, e.g. for the About-screen header. Adapts
    automatically once SUCCESSOR is set for the transition."""
    if SUCCESSOR:
        return f"Originally built by {BUILT_BY}, now maintained by {SUCCESSOR}"
    return f"Designed and built by {BUILT_BY}"


def builder_name():
    """The single name to credit in running text (such as the recovery-code
    warning). Once there is a successor, that is the current maintainer to
    name; otherwise it is the original builder."""
    return SUCCESSOR or BUILT_BY


def attribution_line():
    """The one-line attribution, e.g. for a window header."""
    return builder_phrase()


def about_text():
    """The full About-screen text. Built fresh so it always reflects the
    current attribution (BUILT_BY / SUCCESSOR above)."""
    return (
        f"Ledger version {__version__}\n"
        f"{builder_phrase()}\n\n"
        "Ledger is free, open-source software. Anyone is welcome to read how "
        "it works \u2014 and that openness is also why its encryption stays "
        "strong: the security comes from your passphrase, never from secrecy "
        "in the code.\n\n"
        "A double-entry accounting tool for business and personal books. "
        "Ledger keeps a chart of accounts, records balanced journal entries, "
        "and produces the trial balance, income statement, balance sheet, and "
        "general ledger reports.\n\n"
        "Your business details (shown on your reports) are stored with your "
        "own data file and are private to your books. This attribution is "
        "part of the program itself."
    )
