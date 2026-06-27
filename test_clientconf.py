# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""Checks for clientconf: the client-side trust store (pinned host
fingerprints) and last-connection memory. Runs headless -- no GUI, no
network -- against a throwaway data folder."""

import os
import tempfile
import shutil

from ledger import clientconf, paths


def _fresh_data_dir():
    """Point clientconf at an empty temp folder and return a cleanup fn."""
    tmp = tempfile.mkdtemp(prefix="ledger-clientconf-")
    orig = paths.data_dir
    paths.data_dir = lambda: tmp
    def restore():
        paths.data_dir = orig
        shutil.rmtree(tmp, ignore_errors=True)
    return tmp, restore


def run():
    tmp, restore = _fresh_data_dir()
    try:
        FP1 = "AA:BB:CC:DD:" + "11" * 12
        FP2 = "99:88:77:66:" + "22" * 12

        # 1. Nothing remembered yet.
        assert clientconf.get_pin("host.local", 8765) is None
        assert clientconf.known_hosts() == []
        assert clientconf.last_connection() == (None, None)
        # No file need exist for reads to be safe.
        print("1. first-time reads are empty and safe: OK")

        # 2. Pin a host, then read it back.
        clientconf.remember_host("Office-PC", 8765, FP1, label="Front desk")
        assert clientconf.get_pin("Office-PC", 8765) == FP1
        rec = clientconf.get_host("office-pc", 8765)   # case-insensitive host
        assert rec is not None and rec["fingerprint"] == FP1
        assert rec["label"] == "Front desk"
        assert rec["host"] == "Office-PC"               # original casing kept
        assert rec["added"] and rec["updated"]
        print("2. pin/get round-trips, host match is case-insensitive: OK")

        # 3. Port is part of the identity: same host, different port = miss.
        assert clientconf.get_pin("Office-PC", 9999) is None
        print("3. a different port is a different host: OK")

        # 4. Re-pin (the cert legitimately changed): fingerprint updates,
        #    first-seen time is preserved, label kept when not re-supplied.
        first_added = clientconf.get_host("office-pc", 8765)["added"]
        clientconf.remember_host("office-pc", 8765, FP2)
        rec = clientconf.get_host("office-pc", 8765)
        assert rec["fingerprint"] == FP2
        assert rec["added"] == first_added
        assert rec["label"] == "Front desk"
        print("4. re-pin updates fingerprint, preserves first-seen + label: OK")

        # 5. A second host coexists; known_hosts lists both, sorted.
        clientconf.remember_host("10.0.0.5", 8765, FP1)
        hosts = clientconf.known_hosts()
        assert len(hosts) == 2
        keys = [h["host"].lower() + ":" + str(h["port"]) for h in hosts]
        assert keys == sorted(keys)
        print("5. multiple hosts coexist and list in order: OK")

        # 6. Forget removes exactly one; reports whether it did.
        assert clientconf.forget_host("office-pc", 8765) is True
        assert clientconf.get_pin("office-pc", 8765) is None
        assert clientconf.forget_host("office-pc", 8765) is False
        assert len(clientconf.known_hosts()) == 1
        print("6. forget_host removes one and reports accurately: OK")

        # 7. Last-connection memory round-trips.
        clientconf.set_last_connection("books.example", 8765)
        assert clientconf.last_connection() == ("books.example", 8765)
        print("7. last-connection memory round-trips: OK")

        # 8. A corrupt trust file is treated as 'nothing remembered', never
        #    a crash -- and the next write heals it.
        with open(os.path.join(tmp, "client.json"), "w", encoding="utf-8") as f:
            f.write("{ this is not valid json ::::")
        assert clientconf.known_hosts() == []
        assert clientconf.get_pin("books.example", 8765) is None
        clientconf.remember_host("books.example", 8765, FP1)
        assert clientconf.get_pin("books.example", 8765) == FP1
        print("8. corrupt file tolerated and self-heals on next write: OK")

        # 9. The file is written atomically (no stray temp files left behind).
        leftovers = [n for n in os.listdir(tmp) if n.endswith(".tmp")]
        assert leftovers == [], leftovers
        print("9. atomic write leaves no temp files: OK")

        print("All client trust-store checks passed.")
    finally:
        restore()


if __name__ == "__main__":
    run()
