; Ledger -- Windows installer script (Inno Setup 6)
; SPDX-License-Identifier: MIT
;
; Builds a friendly Setup.exe from the PyInstaller output (dist\Ledger.exe):
; it installs Ledger, adds a Start Menu shortcut (and an optional desktop
; shortcut), and registers a proper uninstaller in "Apps & features".
;
; Compile ON WINDOWS only (Inno Setup does not run on Linux/macOS):
;   - CI does this automatically (see .github/workflows/build.yml), or
;   - locally:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows\Ledger.iss
;     (or open this file in the Inno Setup IDE and press Compile)
;
; Signing: this script does not sign anything itself. CI signs the exe and the
; finished installer IF you provide a code-signing certificate (see the
; "Code signing" section of PACKAGING.md). Without a certificate the installer
; still builds and runs, but Windows shows a SmartScreen warning on first run.
;
; Prerequisite: dist\Ledger.exe must already exist (run PyInstaller first).
; Output:       Output\Ledger-Setup-1.0.0.exe  (at the repo root)

#define MyAppName "Ledger"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Kelly's Computers LLC"
#define MyAppExeName "Ledger.exe"

[Setup]
; A fixed, unique identity for this product. Keep it CONSTANT across versions
; so an installer upgrades an existing install cleanly instead of duplicating.
AppId={{8326463F-673D-41D1-B741-9637A775E7C4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

; All-users install into Program Files (prompts once for admin via UAC). The
; app still stores each user's books in their own %APPDATA%\Ledger, so it never
; needs to write into the read-only install folder.
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

; Only 64-bit Windows; install into the real 64-bit Program Files.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

OutputDir=..\..\Output
OutputBaseFilename=Ledger-Setup-{#MyAppVersion}
SetupIconFile=..\..\assets\ledger.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; \
    Flags: nowait postinstall skipifsilent
