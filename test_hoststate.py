"""Tests for ledger.hoststate -- the detached-host tracking file."""

import os
import subprocess
import sys
import tempfile
import time

from ledger import hoststate


def test_write_read_clear():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "host_state.json")
    assert hoststate.read_state(p) is None
    hoststate.write_state(1234, 8765, "AB:CD", "/books/main.db", path=p)
    data = hoststate.read_state(p)
    assert data["pid"] == 1234
    assert data["port"] == 8765
    assert data["fingerprint"] == "AB:CD"
    assert data["book"] == "/books/main.db"
    assert "started_at" in data
    hoststate.clear_state(p)
    assert hoststate.read_state(p) is None
    # clearing again is safe
    hoststate.clear_state(p)
    print("write/read/clear OK")


def test_atomic_overwrite():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "host_state.json")
    hoststate.write_state(1, 1000, "X", "/a.db", path=p)
    hoststate.write_state(2, 2000, "Y", "/b.db", path=p)
    data = hoststate.read_state(p)
    assert data["pid"] == 2 and data["port"] == 2000 and data["book"] == "/b.db"
    # no leftover temp files beside it
    leftovers = [f for f in os.listdir(d) if f.startswith(".host_state.")]
    assert not leftovers, leftovers
    print("atomic overwrite OK")


def test_corrupt_file():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "host_state.json")
    with open(p, "w") as f:
        f.write("{not valid json")
    assert hoststate.read_state(p) is None
    with open(p, "w") as f:
        f.write('{"unrelated": 1}')   # missing pid/port
    assert hoststate.read_state(p) is None
    print("corrupt/partial file OK")


def test_pid_alive():
    assert hoststate.pid_alive(os.getpid()) is True
    # PID 0 / negatives are never 'alive' for our purposes
    assert hoststate.pid_alive(0) is False
    assert hoststate.pid_alive(-1) is False
    assert hoststate.pid_alive(None) is False
    # A very high pid that is almost certainly not running
    assert hoststate.pid_alive(2 ** 31 - 1) is False
    print("pid_alive OK")


def test_running_host_clears_stale():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "host_state.json")
    # Alive: our own pid
    hoststate.write_state(os.getpid(), 8765, "FP", "/x.db", path=p)
    got = hoststate.running_host(p)
    assert got is not None and got["pid"] == os.getpid()
    # Stale: a dead pid -> running_host returns None and removes the file
    hoststate.write_state(2 ** 31 - 1, 8765, "FP", "/x.db", path=p)
    assert hoststate.running_host(p) is None
    assert hoststate.read_state(p) is None  # file was cleared
    print("running_host stale-clearing OK")


def test_terminate_real_process():
    # Spawn a short-lived child, confirm it's alive, terminate it, confirm gone.
    proc = subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(30)"])
    try:
        time.sleep(0.3)
        assert hoststate.pid_alive(proc.pid) is True
        ok = hoststate.terminate(proc.pid, timeout=5.0)
        assert ok is True
        assert hoststate.pid_alive(proc.pid) is False
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
    print("terminate real process OK")


def test_terminate_dead_pid_is_safe():
    assert hoststate.terminate(2 ** 31 - 1, timeout=1.0) is True
    print("terminate dead pid OK")


def test_port_open():
    import socket
    # A listening socket -> port_open True; once closed -> False.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert hoststate.port_open(port) is True
    finally:
        srv.close()
    assert hoststate.port_open(port, timeout=0.3) is False
    assert hoststate.port_open(0) is False
    assert hoststate.port_open(None) is False
    print("port_open OK")


if __name__ == "__main__":
    test_write_read_clear()
    test_atomic_overwrite()
    test_corrupt_file()
    test_pid_alive()
    test_running_host_clears_stale()
    test_terminate_real_process()
    test_terminate_dead_pid_is_safe()
    test_port_open()
    print("All hoststate tests passed.")
