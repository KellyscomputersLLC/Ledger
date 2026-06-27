# Third-Party Notices

Ledger itself is licensed under the MIT License (see `LICENSE`).

Ledger depends on the components below, and the packaged installers
(Windows `.exe`, macOS `.app`, Linux binary) bundle copies of them. Each is
distributed under its own permissive, open-source license, all of which are
compatible with Ledger's MIT license. None of them place any additional
restriction on how Ledger itself may be used.

## cryptography (Python Cryptographic Authority)
- Used for: password key derivation (Scrypt), at-rest encryption (AES-GCM),
  and the TLS certificate and keys for the optional host/share feature.
- License: Apache License 2.0 OR BSD 3-Clause (dual-licensed).
- Source: https://github.com/pyca/cryptography

## OpenSSL
- Bundled indirectly: the `cryptography` wheels statically link OpenSSL.
- License: Apache License 2.0 (OpenSSL 3.x).
- Source: https://www.openssl.org/

## Python runtime
- The installers include a copy of the Python interpreter.
- License: Python Software Foundation License (PSF), a permissive license.
- Source: https://www.python.org/

## Tcl/Tk
- The graphical windows and dialogs use the Tk toolkit, bundled by the build.
- License: Tcl/Tk License (a BSD-style permissive license).
- Source: https://www.tcl.tk/

The full text of each license can be obtained from the project links above.
For strict redistribution compliance you may also include each project's
LICENSE file alongside the released installers; this is good practice and is
discussed in the printable setup guide.
