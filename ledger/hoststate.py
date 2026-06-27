# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""Tracking the detached host process across app restarts.

When the owner starts hosting, the host runs as a separate background process
so it keeps serving after the app window is closed. This module records where
that process is -- its pid, the port it listens on, its certificate
fingerprint and which book it serves -- in a small JSON file, so a later launch
of the app can find it again to reconnect, show that it is running, or stop it.

The file never holds the books' data key or passphrase, only these locating
details. The data key is handed to the host process over a pipe at launch and
lives solely in that process's memory.
"""

import json
import os
import sys
import tempfile
import time


def _state_dir():
    """Where the host's locating file lives -- beside its certificate."""
    d = os.path.join(os.path.expanduser("~"), ".ledger")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def state_path():
    """The file that records the running detached host, if any."""
    return os.path.join(_state_dir(), "host_state.json")


def write_state(pid, port, fingerprint, book, path=None):
    """Record a running host atomically: write a temp file then rename it into
    place, so a reader never sees a half-written file. Returns the dict
    written."""
    path = path or state_path()
    data = {
        "pid": int(pid),
        "port": int(port),
        "fingerprint": fingerprint or "",
        "book": book or "",
        "started_at": int(time.time()),
    }
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".host_state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return data


def read_state(path=None):
    """Return the recorded host details, or None if there is no valid file."""
    path = path or state_path()
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "pid" not in data or "port" not in data:
        return None
    return data


def clear_state(path=None):
    """Remove the state file. Safe if it is already gone."""
    path = path or state_path()
    try:
        os.unlink(path)
    except OSError:
        pass


def pid_alive(pid):
    """True if a process with this pid is currently running. Cross-platform,
    best-effort; never raises."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        return _win_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process exists but is owned by another user.
        return True
    except OSError:
        return False
    return True


def _win_pid_alive(pid):
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if k.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            k.CloseHandle(h)
    except Exception:
        return False


def terminate(pid, timeout=5.0):
    """Ask the host process to stop and wait briefly for it to exit. On POSIX
    this sends SIGTERM first (the host shuts down cleanly and flushes), then
    SIGKILL if it lingers; on Windows it terminates the process. Returns True
    if the process is gone afterwards."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if not pid_alive(pid):
        return True
    if sys.platform.startswith("win"):
        _win_terminate(pid)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        # If the target is our own child, reap it once it dies so it does not
        # linger as a zombie (which os.kill(pid, 0) would still report as
        # alive). For a process we did not spawn this is simply ECHILD and we
        # rely on its real parent to reap it.
        if not sys.platform.startswith("win"):
            try:
                reaped, _ = os.waitpid(pid, os.WNOHANG)
                if reaped == pid:
                    return True
            except (ChildProcessError, OSError):
                pass
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    if not sys.platform.startswith("win"):
        import signal
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except (ChildProcessError, OSError):
            pass
        time.sleep(0.2)
    return not pid_alive(pid)


def _win_terminate(pid):
    try:
        import ctypes
        PROCESS_TERMINATE = 0x0001
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            k.TerminateProcess(h, 0)
            k.CloseHandle(h)
    except Exception:
        pass


def running_host(path=None):
    """Return the recorded host details only if its process is actually alive.
    A stale file (the process has gone) is cleared and None is returned, so
    callers can treat a non-None result as 'a host really is running here'."""
    data = read_state(path)
    if data is None:
        return None
    if not pid_alive(data.get("pid")):
        clear_state(path)
        return None
    return data


def port_open(port, host="127.0.0.1", timeout=0.6):
    """True if something is listening on this TCP port right now. Used as a
    second, stronger check that a recorded host is really serving (beyond the
    pid being alive, which could be a reused pid). Never raises."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if port <= 0:
        return False
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass
