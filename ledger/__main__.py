# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Entry point so the program can be launched with `python3 -m ledger`.

This starts the graphical application. The command-line interface lives in
cli.py and is reached with `python3 -m ledger.cli`.
"""

from .gui import main

if __name__ == "__main__":
    main()
