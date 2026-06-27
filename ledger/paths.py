# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Where Ledger keeps its files, chosen per operating system.

Ledger runs on both Linux and Windows from the same folder. The one
thing that genuinely differs between the two is *where* an application
should keep its data, because each system has its own convention:

  * Linux  ->  a hidden folder in the user's home directory,
               ~/.ledger/
  * Windows ->  the user's Application Data area,
               C:\\Users\\<name>\\AppData\\Roaming\\Ledger\\

This module works that out once, so the rest of the program never has
to care which operating system it is running on -- it just asks for
`data_dir()` and gets the right place.
"""

import os
import sys


def _is_windows():
    return os.name == "nt" or sys.platform.startswith("win")


def data_dir():
    """
    The folder where this user's Ledger data lives. Created if it
    does not exist yet. Same idea on both platforms -- a private,
    per-user folder -- just following each system's convention.
    """
    if _is_windows():
        # %APPDATA% is the standard per-user data area on Windows.
        # Fall back to the home directory if it is somehow not set.
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "Ledger")
    else:
        # On Linux/macOS, a dot-folder in the home directory is the
        # long-standing convention for a program's private data.
        folder = os.path.join(os.path.expanduser("~"), ".ledger")

    os.makedirs(folder, exist_ok=True)
    return folder


def default_db_path():
    """The default ledger database file for this user."""
    return os.path.join(data_dir(), "ledger.db")


def backups_dir():
    """The folder where backups are kept (inside the data folder)."""
    folder = os.path.join(data_dir(), "backups")
    os.makedirs(folder, exist_ok=True)
    return folder


def documents_dir():
    """
    The user's Documents folder -- the visible, familiar place people
    expect to find their files. This is where Ledger keeps backups by
    default (in a 'Ledger Backups' sub-folder), so they are easy to
    find rather than tucked away in a hidden system folder.

    On Windows, macOS and most Linux desktops this is ~/Documents. The
    folder is not created here; it is created when a backup is actually
    written.
    """
    return os.path.join(os.path.expanduser("~"), "Documents")
