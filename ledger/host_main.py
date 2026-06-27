# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Run Ledger as a HOST: open a shared set of books on this computer and serve
them to other computers on the network, so each person signs in with their own
username and password and what they can do is enforced by their role.

This is the main computer in the host model. It opens the books once (you, the
owner, unlock them when you start it) and holds the data key in memory while it
runs. Client computers never receive the data or the key -- they ask this host
to do things, and the host does only what each person's role allows.

Usage:
    python3 -m ledger.host_main /path/to/Business.db
    python3 -m ledger.host_main /path/to/Business.db --port 8023

You'll be asked for the passphrase that opens the books. The program then prints
the address and a short security fingerprint to give to the people who will
connect, and serves until you press Ctrl+C.

For testing without a prompt (e.g. on a lab machine), the passphrase may be
supplied in the LEDGER_HOST_PASSPHRASE environment variable. Avoid this on a
real machine -- typing it at the prompt keeps it off disk and out of your shell
history.
"""

import argparse
import getpass
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from . import crypto
from . import database
from . import users
from . import host
from . import hostnet
from . import hoststate
from . import profile


def _config_dir():
    """Where the host keeps its certificate (its stable network identity)."""
    d = os.path.join(os.path.expanduser("~"), ".ledger")
    os.makedirs(d, exist_ok=True)
    return d


def _lan_addresses():
    """Best-effort list of this computer's LAN addresses, to show the people
    who need to connect. Never raises."""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets are actually sent; this just selects the outbound
            # interface so we can read its address.
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips)


def open_book_for_host(db_path, passphrase, allow_threads=True):
    """Open a protected, multi-user book and return its (conn, vault, key).
    Raises ValueError with a friendly message if the book can't be hosted."""
    if not os.path.exists(db_path):
        raise ValueError("No book found at: %s" % db_path)
    if not crypto.is_protected(db_path):
        raise ValueError(
            "These books are not protected (encrypted), so they can't be "
            "hosted. Open them in Ledger, turn on protection and shared "
            "access first.")
    vault = crypto.load_vault(db_path)
    try:
        data_key = crypto.unlock(vault, passphrase)
    except Exception:
        raise ValueError("That passphrase did not open the books.")
    conn = database.connect(db_path, data_key=data_key,
                            allow_threads=allow_threads)
    if not users.multiuser_enabled(conn):
        conn.close()
        raise ValueError(
            "These books are not set up for shared access yet. Open them in "
            "Ledger and use Security -> Shared access to set them up first.")
    return conn, vault, data_key


def build_server(conn, vault, data_key, db_path, port=hostnet.DEFAULT_PORT,
                 bind="0.0.0.0", advertise=True):
    """Build (but do not start) a HostServer wrapping these open books. When
    `advertise` is true the server also answers LAN discovery probes, listed
    under the book's business name so clients can find it by name."""
    cert_path = os.path.join(_config_dir(), "host_cert.pem")
    key_path = os.path.join(_config_dir(), "host_key.pem")
    engine = host.HostEngine(conn, vault, data_key, db_path)
    advertise_name = None
    if advertise:
        try:
            advertise_name = (profile.get_profile(conn).get("name") or "").strip()
        except Exception:
            advertise_name = ""
        if not advertise_name:
            advertise_name = "Ledger host"
    server = hostnet.HostServer(engine, cert_path, key_path,
                                host=bind, port=port,
                                advertise_name=advertise_name)
    return server, engine


def start_local_host(db_path, data_key, port=hostnet.DEFAULT_PORT,
                     bind="0.0.0.0", advertise=True):
    """Start hosting a book that is already open and unlocked in the app.

    The app holds the book open on an ordinary single-thread connection, but
    the host server answers on background threads and so needs a thread-safe
    connection. This opens a fresh one from the encrypted file -- which is why
    the caller must COMMIT its current connection first, so the file on disk is
    current. Returns (server, conn); the caller stops the server and closes
    this conn (via stop_local_host) when hosting ends.
    """
    if not crypto.is_protected(db_path):
        raise ValueError(
            "These books are not protected (encrypted), so they can't be "
            "hosted.")
    conn = database.connect(db_path, data_key=data_key, allow_threads=True)
    if not users.multiuser_enabled(conn):
        conn.close()
        raise ValueError(
            "These books are not set up for shared access yet. Use Security "
            "-> Shared access to set them up first.")
    vault = crypto.load_vault(db_path)
    server, _engine = build_server(conn, vault, data_key, db_path,
                                   port=port, bind=bind, advertise=advertise)
    try:
        server.start()
    except OSError:
        try:
            server.stop()
        except Exception:
            pass
        conn.close()
        raise
    return server, conn


def stop_local_host(server, conn):
    """Stop in-app hosting started by start_local_host: stop the server (and
    its discovery responder) and close the hosting connection. Always safe."""
    try:
        if server is not None:
            server.stop()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _print_banner(db_path, server):
    line = "=" * 60
    print(line)
    print("  Ledger host is running")
    print(line)
    print("  Books:        %s" % os.path.basename(db_path))
    print("  Listening on: port %d" % server.port)
    addrs = _lan_addresses()
    if addrs:
        print("  This computer's address(es) for others to connect to:")
        for a in addrs:
            print("       %s   (port %d)" % (a, server.port))
    else:
        print("  (Could not determine this computer's network address; find "
              "it in your system settings.)")
    print()
    print("  Security fingerprint (read this to people connecting the first")
    print("  time, so they can confirm they've reached the right computer):")
    print("       %s" % hostnet.pretty_fingerprint(server.fingerprint()))
    if server.advertising:
        print(line)
        print("  Discoverable: other computers on this network can find this")
        print("  host by name with \u201cFind hosts on the network\u201d \u2014 no")
        print("  address needed. (They still confirm the fingerprint above on")
        print("  first connect.)")
    print(line)
    print("  Press Ctrl+C to stop serving.")
    print(line)
    sys.stdout.flush()


def spawn_detached(book, data_key, port=hostnet.DEFAULT_PORT, advertise=True,
                   state_file=None, python_exe=None, timeout=15.0):
    """Launch the host as a detached background process that outlives this one.

    The data key is handed to the child over its stdin (hex-encoded), never on
    the command line or disk, so it is not visible in the process list. The
    child is placed in its own session/process group so closing this program
    does not take it down. This waits until the child is actually serving (its
    state file appears) and returns (proc, state). Raises RuntimeError if it
    does not come up. The caller keeps `proc` to stop it within this session;
    a later run stops it by pid via hoststate.terminate().
    """
    state_file = state_file or hoststate.state_path()
    # Clear any stale file so we wait for THIS host's readiness, not an old one.
    hoststate.clear_state(state_file)
    exe = python_exe or sys.executable
    cmd = [exe, "-m", "ledger.host_main", "--detached",
           "--state", state_file, "--port", str(port)]
    if not advertise:
        cmd.append("--no-advertise")
    cmd.append(book)

    # Make sure the child can import the ledger package regardless of its
    # working directory, by putting this package's parent on PYTHONPATH.
    env = dict(os.environ)
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pkg_parent + os.pathsep + existing
                         if existing else pkg_parent)

    kwargs = dict(stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, env=env)
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    try:
        proc.stdin.write((data_key.hex() + "\n").encode("ascii"))
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("Could not hand the key to the host process.")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("The host process stopped before it was ready.")
        st = hoststate.read_state(state_file)
        if st and st.get("book") == book and st.get("port"):
            return proc, st
        time.sleep(0.15)
    try:
        proc.kill()
    except Exception:
        pass
    raise RuntimeError("The host did not start in time.")


def serve_detached(book, port=hostnet.DEFAULT_PORT, bind="0.0.0.0",
                   advertise=True, state_file=None, key_stream=None):
    """Run the host as a standalone background process that outlives the app.

    The books' data key is read (hex-encoded) from `key_stream` -- standard
    input by default -- rather than from a passphrase prompt or the command
    line, so it is never visible in the process list. Once the server is bound
    and serving, a small state file records this process's pid, port and
    certificate fingerprint so the app can find, reconnect to, or stop it
    later. The process then serves until it receives SIGTERM (or Ctrl+C),
    whereupon it stops cleanly and clears the state file.

    This path is used by the app itself; a person running the host by hand uses
    the ordinary passphrase prompt instead (see main()).
    """
    stream = key_stream if key_stream is not None else sys.stdin
    raw = (stream.readline() or "").strip()
    if not raw:
        print("No data key supplied on stdin.", file=sys.stderr)
        return 2
    try:
        data_key = bytes.fromhex(raw)
    except ValueError:
        print("Malformed data key on stdin.", file=sys.stderr)
        return 2

    try:
        server, conn = start_local_host(book, data_key, port=port, bind=bind,
                                        advertise=advertise)
    except (ValueError, OSError) as e:
        print("Could not start host: %s" % e, file=sys.stderr)
        return 2

    stop = threading.Event()

    def _stop(_signum=None, _frame=None):
        stop.set()

    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(_sig, _stop)
        except (ValueError, OSError):
            pass

    sf = state_file or hoststate.state_path()
    try:
        hoststate.write_state(os.getpid(), server.port, server.fingerprint(),
                              book, path=sf)
    except Exception as e:
        # If we cannot record where we are, the app cannot find us to manage or
        # stop us -- so we must not keep running as an unmanageable orphan.
        print("Could not write host state file: %s" % e, file=sys.stderr)
        stop_local_host(server, conn)
        return 2

    # Tell a waiting launcher we are serving (in addition to the state file,
    # which is the authoritative readiness signal). Harmless if stdout is
    # discarded.
    try:
        print("READY %d" % server.port, flush=True)
    except Exception:
        pass

    try:
        stop.wait()
    finally:
        stop_local_host(server, conn)
        hoststate.clear_state(sf)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m ledger.host_main",
        description="Serve a shared set of Ledger books to other computers.")
    parser.add_argument("book", help="path to the .db book to host")
    parser.add_argument("--port", type=int, default=hostnet.DEFAULT_PORT,
                        help="port to listen on (default %d)"
                             % hostnet.DEFAULT_PORT)
    parser.add_argument("--bind", default="0.0.0.0",
                        help="address to bind (default all interfaces)")
    parser.add_argument("--no-advertise", action="store_true",
                        help="do not announce this host on the local network "
                             "(clients must be given the address)")
    # Internal: used by the app to run the host as a background process. The
    # data key is read (hex) from stdin and a state file is written so the app
    # can manage this process. Not for interactive use (use the passphrase
    # prompt instead), so it is hidden from --help.
    parser.add_argument("--detached", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--state", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.detached:
        return serve_detached(args.book, port=args.port, bind=args.bind,
                              advertise=not args.no_advertise,
                              state_file=args.state)

    passphrase = os.environ.get("LEDGER_HOST_PASSPHRASE")
    if not passphrase:
        passphrase = getpass.getpass("Passphrase to open the books: ")

    try:
        conn, vault, data_key = open_book_for_host(args.book, passphrase)
    except ValueError as e:
        print("Could not start: %s" % e, file=sys.stderr)
        return 2

    server, _engine = build_server(conn, vault, data_key, args.book,
                                   port=args.port, bind=args.bind,
                                   advertise=not args.no_advertise)
    server.start()
    _print_banner(args.book, server)
    try:
        # Sleep forever; serving happens on the server's own thread.
        stop = threading.Event()
        stop.wait()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.stop()
        try:
            conn.close()
        except Exception:
            pass
    print("Host stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
