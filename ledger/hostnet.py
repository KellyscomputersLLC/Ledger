# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Network transport for the host model (Phase 2, Slice 2).

This wraps the transport-free HostEngine (host.py) in a real TLS socket server,
and provides a thin client to talk to it. The engine still does all the
thinking -- authentication, role enforcement, audit -- this module only carries
its request/response dicts safely across the LAN.

How it is secured
-----------------
* The channel is TLS (stdlib `ssl`). The host holds a self-signed certificate
  and key, generated once on first run with the `cryptography` library (the
  same library used for at-rest encryption -- no home-grown channel crypto).
* The host is authenticated by certificate pinning, trust-on-first-use: on the
  first connection the client records the host certificate's SHA-256
  fingerprint, and on every later connection it checks the host still presents
  the same certificate. This is the SSH `known_hosts` model. It closes the
  door on a man-in-the-middle after first contact; the one residual risk is an
  interceptor present at the very first connection, which a later polish step
  addresses by showing the fingerprint for out-of-band confirmation.
* TLS secures and authenticates the CHANNEL. The user is still authenticated at
  the application layer (login -> token) by the engine. The session token is a
  bearer secret, which is exactly why it must only ever travel inside this
  encrypted channel.

Wire format
-----------
Each message is a 4-byte big-endian length followed by that many bytes of UTF-8
JSON -- the same request/response dicts the engine already uses. A connection
stays open for many request/response pairs until the client disconnects.
"""

import datetime
import hashlib
import hmac
import json
import os
import socket
import socketserver
import ssl
import struct
import threading

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import discovery


DEFAULT_PORT = 8023
MAX_MESSAGE_BYTES = 8 * 1024 * 1024      # a generous cap, to refuse abuse
_HANDSHAKE_TIMEOUT = 10                   # seconds allowed for the TLS handshake


# ---- length-prefixed JSON framing ------------------------------------------

def _send_msg(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Message too large to send.")
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_exactly(sock, n):
    """Read exactly n bytes, or return None if the peer closed first."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _recv_msg(sock):
    """Read one framed message, or None if the connection closed cleanly."""
    header = _recv_exactly(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    if length > MAX_MESSAGE_BYTES:
        raise ValueError("Message too large to receive.")
    body = _recv_exactly(sock, length)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


# ---- self-signed certificate -----------------------------------------------

def ensure_host_cert(cert_path, key_path, common_name="Ledger Host"):
    """Create a self-signed certificate and private key if they don't already
    exist. Returns (cert_path, key_path). The private key is written with
    owner-only permissions where the platform supports it."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    directory = os.path.dirname(cert_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("ledger-host")]),
                critical=False)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True)
            .sign(key, hashes.SHA256()))

    # Private key first, with restrictive permissions, then the certificate.
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    with open(key_path, "wb") as f:
        f.write(key_pem)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def cert_fingerprint_from_der(der_bytes):
    """SHA-256 fingerprint (lowercase hex) of a DER-encoded certificate."""
    return hashlib.sha256(der_bytes).hexdigest()


def cert_fingerprint_of_file(cert_path):
    """SHA-256 fingerprint of a PEM certificate file."""
    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    return cert_fingerprint_from_der(
        cert.public_bytes(serialization.Encoding.DER))


def pretty_fingerprint(hex_fp):
    """Group a hex fingerprint into colon-separated pairs, for a human to read
    aloud when confirming a host's identity (e.g. AB:CD:EF:...)."""
    hex_fp = (hex_fp or "").upper()
    return ":".join(hex_fp[i:i + 2] for i in range(0, len(hex_fp), 2))


# ---- server ----------------------------------------------------------------

class _RequestHandler(socketserver.BaseRequestHandler):
    """Serves one client connection: read a request, hand it to the engine,
    send the response, repeat until the client goes away."""

    def handle(self):
        engine = self.server.engine
        sock = self.request
        try:
            while True:
                try:
                    req = _recv_msg(sock)
                except (ValueError, json.JSONDecodeError):
                    _send_msg(sock, {"ok": False,
                                     "error": "Malformed request.",
                                     "code": "bad_request"})
                    continue
                if req is None:
                    break
                resp = engine.handle(req)
                _send_msg(sock, resp)
        except (ConnectionError, ssl.SSLError, OSError):
            # The client disconnected or the channel broke; just end quietly.
            pass


class _TLSThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler, ssl_context):
        self.ssl_context = ssl_context
        self.engine = None
        super().__init__(server_address, handler)

    def get_request(self):
        """Accept a connection and complete the TLS handshake before handing
        it to a worker thread. A failed handshake raises OSError, which
        serve_forever catches and ignores -- a bad client cannot stop the
        server."""
        sock, addr = self.socket.accept()
        try:
            sock.settimeout(_HANDSHAKE_TIMEOUT)
            ssock = self.ssl_context.wrap_socket(sock, server_side=True)
            ssock.settimeout(None)
            return ssock, addr
        except OSError:
            try:
                sock.close()
            finally:
                raise


class HostServer:
    """A TLS socket server that serves a HostEngine to clients on the LAN.

    Typical use on the main computer: open the books, build a HostEngine, then
    HostServer(engine, cert_path, key_path).start(). The cert/key live in the
    host's own config folder and are created automatically the first time.
    """

    def __init__(self, engine, cert_path, key_path,
                 host="0.0.0.0", port=DEFAULT_PORT,
                 advertise_name=None, discovery_port=discovery.DISCOVERY_PORT):
        ensure_host_cert(cert_path, key_path)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_path, key_path)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.cert_path = cert_path
        self._srv = _TLSThreadingServer((host, port), _RequestHandler, ctx)
        self._srv.engine = engine
        self._thread = None
        # When advertise_name is set, the server also answers LAN discovery
        # probes so clients can find it without being told its address. The
        # name is what people will see in the "find hosts" list -- usually the
        # business name. Discovery is a convenience only; the secure TCP server
        # works the same whether or not it is on.
        self.advertise_name = advertise_name
        self.discovery_port = discovery_port
        self._responder = None

    @property
    def port(self):
        """The actual port the server is listening on (useful when port=0)."""
        return self._srv.server_address[1]

    @property
    def engine(self):
        """The HostEngine answering requests -- so an in-process LoopbackClient
        can let this computer use the books it is hosting."""
        return self._srv.engine

    def fingerprint(self):
        """The SHA-256 fingerprint clients will pin for this host."""
        return cert_fingerprint_of_file(self.cert_path)

    @property
    def advertising(self):
        """True if this server is answering LAN discovery probes."""
        return self._responder is not None

    @property
    def session_count(self):
        """How many clients are currently signed in (for host-side display)."""
        try:
            return self._srv.engine.session_count()
        except Exception:
            return 0

    def start(self):
        """Begin serving in a background thread."""
        self._thread = threading.Thread(
            target=self._srv.serve_forever, name="ledger-host", daemon=True)
        self._thread.start()
        if self.advertise_name:
            try:
                responder = discovery.DiscoveryResponder(
                    self.advertise_name, self.port, self.discovery_port)
                responder.start()
                self._responder = responder
            except OSError:
                # The discovery port may be busy or blocked. That only costs
                # the convenience of being found automatically; clients can
                # still connect by address, so serving continues regardless.
                self._responder = None

    def stop(self):
        """Stop serving and release the port."""
        if self._responder is not None:
            try:
                self._responder.stop()
            except Exception:
                pass
            self._responder = None
        self._srv.shutdown()
        self._srv.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


# ---- client ----------------------------------------------------------------

class HostConnectionError(Exception):
    """Could not reach or talk to the host."""


class HostCertMismatch(Exception):
    """The host presented a different certificate than the one pinned. Either
    the host was reinstalled/changed -- or something is impersonating it."""


class HostClient:
    """A thin client to a HostServer.

    Open a TLS connection (pinning the host certificate, trust-on-first-use),
    then call request()/login(). Responses are the same dicts the engine
    returns: {"ok": True, "result": ...} or {"ok": False, "error", "code"}.
    """

    def __init__(self, host, port=DEFAULT_PORT, pinned_fingerprint=None,
                 timeout=10):
        self.host = host
        self.port = port
        self.pinned_fingerprint = pinned_fingerprint
        self.timeout = timeout
        self.sock = None
        self.server_fingerprint = None
        self.token = None

    def connect(self):
        """Open the TLS connection and check the host's certificate. Returns
        the host's fingerprint (so a first-time caller can store it). Raises
        HostCertMismatch if a pin was given and does not match, or
        HostConnectionError if the host can't be reached."""
        try:
            raw = socket.create_connection((self.host, self.port),
                                           timeout=self.timeout)
        except OSError as e:
            raise HostConnectionError(
                "Could not reach the main computer.") from e
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False         # must be cleared before CERT_NONE
        ctx.verify_mode = ssl.CERT_NONE    # we pin the exact cert ourselves
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            self.sock = ctx.wrap_socket(raw, server_hostname="ledger-host")
        except OSError as e:
            raw.close()
            raise HostConnectionError(
                "Could not establish a secure connection to the main "
                "computer.") from e

        der = self.sock.getpeercert(binary_form=True)
        fp = cert_fingerprint_from_der(der) if der else None
        self.server_fingerprint = fp
        if self.pinned_fingerprint is not None:
            if fp is None or not hmac.compare_digest(
                    fp, self.pinned_fingerprint):
                self.close()
                raise HostCertMismatch(
                    "The main computer's security certificate has changed. "
                    "If you did not expect this, do not continue.")
        self.sock.settimeout(None)
        return fp

    def _exchange(self, message):
        if self.sock is None:
            raise HostConnectionError("Not connected to the host.")
        try:
            _send_msg(self.sock, message)
            resp = _recv_msg(self.sock)
        except (ConnectionError, ssl.SSLError, OSError) as e:
            raise HostConnectionError(
                "Lost the connection to the main computer.") from e
        if resp is None:
            raise HostConnectionError(
                "The main computer closed the connection.")
        return resp

    def request(self, op, **args):
        """Send an operation using the current session token."""
        return self._exchange({"op": op, "token": self.token, "args": args})

    def login(self, username, password):
        """Authenticate and remember the session token on success."""
        resp = self._exchange({"op": "login", "token": None,
                               "args": {"username": username,
                                        "password": password}})
        if resp.get("ok"):
            self.token = (resp.get("result") or {}).get("token")
        return resp

    def logout(self):
        if self.sock is None or self.token is None:
            return {"ok": True, "result": {"signed_out": True}}
        resp = self._exchange({"op": "logout", "token": self.token,
                               "args": {}})
        self.token = None
        return resp

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
