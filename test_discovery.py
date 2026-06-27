# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""Checks for discovery: the dependency-free UDP host finder. Runs headless
over loopback -- a responder is started on a free port and probed directly at
127.0.0.1, so the test does not depend on broadcast being permitted in the
sandbox (the real client uses broadcast on a LAN; the protocol exercised here
is identical)."""

import socket
import time

from ledger import discovery


def _free_udp_port():
    """Grab a UDP port the OS says is free, then release it for the test to
    reuse. A tiny race, but fine for a local self-test."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _send_probe_raw(port, payload):
    """Send a raw datagram to the responder and wait briefly for a reply.
    Returns the decoded reply dict, or None if nothing came back."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    try:
        s.sendto(payload, ("127.0.0.1", port))
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            return None
        return discovery._decode(data)
    finally:
        s.close()


def run():
    port = _free_udp_port()
    resp = discovery.DiscoveryResponder("Maple Street Bakery", 8023,
                                        discovery_port=port)
    resp.start()
    try:
        time.sleep(0.1)   # let the responder thread settle on the socket

        # 1. A valid probe gets a well-formed reply with name + server port.
        reply = _send_probe_raw(port, discovery._encode(
            {"m": discovery._MAGIC, "v": 1, "q": "hosts"}))
        assert reply is not None, "no reply to a valid probe"
        assert reply.get("r") == "host"
        assert reply.get("name") == "Maple Street Bakery"
        assert reply.get("port") == 8023
        print("1. responder answers a valid probe with name + port: OK")

        # 2. Junk and unrelated datagrams are ignored (no reply).
        for junk in (b"not json at all",
                     discovery._encode({"m": "something-else", "q": "hosts"}),
                     discovery._encode({"m": discovery._MAGIC}),  # no q
                     discovery._encode({"m": discovery._MAGIC, "q": "other"})):
            assert _send_probe_raw(port, junk) is None, junk
        print("2. malformed / unrelated datagrams are ignored: OK")

        # 3. The client-side discover_hosts() finds the responder when aimed
        #    at loopback, returning a clean address/port/name record.
        hosts = discovery.discover_hosts(timeout=1.0, discovery_port=port,
                                         targets=["127.0.0.1"])
        assert len(hosts) == 1, hosts
        h = hosts[0]
        assert h["address"] in ("127.0.0.1",)
        assert h["port"] == 8023
        assert h["name"] == "Maple Street Bakery"
        print("3. discover_hosts() finds and parses the host: OK")

        # 4. De-duplication: one responder yields exactly one entry even
        #    though discovery may receive its reply via more than one path.
        hosts2 = discovery.discover_hosts(timeout=0.8, discovery_port=port,
                                          targets=["127.0.0.1", "127.0.0.1"])
        keys = {(x["address"], x["port"]) for x in hosts2}
        assert len(keys) == len(hosts2), "duplicate entries leaked"
        print("4. replies are de-duplicated by address+port: OK")
    finally:
        resp.stop()

    # 5. After stop(), nothing answers (responder socket is closed) and a
    #    probe to the now-empty port yields no hosts.
    time.sleep(0.1)
    empty = discovery.discover_hosts(timeout=0.6, discovery_port=port,
                                     targets=["127.0.0.1"])
    assert empty == [], empty
    print("5. after stop() the host is no longer discoverable: OK")

    # 6. stop() is idempotent and leaves no thread running.
    resp.stop()
    assert resp._thread is None and resp._sock is None
    print("6. stop() is clean and idempotent: OK")

    print("All discovery checks passed.")


if __name__ == "__main__":
    run()
