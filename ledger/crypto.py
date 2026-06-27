# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
The cryptographic foundation for Ledger's optional encryption.

Everything in this module is deliberately small, self-contained, and built
only from well-reviewed, standard building blocks (the `cryptography`
library). It uses no home-made crypto -- which matters all the more because
Ledger is open source: the strength comes from the secret the user holds,
not from anything hidden in this code.

The design is the "wrapped key" (envelope) pattern used by serious systems
like disk encryption:

  * There is ONE random *data key* that actually encrypts the books and
    their backups. The data key itself is never shown to anyone and never
    stored in the clear.
  * The data key is kept in a small *vault* as one or more *slots*. Each
    slot stores the data key locked ("wrapped") under a different secret --
    the owner's passphrase, the recovery code, and (on the business side)
    each employee's password.

This single idea gives us everything the program needs:

  * Many users, one set of books -- each person has their own slot, so each
    unlocks the same data key with their own password. Nobody shares a
    password and nobody learns anyone else's.
  * Recovery -- the recovery code is just another slot, so a forgotten
    passphrase can be recovered by unlocking with the code and then
    re-wrapping a new passphrase. Nothing has to be re-encrypted.
  * Changing or resetting a password -- re-wrap that one slot; the data key
    (and therefore all the encrypted data) is untouched.

What this protects, stated honestly: data *at rest*. A stolen laptop, a
copied or un-deleted file, a nosy person on the same computer -- all get
unreadable bytes. It does not protect data while Ledger is open and
unlocked, and it cannot stop a file being deleted. Encryption guards
readability, not existence.
"""

import os
import json
import base64
import secrets

try:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    CRYPTO_AVAILABLE = True
except Exception:
    # The 'cryptography' library is not installed. The program must still
    # open and work normally for unencrypted books -- so we do NOT fail here.
    # Any actual encryption operation calls _require_crypto() below, which
    # raises a clear, catchable error that the GUI turns into a friendly
    # "install the library" message.
    CRYPTO_AVAILABLE = False
    Scrypt = None
    AESGCM = None

    class InvalidTag(Exception):
        pass


def _require_crypto():
    if not CRYPTO_AVAILABLE:
        raise RuntimeError(
            "The 'cryptography' library is required for encryption but is "
            "not installed. Install it with:  pip install cryptography")


# --- tunables --------------------------------------------------------------
#
# The key-derivation cost. scrypt is memory-hard, so these settings make
# guessing a passphrase very expensive while staying quick enough to unlock
# on an ordinary (even older) computer. They are stored *with* each slot, so
# raising them does not break old vaults: existing slots keep unlocking with
# the cost they were created at, and any slot re-wrapped later (a new book, or
# a password change) is created at the new, stronger cost.
#
# 2**16 (about 64 MB of memory per attempt) costs roughly a fifth of a second
# to unlock on a typical machine -- paid once at sign-in only, never per
# action -- and several times that for an attacker guessing in bulk.
SCRYPT_N = 2 ** 16          # CPU/memory cost (65536)
SCRYPT_R = 8
SCRYPT_P = 1

DATA_KEY_BYTES = 32         # 256-bit key for AES-GCM
SALT_BYTES = 16
NONCE_BYTES = 12

VAULT_VERSION = 1

# A deliberately unambiguous alphabet for recovery codes: no 0/O, 1/I/L, so
# the code is safe to read aloud and to copy by hand without mistakes.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# --- small helpers ---------------------------------------------------------

def _b64e(raw):
    return base64.b64encode(raw).decode("ascii")


def _b64d(text):
    return base64.b64decode(text.encode("ascii"))


def _derive_key(secret, salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P):
    """Turn a passphrase or recovery code into a 32-byte key. The same
    secret + salt + cost always yields the same key; without the secret the
    key cannot be reproduced."""
    _require_crypto()
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    kdf = Scrypt(salt=salt, length=DATA_KEY_BYTES, n=n, r=r, p=p)
    return kdf.derive(secret)


# --- recovery codes --------------------------------------------------------

def generate_recovery_code(groups=12, group_len=4):
    """A long, random recovery code, shown in dash-separated groups so it is
    easy to write down. The default is 48 characters from a 31-symbol
    alphabet -- far beyond any possibility of being guessed."""
    chars = [secrets.choice(_CODE_ALPHABET)
             for _ in range(groups * group_len)]
    blocks = ["".join(chars[i:i + group_len])
              for i in range(0, len(chars), group_len)]
    return "-".join(blocks)


def generate_temp_password(length=12):
    """A short, readable one-time password an owner can hand to a new user.

    Uses the same unambiguous alphabet as recovery codes (no 0/O/1/I/L) and is
    returned ungrouped. At sign-in, spaces and capitalisation do not matter,
    because logins also try the normalised form -- so an employee can type it
    however is easiest, then set their own password."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def normalize_code(text):
    """Tidy a typed recovery code so spacing, dashes, and capitalisation do
    not matter: keep only the real characters, upper-cased."""
    if not text:
        return ""
    up = text.upper()
    return "".join(ch for ch in up if ch in _CODE_ALPHABET)


# --- the vault -------------------------------------------------------------

def _wrap(data_key, secret, label, slot_type):
    """Lock the data key under one secret, producing a slot. Each slot has
    its own random salt, and the label/type are bound in as authenticated
    data so a slot cannot be silently relabelled."""
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = _derive_key(secret, salt)
    aad = f"{slot_type}:{label}".encode("utf-8")
    ct = AESGCM(key).encrypt(nonce, data_key, aad)
    return {
        "id": secrets.token_hex(8),
        "label": label,
        "type": slot_type,
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R,
                "p": SCRYPT_P, "salt": _b64e(salt)},
        "nonce": _b64e(nonce),
        "ct": _b64e(ct),
    }


def _unwrap(slot, secret):
    """Try to recover the data key from one slot. Returns the data key, or
    None if this secret does not fit this slot (or the slot was tampered
    with -- AES-GCM detects that and we treat it as a miss)."""
    try:
        kdf = slot["kdf"]
        key = _derive_key(secret, _b64d(kdf["salt"]),
                          n=kdf["n"], r=kdf["r"], p=kdf["p"])
        aad = f"{slot['type']}:{slot['label']}".encode("utf-8")
        return AESGCM(key).decrypt(_b64d(slot["nonce"]),
                                   _b64d(slot["ct"]), aad)
    except (InvalidTag, KeyError, ValueError):
        return None


def create_vault(passphrase, owner_label="owner"):
    """Begin a new encrypted set of books.

    Generates a fresh random data key and locks it under the owner's
    passphrase and under a newly generated recovery code. Returns the vault
    (safe to store as-is -- it holds no secret in the clear) and the
    recovery code (which must be shown to the owner once and then never kept
    by the program).
    """
    _require_crypto()
    data_key = os.urandom(DATA_KEY_BYTES)
    recovery_code = generate_recovery_code()
    vault = {
        "version": VAULT_VERSION,
        "slots": [
            _wrap(data_key, passphrase, owner_label, "passphrase"),
            _wrap(data_key, normalize_code(recovery_code), "recovery",
                  "recovery"),
        ],
    }
    return vault, recovery_code


def unlock(vault, secret):
    """Open the vault with any valid secret (a passphrase or a recovery
    code), returning the data key. Raises ValueError if nothing fits."""
    _require_crypto()
    norm = normalize_code(secret)
    for slot in vault.get("slots", []):
        # Recovery slots expect the normalised code; others expect the
        # passphrase exactly as typed. Try both forms to keep callers simple.
        for candidate in ((norm,) if slot["type"] == "recovery"
                          else (secret, norm)):
            dk = _unwrap(slot, candidate)
            if dk is not None:
                return dk
    raise ValueError("That passphrase or recovery code is not correct.")


def unlock_as(vault, label, secret):
    """Open the vault using ONLY the slot with the given label (a specific
    user's login). Returns the data key, or raises ValueError if that user's
    password is wrong or there is no such user.

    This is what a username login uses, and it is essential to security: one
    person's password must never open another person's account. (The general
    unlock(), which tries every slot, is only for the single-secret cases --
    the owner's own passphrase and the recovery code.)
    """
    _require_crypto()
    norm = normalize_code(secret)
    for slot in vault.get("slots", []):
        if slot.get("label") != label:
            continue
        for candidate in ((norm,) if slot["type"] == "recovery"
                          else (secret, norm)):
            dk = _unwrap(slot, candidate)
            if dk is not None:
                return dk
        break  # the labelled slot exists but the password did not fit it
    raise ValueError("That username or password is not correct.")


def verify(vault, secret):
    """True if `secret` opens the vault, without exposing the data key."""
    try:
        unlock(vault, secret)
        return True
    except ValueError:
        return False


def add_slot(vault, data_key, secret, label, slot_type="user"):
    """Give another secret access to the same data key (e.g. add an
    employee). The caller must already hold the data key (i.e. be unlocked).
    A label is unique within a vault; an existing one is replaced."""
    vault["slots"] = [s for s in vault.get("slots", [])
                      if s["label"] != label]
    vault["slots"].append(_wrap(data_key, secret, label, slot_type))
    return vault


def remove_slot(vault, label):
    """Revoke a secret's access by deleting its slot (e.g. remove an
    employee). The data key itself is unchanged; for full revocation after a
    departure, rotate the data key as well (a later feature)."""
    before = len(vault.get("slots", []))
    vault["slots"] = [s for s in vault.get("slots", [])
                      if s["label"] != label]
    return len(vault["slots"]) < before


def change_secret(vault, data_key, label, new_secret, slot_type=None):
    """Re-lock one slot under a new secret -- used to change a passphrase or
    to reset an employee's password. Keeps the slot's type unless told
    otherwise. The data key (and all encrypted data) is untouched."""
    existing = next((s for s in vault.get("slots", [])
                     if s["label"] == label), None)
    stype = slot_type or (existing["type"] if existing else "user")
    return add_slot(vault, data_key, new_secret, label, stype)


def list_slots(vault):
    """The labels and types of who/what can currently unlock the books --
    never any secret. Useful for an employee-management screen."""
    return [{"label": s["label"], "type": s["type"], "id": s["id"]}
            for s in vault.get("slots", [])]


# --- saving / loading the vault -------------------------------------------

def dumps(vault):
    """The vault as text, safe to store on disk: it contains only salts and
    the data key in its locked forms, never a passphrase or the data key
    itself."""
    return json.dumps(vault, indent=2, sort_keys=True)


def loads(text):
    return json.loads(text)


# --- the companion vault file ---------------------------------------------
#
# Each protected set of books keeps its vault in a small file sitting right
# next to the data file: "books.db" -> "books.db.vault". The vault file holds
# only salts and the data key in its locked forms -- never a passphrase or
# the data key itself -- so it is safe to sit on disk. Its mere presence is
# how the program knows, before unlocking anything, that a book is protected
# and that it should ask for the passphrase.

VAULT_SUFFIX = ".vault"


def vault_path(db_path):
    """The path of the vault file that belongs to a data file."""
    return db_path + VAULT_SUFFIX


def is_protected(db_path):
    """True if this set of books has a vault -- i.e. it is encrypted."""
    return os.path.exists(vault_path(db_path))


def save_vault(db_path, vault):
    """Write a book's vault file. Written to a temporary name first and then
    moved into place, so a vault file is never left half-written."""
    final = vault_path(db_path)
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dumps(vault))
    os.replace(tmp, final)
    return final


def load_vault(db_path):
    """Read a book's vault file."""
    with open(vault_path(db_path), "r", encoding="utf-8") as f:
        return loads(f.read())


def delete_vault(db_path):
    """Remove a book's vault file (used when turning encryption off)."""
    p = vault_path(db_path)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


# --- encrypting the actual data (the books, and backups) ------------------

def encrypt_blob(data_key, plaintext):
    """Encrypt bytes with the data key, returning a self-contained blob
    (nonce + ciphertext). Authenticated, so tampering or corruption is
    detected on the way back out."""
    _require_crypto()
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(data_key).encrypt(nonce, plaintext, None)
    return nonce + ct


def decrypt_blob(data_key, blob):
    """Reverse encrypt_blob. Raises ValueError if the data key is wrong or
    the blob has been altered or damaged."""
    _require_crypto()
    try:
        nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
        return AESGCM(data_key).decrypt(nonce, ct, None)
    except (InvalidTag, ValueError):
        raise ValueError("The data could not be decrypted -- wrong key, or "
                         "the file has been changed or damaged.")


def encrypt_file(data_key, src_path, dest_path):
    """Write an encrypted copy of a file (used to encrypt a backup)."""
    with open(src_path, "rb") as f:
        blob = encrypt_blob(data_key, f.read())
    with open(dest_path, "wb") as f:
        f.write(blob)
    return dest_path


def decrypt_file(data_key, src_path, dest_path):
    """Write a decrypted copy of an encrypted file (used to read a backup
    before restoring it)."""
    with open(src_path, "rb") as f:
        data = decrypt_blob(data_key, f.read())
    with open(dest_path, "wb") as f:
        f.write(data)
    return dest_path


# --- encrypting the whole books file (the live database, at rest) ----------
#
# The live database is held in memory while Ledger is open; only an encrypted
# copy is ever written to disk. That copy is a single self-describing blob:
#
#     MAGIC (6 bytes) | VERSION (1 byte) | nonce + ciphertext (encrypt_blob)
#
# The little header lets the program recognise its own encrypted files, tell
# them apart from a plaintext SQLite file, and refuse to touch something it
# does not understand -- so the wrong file is never silently corrupted.

ENC_DB_MAGIC = b"LDGRDB"          # "this is an encrypted Ledger book"
ENC_DB_VERSION = 1
_ENC_DB_HEADER_LEN = len(ENC_DB_MAGIC) + 1


def encrypt_db_bytes(data_key, raw):
    """Encrypt the raw bytes of a SQLite database into a self-describing,
    authenticated blob suitable for writing to disk."""
    _require_crypto()
    return ENC_DB_MAGIC + bytes([ENC_DB_VERSION]) + encrypt_blob(data_key, raw)


def looks_like_encrypted_db(blob):
    """A cheap, key-free check of whether some bytes are one of our encrypted
    book files, by their header. Never raises."""
    try:
        return (len(blob) >= _ENC_DB_HEADER_LEN
                and blob[:len(ENC_DB_MAGIC)] == ENC_DB_MAGIC)
    except Exception:
        return False


def decrypt_db_bytes(data_key, blob):
    """Reverse encrypt_db_bytes. Raises ValueError if the header is not one
    of ours, the format version is unknown, or the key is wrong / the data
    has been changed or damaged (AES-GCM authentication)."""
    _require_crypto()
    if not looks_like_encrypted_db(blob):
        raise ValueError(
            "This does not look like an encrypted Ledger book file.")
    version = blob[len(ENC_DB_MAGIC)]
    if version != ENC_DB_VERSION:
        raise ValueError(
            "This encrypted book was written by a newer version of Ledger "
            "(format {}); please update Ledger to open it.".format(version))
    return decrypt_blob(data_key, blob[_ENC_DB_HEADER_LEN:])


def is_encrypted_db_file(path):
    """True if the file at `path` exists and carries our encrypted-book
    header. A quick, key-free sanity check; reads only the first few bytes."""
    try:
        with open(path, "rb") as f:
            head = f.read(_ENC_DB_HEADER_LEN)
        return looks_like_encrypted_db(head)
    except OSError:
        return False


def save_encrypted_db(path, data_key, raw):
    """Write the encrypted form of a database to `path`, atomically: the
    bytes are written to a temp file, forced to disk, then moved into place,
    so an interruption never leaves a half-written file -- the previous good
    copy survives until the new one is complete."""
    blob = encrypt_db_bytes(data_key, raw)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def load_encrypted_db(path, data_key):
    """Read and decrypt an encrypted database file, returning the raw SQLite
    bytes (to be loaded into an in-memory database)."""
    with open(path, "rb") as f:
        return decrypt_db_bytes(data_key, f.read())
