# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
"""End-to-end check for part B: a HostServer started with an advertise_name
answers LAN discovery probes, pointing clients at its real TLS port; a server
without a name does not advertise. Runs headless over loopback with a dummy
engine (no client traffic is exercised -- only the discovery wiring)."""

import os
import socket
import tempfile
import shutil
import time

from ledger import hostnet, discovery


def _free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _DummyEngine:
    """Stands in for a HostEngine: discovery never calls it; only TLS clients
    would, and this test makes no client connections."""


def run():
    tmp = tempfile.mkdtemp(prefix="ledger-hostdisc-")
    cert = os.path.join(tmp, "host_cert.pem")
    key = os.path.join(tmp, "host_key.pem")
    try:
        # 1. A host started with a name is discoverable, and the reply carries
        #    the host's ACTUAL secure-server port (here an ephemeral one).
        dport = _free_udp_port()
        server = hostnet.HostServer(
            _DummyEngine(), cert, key, host="127.0.0.1", port=0,
            advertise_name="Maple Street Bakery", discovery_port=dport)
        assert not server.advertising      # not until start()
        server.start()
        try:
            time.sleep(0.15)
            assert server.advertising
            hosts = discovery.discover_hosts(
                timeout=1.0, discovery_port=dport, targets=["127.0.0.1"])
            assert len(hosts) == 1, hosts
            assert hosts[0]["name"] == "Maple Street Bakery"
            assert hosts[0]["port"] == server.port, (
                hosts[0]["port"], server.port)
            print("1. a started host is discoverable, pointing at its TLS "
                  "port: OK")
        finally:
            server.stop()

        # 2. Once stopped, it is no longer discoverable.
        assert not server.advertising
        time.sleep(0.1)
        gone = discovery.discover_hosts(
            timeout=0.6, discovery_port=dport, targets=["127.0.0.1"])
        assert gone == [], gone
        print("2. after stop() the host stops advertising: OK")

        # 3. advertise_name=None means no responder at all.
        dport2 = _free_udp_port()
        s2 = hostnet.HostServer(
            _DummyEngine(), cert, key, host="127.0.0.1", port=0,
            advertise_name=None, discovery_port=dport2)
        s2.start()
        try:
            time.sleep(0.15)
            assert not s2.advertising
            none = discovery.discover_hosts(
                timeout=0.6, discovery_port=dport2, targets=["127.0.0.1"])
            assert none == [], none
            print("3. advertise_name=None means no discovery responder: OK")
        finally:
            s2.stop()

        print("All host-discovery checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()
