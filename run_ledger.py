#!/usr/bin/env python3
# Ledger -- packaging entry point
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Launcher used by PyInstaller to build the desktop app.

The app normally runs with `python3 -m ledger.gui`; PyInstaller needs a plain
script as its starting point, so this simply calls the same main() that the
module's `if __name__ == "__main__"` block calls. Keeping it tiny means the
build has a single, obvious entry and the package itself is unchanged.
"""

from ledger.gui import main

if __name__ == "__main__":
    main()
