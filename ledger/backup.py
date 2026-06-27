# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Backup and restore for Ledger.

All of Ledger's data lives in a single SQLite file, so a backup is
simply a timestamped copy of that file, and a restore is copying one
of those copies back into place.

For a Protected (encrypted) book the data file on disk is already an
encrypted blob, so a copy of it is an encrypted backup automatically --
there is no separate "encrypt the backup" step, and a backup can only be
read back with the book's key. For an Open book the file is a plain
SQLite database and the backup is a plain copy, exactly as it has always
been.

Backups are written to a "Ledger Backups" folder inside your
Documents by default, in a sub-folder named for your business, with the
date and time in the filename so you can keep several and always know
which is which. Nothing is ever overwritten by a backup -- each one is a
new file. You can also back up to any other folder (a USB drive or a
cloud folder) for safekeeping away from this computer.

Restoring DOES overwrite your current data file, so restore() makes a
one-off safety copy of the current file first (called a
'pre-restore' backup) before replacing it. That way, even an
unwanted restore can be undone.
"""

import os
import shutil
import glob
import hashlib
import re
from datetime import datetime, timedelta

from .database import DEFAULT_DB_PATH
from . import paths
from . import crypto

# How long automatic on-exit backups are kept before being tidied away.
# Manual backups are never removed automatically; see prune_backups().
AUTO_BACKUP_KEEP_DAYS = 30


def documents_backup_root():
    """The visible top-level backup folder: a 'Ledger Backups' folder
    inside the user's Documents. Each set of books gets its own sub-folder
    named after the business (or person), so backups are easy to find and
    never mixed up between different books."""
    return os.path.join(paths.documents_dir(), "Ledger Backups")


def _safe_folder_name(name):
    """Turn a business or person name into a safe folder name. Only the
    characters that are actually illegal in a folder name are replaced
    (so 'Kelly's Computers LLC' stays readable)."""
    name = (name or "").strip()
    invalid = set('\\/:*?"<>|')
    cleaned = "".join("_" if (ch in invalid or ord(ch) < 32) else ch
                      for ch in name)
    cleaned = " ".join(cleaned.split())     # collapse runs of whitespace
    cleaned = cleaned.rstrip(" .")           # Windows dislikes trailing dot/space
    return cleaned or "Unnamed Books"


def business_backup_dir(name):
    """
    The default backup folder for the books belonging to `name`:
    Documents/Ledger Backups/<name>/. This is the parent that holds the
    two sub-folders below; the folder is not created here -- backup()
    creates what it needs when a backup is actually made.
    """
    return os.path.join(documents_backup_root(), _safe_folder_name(name))


# Within each book's folder, backups are kept apart by how they were made:
# the ones the user chooses to make, and the automatic on-exit safety
# copies. Keeping them in separate sibling folders means that if one folder
# is deleted, the other -- and the restore points in it -- still survives.
MANUAL_SUBDIR = "Manual Backups"
AUTO_SUBDIR = "Automatic Backups"


def manual_dir(book_dir):
    """The sub-folder for backups the user makes themselves."""
    return os.path.join(book_dir, MANUAL_SUBDIR)


def auto_dir(book_dir):
    """The sub-folder for the automatic backups taken on exit."""
    return os.path.join(book_dir, AUTO_SUBDIR)


def _legacy_backup_dir():
    """The old hidden location (~/.ledger/backups). Still read when
    listing so backups from earlier versions are never lost. Computed
    without creating it."""
    return os.path.join(paths.data_dir(), "backups")


def _default_backup_dir():
    """A general, visible fallback folder, used for the one-off pre-restore
    safety copy. Ordinary per-book backups use business_backup_dir()."""
    return documents_backup_root()


def backup(db_path=DEFAULT_DB_PATH, backup_dir=None, create=False,
           name_tag=""):
    """
    Make a timestamped copy of the database file.

    `backup_dir` chooses where it goes:
      * None             -> the old hidden folder (kept only as a safe
                            fallback for callers that pass nothing).
      * folder, create=True  -> created if needed. This is how the default
                            Documents/Ledger Backups/<business>/ folder
                            is used.
      * folder, create=False (the default) -> the folder must ALREADY
                            exist. This is deliberate for removable drives:
                            an unplugged USB stick fails loudly instead of
                            quietly creating an empty folder on the internal
                            disk and "backing up" there.

    `name_tag` is an optional marker added to the filename, after the
    timestamp, to show how a backup was made (e.g. "_auto" for the
    safety copy taken automatically on exit). It is kept after the
    timestamp on purpose so backups still sort chronologically, and it
    still matches the "ledger_backup_*" pattern, so tagged backups are
    listed and restored exactly like any other.

    Returns the full path of the backup created. Raises FileNotFoundError
    if there is no database to back up, or if a create=False `backup_dir`
    does not exist.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"No database found at {db_path}. "
            f"Run 'init' and record some entries first."
        )

    if backup_dir is None:
        backup_dir = _legacy_backup_dir()
        os.makedirs(backup_dir, exist_ok=True)
    elif create:
        # A default location we are allowed to create (Documents folder).
        os.makedirs(backup_dir, exist_ok=True)
    else:
        # A custom location (USB drive, cloud folder): it must already
        # exist, so an unplugged drive fails loudly.
        if not os.path.isdir(backup_dir):
            raise FileNotFoundError(
                f"The folder '{backup_dir}' does not exist or is not "
                f"reachable. If it is a USB drive, check that it is "
                f"plugged in."
            )

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"ledger_backup_{stamp}{name_tag}.db"
    dest = os.path.join(backup_dir, name)

    # copy2 preserves timestamps; never overwrites because the name is
    # unique to the second.
    shutil.copy2(db_path, dest)
    return dest


def list_backups(backup_dir=None):
    """
    Return the paths of backup files, newest first.

    With an explicit `backup_dir`, that book's folder is listed -- including
    its "Manual Backups" and "Automatic Backups" sub-folders, plus the
    folder itself for any flat backups left by earlier versions. With no
    folder, every default location is searched -- each business sub-folder
    under Documents/Ledger Backups and the two sub-folders inside each,
    plus the old hidden folder -- so no backup is ever hidden from view.
    """
    if backup_dir:
        dirs = [backup_dir, manual_dir(backup_dir), auto_dir(backup_dir)]
    else:
        dirs = []
        root = documents_backup_root()
        if os.path.isdir(root):
            dirs.append(root)
            for entry in sorted(os.listdir(root)):
                sub = os.path.join(root, entry)
                if os.path.isdir(sub):
                    dirs.append(sub)
                    dirs.append(manual_dir(sub))
                    dirs.append(auto_dir(sub))
        dirs.append(_legacy_backup_dir())

    files, seen = [], set()
    for d in dirs:
        if d and os.path.isdir(d):
            for f in glob.glob(os.path.join(d, "ledger_backup_*.db")):
                if f not in seen:
                    seen.add(f)
                    files.append(f)
    # The timestamp lives in the filename, so sort by the filename (not the
    # full path) to stay chronological even across different sub-folders.
    return sorted(files, key=lambda p: os.path.basename(p), reverse=True)


def _file_digest(path):
    """A content fingerprint (SHA-256) of a file's raw bytes, read in chunks
    so even a large data file is handled without loading it all into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()


def _content_digest(path, data_key=None):
    """A fingerprint of a backup's *contents* -- the actual bookkeeping data,
    not the bytes as they happen to sit on disk.

    This matters for encrypted books. Each encrypted save uses a fresh random
    nonce, so identical data is written as different bytes every time.
    Comparing raw bytes would therefore conclude the data had changed when it
    had not, and take a needless backup on every close. So when a key is given
    and the file is one of our encrypted books, we decrypt it first and
    fingerprint the data inside; identical data then yields an identical
    fingerprint however the bytes were encrypted.

    For an unencrypted (Open) book -- no key -- the file's bytes ARE the data,
    so this is just the plain file fingerprint, exactly as before.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data_key is not None and crypto.looks_like_encrypted_db(data):
        try:
            data = crypto.decrypt_db_bytes(data_key, data)
        except Exception:
            # Can't decrypt (wrong key, or damaged): fall back to the raw
            # bytes rather than fail. The worst case is one extra safety copy.
            pass
    return hashlib.sha256(data).digest()


def is_current_state_backed_up(db_path=DEFAULT_DB_PATH, backup_dir=None,
                               data_key=None):
    """
    True if the current database already matches one of its backups,
    i.e. the user has saved the data as it stands right now.

    This is what the program checks when it closes: if the answer is
    False, the data has changed since the last backup, so an automatic
    safety copy is taken before exit.

    Comparison is by *content*. For an encrypted book, the live file and the
    backups are decrypted with `data_key` and the data inside compared, so a
    backup made moments ago is still recognised even though every encrypted
    save writes different bytes (a fresh nonce each time). Without a key,
    comparison is by exact file bytes, exactly as before.

    If there is no database yet, there is nothing to lose, so this
    returns True. If the database can't be read, it returns False so the
    caller errs on the side of making a backup.
    """
    if not os.path.exists(db_path):
        return True
    try:
        current = _content_digest(db_path, data_key)
    except OSError:
        return False
    # Newest first: the common case is a manual backup taken seconds ago,
    # so this usually matches on the very first file and stops.
    for path in list_backups(backup_dir):
        try:
            if _content_digest(path, data_key) == current:
                return True
        except OSError:
            continue
    return False


_BACKUP_TIME_RE = re.compile(r"ledger_backup_(\d{4}-\d{2}-\d{2}_\d{6})")


def _parse_backup_time(path):
    """The moment a backup was made, read from its filename. The filename
    stamp is used rather than the file's modified-time because copying a
    file preserves the *data* file's timestamp, not the moment the copy
    was made -- so mtime would be the wrong clock to age backups by."""
    m = _BACKUP_TIME_RE.search(os.path.basename(path))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def prune_backups(book_dir, days=AUTO_BACKUP_KEEP_DAYS, keep_newest=1):
    """
    Tidy old AUTOMATIC backups out of a book's folder so they cannot pile
    up forever. Only the automatic on-exit copies are ever removed:

      * The "Manual Backups" folder is never touched -- those are
        deliberate save points the user chose to make.
      * An automatic backup is removed only if it is older than `days`
        days, going by the timestamp in its filename.
      * The newest `keep_newest` automatic copies are ALWAYS kept, whatever
        their age, so a book is never left without a recent restore point
        (even one not changed in months keeps its last automatic copy).

    Looks in the "Automatic Backups" sub-folder, and also at any flat
    "..._auto.db" files left in the book folder by earlier versions, so
    nothing is missed. Custom locations (USB drives, cloud folders) are
    never pruned. Returns the list of files removed.
    """
    if not book_dir:
        return []
    auto_files = []
    for d in (auto_dir(book_dir), book_dir):
        if os.path.isdir(d):
            auto_files.extend(
                glob.glob(os.path.join(d, "ledger_backup_*_auto.db")))
    # Newest first by filename timestamp.
    auto_files = sorted(set(auto_files),
                        key=lambda p: os.path.basename(p), reverse=True)
    protected = set(auto_files[:max(keep_newest, 0)])  # always keep these
    cutoff = datetime.now() - timedelta(days=days)
    removed = []
    for path in auto_files:
        if path in protected:
            continue
        made = _parse_backup_time(path)
        if made is None or made >= cutoff:
            continue                                  # unreadable date, or recent
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass                                      # if it won't delete, leave it
    return removed


# --- remembering the last place the user chose to back up to ----------
#
# When the user picks a custom location (a USB drive, another folder),
# we remember it in a tiny text file so the app can offer a one-click
# "back up there again" next time. This is a convenience only -- it
# never makes a backup on its own, and if the remembered place is gone
# (e.g. the USB stick is unplugged) the app simply notices and says so.

def _prefs_path():
    """The little file that remembers the last custom backup folder.
    It sits in the per-user data folder, wherever that is on this OS."""
    return os.path.join(paths.data_dir(), "last_backup_location.txt")


def get_last_location():
    """
    Return the last custom backup folder the user chose, or None if
    they have never chosen one (or the saved file can't be read).
    """
    path = _prefs_path()
    try:
        with open(path, "r") as f:
            location = f.read().strip()
        return location or None
    except OSError:
        return None


def remember_location(folder):
    """Save `folder` as the last custom backup location."""
    if not folder:
        return
    try:
        # paths.data_dir() makes sure the folder exists.
        with open(_prefs_path(), "w") as f:
            f.write(folder.strip())
    except OSError:
        # Remembering is a nice-to-have; if it fails, carry on quietly.
        pass


def location_available(folder):
    """
    True if `folder` exists and can be written to right now. Used to
    tell whether a remembered location (like a USB drive) is currently
    plugged in / reachable.
    """
    return bool(folder) and os.path.isdir(folder) and os.access(folder, os.W_OK)


def restore(backup_file, db_path=DEFAULT_DB_PATH, data_key=None):
    """
    Replace the current database with a backup copy.

    Before overwriting, the current database (if any) is itself copied
    aside to a 'pre-restore' file, so this operation can be undone.

    For a Protected book, `data_key` is the key to the currently open book.
    The chosen backup is checked FIRST -- it must be one of our encrypted
    files and must decrypt with this key -- before anything on disk is
    touched. That refuses, safely and with nothing changed, a backup that
    belongs to a different set of books, a plaintext backup made before this
    book was protected, or a damaged file. A restore can therefore never
    leave you locked out of your own books.

    The mirror case is guarded too: an *encrypted* backup cannot be restored
    when there is no key (an unencrypted/Open book, or a computer without the
    cryptography library). That check is only a look at the file's header, so
    it works even where encryption is unavailable, and it stops an encrypted
    blob being written over a readable book and then failing to reopen.

    Returns a tuple: (path_restored_from, path_of_safety_copy_or_None).
    """
    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    # Refuse an encrypted backup when we hold no key to read it (the current
    # book is Open, or this computer lacks the cryptography library). This is
    # a header-only check, so it needs no key and no library.
    if data_key is None and crypto.is_encrypted_db_file(backup_file):
        raise ValueError(
            "This backup is from a protected (encrypted) set of books, so it "
            "can't be restored into an unencrypted one. Open the matching "
            "protected book first, then restore into it. Your current data "
            "has NOT been changed."
        )

    # For a protected book, verify the backup belongs to it and opens with
    # the current key BEFORE replacing anything.
    if data_key is not None:
        try:
            crypto.load_encrypted_db(backup_file, data_key)
        except Exception:
            raise ValueError(
                "This backup could not be opened with the current book's "
                "key. It may belong to a different set of books, be a "
                "plaintext backup made before this book was protected, or be "
                "damaged. Your current data has NOT been changed."
            )

    safety_copy = None
    if os.path.exists(db_path):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safety_dir = _default_backup_dir()
        os.makedirs(safety_dir, exist_ok=True)
        safety_copy = os.path.join(
            safety_dir, f"ledger_pre-restore_{stamp}.db"
        )
        shutil.copy2(db_path, safety_copy)

    # Make sure the destination folder exists, then copy the backup in.
    dest_dir = os.path.dirname(db_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(backup_file, db_path)

    return backup_file, safety_copy
