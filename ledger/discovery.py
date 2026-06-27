# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Find Ledger hosts on the local network, so a client does not have to be told
an IP address by hand.

This is a small, dependency-free discovery built on a single UDP port, the
way many devices announce themselves on a home or office network:

  * A host that is sharing its books runs a tiny responder
    (DiscoveryResponder) that listens on the discovery port and answers a
    probe with its name and the TCP port its secure server is on.
  * A client calls discover_hosts(), which broadcasts a probe and gathers the
    replies for a short moment, returning the hosts it heard from.

Discovery only helps a person FIND a host to pick from a list -- it grants no
trust. The real security still happens at connect time: the client opens a TLS
connection to the chosen address and pins that host's certificate
(trust-on-first-use), exactly as if the address had been typed by hand. A
spoofed discovery reply can at most put a wrong entry in the list; it cannot
make the client trust a host it would not otherwise trust.

Discovery uses UDP broadcast, which reaches the local network segment only. It
does not cross routers or subnets, and some networks block broadcast traffic;
in those cases a person can still type the address directly.
"""

import json
import socket
import threading
import time

# The UDP port discovery talks on. The secure TCP server (hostnet) is a
# separate port; a reply carries whichever port that server is actually on.
DISCOVERY_PORT = 8024

_MAGIC = "ledger-discovery"
_PROTOCOL = 1
_ENC = "utf-8"
_MAX_DATAGRAM = 2048


def _encode(obj):
    return json.dumps(obj, separators=(",", ":")).encode(_ENC)


def _decode(data):
    try:
        obj = json.loads(data.decode(_ENC))
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _is_probe(msg):
    return bool(msg) and msg.get("m") == _MAGIC and msg.get("q") == "hosts"


def _is_reply(msg):
    return bool(msg) and msg.get("m") == _MAGIC and msg.get("r") == "host"


class DiscoveryResponder:
    """Runs on a host. Listens on the discovery port and answers valid probes
    with this host's name and secure-server port. Start it when hosting and
    stop it when hosting ends. Malformed or unrelated datagrams are ignored.
    """

    def __init__(self, name, server_port, discovery_port=DISCOVERY_PORT):
        self.name = name or "Ledger host"
        self.server_port = int(server_port)
        self.discovery_port = int(discovery_port)
        self._sock = None
        self._thread = None
        self._running = False

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass   # not available on every platform; harmless when absent
        sock.bind(("", self.discovery_port))
        sock.settimeout(0.5)
        self._sock = sock
        self._running = True
        self._thread = threading.Thread(
            target=self._serve, name="ledger-discovery", daemon=True)
        self._thread.start()

    def _reply_bytes(self):
        return _encode({"m": _MAGIC, "v": _PROTOCOL, "r": "host",
                        "name": self.name, "port": self.server_port})

    def _serve(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(_MAX_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break
            if not _is_probe(_decode(data)):
                continue
            try:
                self._sock.sendto(self._reply_bytes(), addr)
            except OSError:
                pass

    def stop(self):
        self._running = False
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)


def discover_hosts(timeout=1.5, discovery_port=DISCOVERY_PORT, targets=None):
    """Broadcast a probe and gather replies for `timeout` seconds.

    Returns a list of {"address", "port", "name"} dicts, one per host that
    answered, de-duplicated by address+port and sorted by name then address.

    `targets` is the list of addresses to send the probe to; it defaults to
    the network broadcast address (the whole local segment) plus loopback, so a
    host running on this same computer (e.g. when testing with two windows) is
    found too. A caller can pass specific addresses instead -- e.g. a
    particular subnet broadcast, or a single host's address to check just that
    one.
    """
    if targets is None:
        targets = ["255.255.255.255", "127.0.0.1"]
    probe = _encode({"m": _MAGIC, "v": _PROTOCOL, "q": "hosts"})

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.3)
    found = {}
    try:
        sock.bind(("", 0))
        for target in targets:
            try:
                sock.sendto(probe, (target, discovery_port))
            except OSError:
                continue
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(_MAX_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = _decode(data)
            if not _is_reply(msg):
                continue
            try:
                port = int(msg.get("port"))
            except (TypeError, ValueError):
                continue
            address = addr[0]
            key = (address, port)
            if key not in found:
                found[key] = {
                    "address": address,
                    "port": port,
                    "name": str(msg.get("name") or "Ledger host"),
                }
    finally:
        sock.close()

    return sorted(found.values(),
                  key=lambda h: (h["name"].lower(), h["address"]))
