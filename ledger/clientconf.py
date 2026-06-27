# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Where a Ledger CLIENT remembers the hosts it connects to.

When this computer connects to another one that is hosting the books, two
small things are worth keeping between runs:

  * the host's security fingerprint -- so we recognise the SAME host next
    time (trust-on-first-use) and can warn loudly if it ever changes, the
    way an SSH client pins a server's key; and
  * the last address and port typed -- purely so the connect screen can
    pre-fill them as a convenience.

A fingerprint is not secret -- it is public information -- but it IS
integrity-sensitive: if the stored value were quietly altered, an impostor
host could slip in unnoticed. So this lives in the user's private Ledger
data folder, beside the books, and is written atomically (whole-file replace)
so a crash mid-write can never leave a half-written trust file.

The file is plain JSON and survives being missing or corrupt by simply
behaving as though nothing has been remembered yet.
"""

import datetime
import json
import os
import tempfile

from . import paths

_FILENAME = "client.json"
_VERSION = 1


# --- file location & io -----------------------------------------------------

def _path():
    return os.path.join(paths.data_dir(), _FILENAME)


def _now():
    return (datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat())


def _key(host, port):
    """The identity a host is remembered under. Host is lower-cased so the
    same machine typed as 'Office-PC' or 'office-pc' is one entry; the port
    is part of the key because a different port can be a different host."""
    return "%s:%d" % ((host or "").strip().lower(), int(port))


def _blank():
    return {"version": _VERSION, "hosts": {}, "last": {}}


def _load():
    """Read the trust file, tolerating absence or corruption by returning an
    empty structure rather than raising."""
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _blank()
    if not isinstance(data, dict):
        return _blank()
    data.setdefault("version", _VERSION)
    if not isinstance(data.get("hosts"), dict):
        data["hosts"] = {}
    if not isinstance(data.get("last"), dict):
        data["last"] = {}
    return data


def _save(data):
    """Write the trust file atomically: a temp file in the same folder, then
    an atomic replace, so readers never see a partial file."""
    target = _path()
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".client-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --- pinned fingerprints (trust-on-first-use) -------------------------------

def get_pin(host, port):
    """The fingerprint previously pinned for this host, or None if this is a
    first-time connection (the caller should then show the fingerprint and
    ask the person to confirm before remembering it)."""
    rec = _load()["hosts"].get(_key(host, port))
    return rec.get("fingerprint") if rec else None

def get_host(host, port):
    """The full remembered record for a host, or None."""
    return _load()["hosts"].get(_key(host, port))


def remember_host(host, port, fingerprint, label=None):
    """Pin (or re-pin) a host's fingerprint. The first-seen time is preserved
    across re-pins; a re-pin (the certificate legitimately changed) just
    updates the fingerprint and the 'updated' time."""
    data = _load()
    k = _key(host, port)
    existing = data["hosts"].get(k, {})
    data["hosts"][k] = {
        "host": (host or "").strip(),
        "port": int(port),
        "fingerprint": fingerprint,
        "label": (label if label is not None else existing.get("label", "")),
        "added": existing.get("added") or _now(),
        "updated": _now(),
    }
    _save(data)


def forget_host(host, port):
    """Drop a pinned host. Returns True if there was one to remove."""
    data = _load()
    k = _key(host, port)
    if k in data["hosts"]:
        del data["hosts"][k]
        _save(data)
        return True
    return False


def known_hosts():
    """Every pinned host as a list of records, ordered by identity."""
    hosts = _load()["hosts"]
    return [hosts[k] for k in sorted(hosts)]


# --- last connection (convenience pre-fill) ---------------------------------

def last_connection():
    """The host/port last connected to, as (host, port), or (None, None) if
    nothing has been remembered yet."""
    last = _load()["last"]
    host = last.get("host")
    port = last.get("port")
    if host and port:
        return (host, int(port))
    return (None, None)


def set_last_connection(host, port):
    """Remember the address last used, so the connect screen can offer it."""
    data = _load()
    data["last"] = {"host": (host or "").strip(), "port": int(port)}
    _save(data)
