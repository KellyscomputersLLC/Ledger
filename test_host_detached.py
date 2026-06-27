"""Integration test for the detached host process.

Exercises host_main.spawn_detached() -- the exact mechanism the app uses to
start hosting -- then connects a real client over the loopback, checks it
serves, and stops it both ways the app can: via the Popen handle (same session)
and via pid from the state file (a later run). This is the core of 'hosting
survives the app being closed': the spawned process is in its own session with
no parent app holding it open.
"""

import os
import socket
import tempfile
import time

from ledger import (crypto, database, seed, service, roles, hostnet,
                    hoststate, host_main)


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _make_book(path):
    vault, _ = crypto.create_vault("OwnerPass-123")
    crypto.save_vault(path, vault)
    key = crypto.unlock(vault, "OwnerPass-123")
    conn = database.connect(path, data_key=key)
    database.init_db(conn)
    seed.seed_accounts(conn)
    conn.commit()
    s = service.Session(conn, "o", roles.OWNER, vault=crypto.load_vault(path),
                        data_key=key, db_path=path)
    service.enable_multiuser(s, "OwnerPass-123", "ben")
    conn.commit()
    conn.close()              # release the file so the host opens it fresh
    return key


def _serves_ok(port):
    client = hostnet.HostClient("127.0.0.1", port)
    client.connect()
    try:
        resp = client.login("ben", "OwnerPass-123")
        assert resp.get("ok"), resp
        who = client.request("whoami")
        assert who.get("ok") and who["result"]["username"] == "ben", who
        status = client.request("host_status")
        assert status.get("ok") and status["result"]["session_count"] >= 1
    finally:
        try:
            client.logout()
        except Exception:
            pass
        client.close()


def test_spawn_connect_stop_via_proc():
    d = tempfile.mkdtemp()
    book = os.path.join(d, "Business.db")
    state_path = os.path.join(d, "host_state.json")
    key = _make_book(book)
    port = _free_port()

    proc, st = host_main.spawn_detached(book, key, port=port, advertise=False,
                                        state_file=state_path)
    try:
        assert st["port"] == port and st["pid"] == proc.pid
        assert hoststate.pid_alive(proc.pid) is True
        assert hoststate.running_host(state_path) is not None
        _serves_ok(port)
        print("spawn + connect OK (pid=%d port=%d)" % (proc.pid, port))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
    assert hoststate.pid_alive(proc.pid) is False
    deadline = time.time() + 3.0
    while time.time() < deadline and hoststate.read_state(state_path):
        time.sleep(0.05)
    assert hoststate.running_host(state_path) is None
    print("stopped via Popen handle, state cleared OK")


def test_spawn_then_stop_via_pid():
    d = tempfile.mkdtemp()
    book = os.path.join(d, "Business.db")
    state_path = os.path.join(d, "host_state.json")
    key = _make_book(book)
    port = _free_port()

    proc, st = host_main.spawn_detached(book, key, port=port, advertise=False,
                                        state_file=state_path)
    try:
        _serves_ok(port)
        pid = st["pid"]
        ok = hoststate.terminate(pid, timeout=8.0)
        assert ok is True
        assert hoststate.pid_alive(pid) is False
        deadline = time.time() + 3.0
        while time.time() < deadline and hoststate.read_state(state_path):
            time.sleep(0.05)
        assert hoststate.running_host(state_path) is None
        print("stopped by pid (cross-restart path) OK")
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    test_spawn_connect_stop_via_proc()
    test_spawn_then_stop_via_pid()
    print("All detached-host integration checks passed.")
