# Packaging Ledger for Linux, Windows, and macOS

Ledger ships as a self-contained app per platform, built with
[PyInstaller](https://pyinstaller.org). The single `ledger.spec` is used
unchanged on all three operating systems.

## The one rule that shapes everything

**You build on the OS you are targeting.** A macOS `.app` can only be built on
macOS, a Windows `.exe` only on Windows, a Linux binary only on Linux. There is
no reliable cross-compiling. That is why the real builds run in GitHub Actions
(`.github/workflows/build.yml`), which gives us a clean machine of each kind.

## Layout these files expect

```
your-repo/
├── ledger/                # the package (gui.py, database.py, crypto.py, ...)
│   ├── __init__.py
│   ├── ledger-icon.png    # in-app icon (sign-in screen) — bundled from here
│   └── logo.png           # in-app logo (welcome tour) — bundled from here
├── run_ledger.py          # tiny launcher PyInstaller starts from
├── ledger.spec            # the build recipe (all 3 OSes)
├── requirements.txt       # third-party deps to bundle (cryptography)
├── assets/                # build-time app icons
│   ├── ledger.ico         #   Windows executable icon
│   └── ledger.icns        #   macOS app icon
└── .github/workflows/build.yml
```

## Build locally (to test on your own machine)

```bash
python -m pip install --upgrade pip
pip install pyinstaller
pip install -r requirements.txt        # if you have any deps
pyinstaller ledger.spec --noconfirm
```

Result in `dist/`:

| OS      | Output            | Hand to users as            |
|---------|-------------------|-----------------------------|
| Linux   | `dist/Ledger`     | the binary (or a `.tar.gz`) |
| Windows | `dist/Ledger.exe` | the `.exe` (or a `.zip`)    |
| macOS   | `dist/Ledger.app` | the `.app` (zipped)         |

## Cut a release (all three at once)

1. Push a tag: `git tag v1.0.0 && git push origin v1.0.0`.
2. The workflow builds Linux, Windows, macOS-Intel and macOS-AppleSilicon, then
   attaches all four archives to the `v1.0.0` Release.
3. To dry-run without releasing, use the **Run workflow** button on the Actions
   tab and download the artifacts from that run.

## Before the first green build — status

1. **Dependencies — RESOLVED.** Every module's imports were scanned: the only
   third-party package is `cryptography` (crypto.py + hostnet.py), now pinned in
   `requirements.txt`. It has prebuilt wheels for all four targets, so CI needs
   no compiler. There are no dynamic/by-name imports, so nothing hides from
   PyInstaller's analysis.
2. **Data location — RESOLVED.** Confirmed against `paths.py`: data goes to
   `%APPDATA%\Ledger` on Windows and `~/.ledger` on Linux *and macOS* (a home
   dot-folder), backups to `~/Documents/Ledger Backups`. All per-user and
   writable, never beside the binary — so a packaged build has nowhere it needs
   to write that it can't. (Optional polish, pre-release only: macOS could use
   `~/Library/Application Support/Ledger` instead of `~/.ledger`; both work, and
   `~/.ledger` is simpler. Worth changing only now, before anyone has Mac data
   there.)
3. **Assets — DONE.** App icons `assets/ledger.ico` (Windows) and
   `assets/ledger.icns` (macOS) are generated from `ledger-icon.png` and wired
   into the spec. The in-app images (`ledger-icon.png`, `logo.png`) are placed
   inside the `ledger/` package folder, where the runtime `__file__` lookup
   finds them and `collect_data_files` bundles them. Note: the source art is
   160×160, which is small for a Mac dock icon (it renders up to 512+) — a
   ≥512px (ideally 1024px) master PNG would make the icon noticeably sharper.

## Signing and notarization (the "scary warning" problem)

Unsigned apps **run**, but the OS shows a warning the first time:

- **Windows** — SmartScreen "unknown publisher". Removing it needs an
  Authenticode code-signing certificate (a paid cert from a CA).
- **macOS** — Gatekeeper blocks unsigned apps by default; users must
  right-click → Open, or you sign with an Apple Developer ID ($99/yr) and
  notarize with `notarytool`. This is the bigger friction of the two.
- **Linux** — no signing gate; the binary just runs.

Signing is a later step, not required to start distributing. When you want it,
it slots into the spec (`codesign_identity`) and the workflow (an extra
notarize step with secrets). Flag it and we'll do it as its own slice.

## Installers

**Windows — done.** A real `Setup.exe` is built by `installer\windows\Ledger.iss`
(Inno Setup 6). CI compiles it automatically on the Windows runner, so the
`Ledger-windows-x64` artifact contains BOTH:

- `Output\Ledger-Setup-1.0.0.exe` — the installer (all-users install into
  `C:\Program Files\Ledger`; prompts once for admin via UAC). Creates a Start
  Menu shortcut, a desktop shortcut, and an uninstaller in "Apps & features".
  Each Windows user's books still live in their own `%APPDATA%\Ledger`.
- `Ledger-windows-x64-portable.zip` — the bare `Ledger.exe` for anyone who
  prefers no install.

To build the installer locally on Windows (after `pyinstaller ledger.spec`):

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows\Ledger.iss
```

## Code signing (removing the SmartScreen warning)

Unsigned, the installer and app **run fine** but Windows shows a SmartScreen
warning on first launch ("Windows protected your PC" → More info → Run anyway).
The *only* way to remove it is to sign with a real code-signing certificate;
no build setting, manifest, or self-signed certificate removes it for end
users. Tiers: an **OV** certificate clears "unknown publisher" but SmartScreen
may still warn until the app earns download reputation; an **EV** certificate is
trusted instantly but costs more. Certificates run roughly $200–$500/yr from a
CA (DigiCert, Sectigo, …) and require verifying your business identity.

The build is already wired to sign automatically once you have one — no
workflow edits needed. Add two repository secrets (Settings → Secrets and
variables → Actions):

- `WINDOWS_PFX_BASE64` — your `.pfx` certificate, base64-encoded. Create it
  with: `certutil -encode cert.pfx cert.txt` (then paste the body), or on any
  machine: `base64 -w0 cert.pfx`.
- `WINDOWS_PFX_PASSWORD` — the certificate's password.

On the next run the workflow signs both `Ledger.exe` and the finished
`Setup.exe` (SHA-256, timestamped). With no secrets set, the signing steps skip
themselves and the build proceeds unsigned. Note: certificates issued since
2023 live on a hardware token / cloud HSM, which a `.pfx`-file flow may not
support — if yours is token-based, the CA's cloud-signing tool replaces the
signtool step, and I can adjust the workflow for that.

**macOS / Linux — later (optional).** A `.dmg` on macOS and a `.deb` on Linux
are the usual friendlier formats; each is an extra packaging step on top of the
`.app` / binary the build already produces.
