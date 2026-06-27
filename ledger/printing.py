# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Printing a short piece of text -- the recovery code -- on the user's printer,
without leaving a lasting copy on the computer wherever that can be avoided.

There is no single cross-platform "print this text" call in the standard
library, so this does the right thing per operating system:

  * Linux / macOS: the text is sent straight to the printing system (lp, or
    lpr) on its standard input, so NOTHING is written to disk at all.
  * Windows: there is no stdin route to the spooler, so the text is written to
    a temporary file, handed to Windows' normal print handler, and the
    temporary file is then deleted once the spooler has had time to read it.
    That file lives only in the system temp area, never among the user's
    documents.

This matters because the recovery code is a secret: we deliberately do NOT
offer a clipboard "copy" (which would linger in the clipboard and in clipboard
history), and we keep any on-disk trace as brief and out-of-the-way as we can.

Every path is best-effort and never raises: it returns (ok, message) so the
caller can tell the user plainly whether printing worked.
"""

import os
import sys
import shutil
import subprocess
import tempfile


def _is_windows():
    return os.name == "nt" or sys.platform.startswith("win")


def print_text(text, schedule_delete=None):
    """Print `text` on the default printer. Returns (ok, message).

    `schedule_delete`, if given, is called as schedule_delete(func, seconds)
    to remove the Windows temporary file after the spooler has had time to
    read it (the GUI passes a small adapter around Tk's `after`). If it is not
    given, a background timer is used instead. It is unused on Linux/macOS,
    where no file is created.
    """
    if not text:
        return False, "There was nothing to print."
    try:
        if _is_windows():
            return _print_windows(text, schedule_delete)
        return _print_unix(text)
    except Exception as e:
        return False, str(e)


def _print_unix(text):
    """Send text to lp or lpr on stdin -- no temp file is created."""
    data = text.encode("utf-8")
    for cmd in (["lp"], ["lpr"]):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            proc = subprocess.run(cmd, input=data,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        except Exception:
            continue
        if proc.returncode == 0:
            return True, "Sent to the printer."
        # A printing tool exists but failed (often: no printer configured).
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        return False, err or "The printer could not be reached."
    return False, ("No printing system was found on this computer. You can "
                   "write the code down instead.")


def _print_windows(text, schedule_delete):
    """Write a temp file, print it with the default handler, then delete it
    once the spooler has had time to read it."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="ledger_recovery_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        # os.startfile exists only on Windows; the _is_windows() guard in
        # print_text() ensures we only reach here on Windows.
        os.startfile(path, "print")
    except Exception as e:
        try:
            os.remove(path)
        except OSError:
            pass
        return False, str(e)

    def _cleanup():
        try:
            os.remove(path)
        except OSError:
            pass

    # Give the spooler time to read the file before removing it.
    if schedule_delete is not None:
        try:
            schedule_delete(_cleanup, 15)
        except Exception:
            _cleanup()
    else:
        try:
            import threading
            threading.Timer(15, _cleanup).start()
        except Exception:
            _cleanup()
    return True, "Sent to the printer."
