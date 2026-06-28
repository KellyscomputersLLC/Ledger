# Ledger -- PyInstaller build spec (Linux, Windows, macOS)
# SPDX-License-Identifier: MIT
#
# Build (always ON the target OS -- you cannot cross-compile these):
#     pyinstaller ledger.spec --noconfirm
#
# Output lands in ./dist :
#     Linux    -> dist/Ledger            (single binary)
#     Windows  -> dist/Ledger.exe        (single .exe, no console window)
#     macOS    -> dist/Ledger.app        (app bundle)
#
# This one spec is used unchanged on all three platforms; it branches on
# sys.platform only for the icon and the macOS .app wrapper.

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# IMPORTANT: put the project root (the folder holding this spec, which is also
# the folder that contains the `ledger/` package) on sys.path *before* calling
# the collect_* helpers below. Those helpers resolve the package by importing
# it in an isolated probe, and PyInstaller runs the spec with a sys.path that
# does NOT include the project root. Without this line, `import ledger` fails
# during the build, both helpers silently return EMPTY, and the build ships
# with NO package data (blank Help panel, icons falling back to the drawn
# emblem) and NO lazily-imported submodules. SPECPATH is the spec's directory,
# injected by PyInstaller. This is verified to flow through to the isolated
# probe, so collect_submodules/collect_data_files see the real package.
if SPECPATH not in sys.path:
    sys.path.insert(0, SPECPATH)

# Pull in the WHOLE ledger package so any submodule that is imported lazily or
# by name (networking, discovery, printing, ...) is never dropped, plus any
# non-code data shipped inside the package.
hiddenimports = collect_submodules("ledger")
datas = collect_data_files("ledger")

# Belt-and-suspenders: the app cannot start without its data files, so if the
# collection above ever comes back empty (e.g. a future PyInstaller changes how
# the isolated probe resolves sys.path), fail loudly at build time rather than
# shipping a silently-broken installer. This guard turned an invisible runtime
# bug into a visible build error.
if not any(dest == "ledger" for _src, dest in datas):
    raise SystemExit(
        "ledger.spec: package data files were not collected -- the Help panel "
        "and icons would be missing from this build. Check that the 'ledger' "
        "package is importable from SPECPATH during the build."
    )

# crypto.py imports these THREE lazily (inside functions), so static analysis
# could miss them. hostnet.py also imports `cryptography` at top level, which
# activates PyInstaller's bundled cryptography hook -- but we list the lazy
# pieces explicitly as a belt-and-suspenders guard against a runtime
# ImportError in a packaged build.
hiddenimports += [
    "cryptography.hazmat.primitives.kdf.scrypt",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.exceptions",
]

# Runtime images (the sign-in screen's `ledger-icon.png`, the welcome tour's
# `logo.png`) are looked up at runtime via os.path.dirname(__file__) -- i.e.
# from INSIDE the ledger package folder. So they must live next to gui.py in
# the package, where collect_data_files("ledger") above already bundles them
# to the right place. (If the files are absent the app still runs, using its
# built-in drawn emblem.) Nothing to add here for them.

# Icon for the built executable / app. Windows wants .ico, macOS wants .icns;
# these live in ./assets and are used by PyInstaller at build time (they are a
# separate concern from the in-app images above).
icon = None
if sys.platform.startswith("win") and os.path.exists("assets/ledger.ico"):
    icon = "assets/ledger.ico"
elif sys.platform == "darwin" and os.path.exists("assets/ledger.icns"):
    icon = "assets/ledger.icns"

a = Analysis(
    ["run_ledger.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Ledger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,                 # GUI app -- never pop a terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,              # builds for the runner's own CPU arch
    codesign_identity=None,        # set when you add signing (see PACKAGING.md)
    entitlements_file=None,
    icon=icon,
)

# macOS: wrap the binary in a real .app bundle so it behaves like a native app.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Ledger.app",
        icon=icon,
        bundle_identifier="com.kellyscomputers.ledger",
        info_plist={
            "CFBundleName": "Ledger",
            "CFBundleDisplayName": "Ledger",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
