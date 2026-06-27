# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Business profile for Ledger.

The business profile is the owner's own information: business name,
address, contact details, and a tagline. It is stored inside the data
file (the business_profile table), which means it belongs to one set
of books only.

This is deliberately separate from the program's attribution. The
profile is YOUR data and shows on YOUR reports; if someone else uses
Ledger with their own data file, they fill in their own profile and
never see yours. The attribution ("Designed & built by ...") is part
of the program itself and lives in the About screen and the source
files -- see ledger/about.py.
"""

# The profile is always a single row at id = 1.
_FIELDS = ("name", "address", "contact", "tagline")

# Whether a set of books is run as a business or for personal use. This
# only affects the wording the program shows; the accounts and the
# bookkeeping are identical for both.
VALID_KINDS = ("business", "personal")
DEFAULT_KIND = "business"


def get_profile(conn):
    """
    Return the business profile as a dict with keys
    name, address, contact, tagline, kind. If no profile has been saved
    yet, every text value is an empty string and kind is 'business'.
    """
    row = conn.execute(
        "SELECT name, address, contact, tagline, kind "
        "FROM business_profile WHERE id = 1"
    ).fetchone()
    if row is None:
        data = {f: "" for f in _FIELDS}
        data["kind"] = DEFAULT_KIND
        return data
    data = {f: (row[f] or "") for f in _FIELDS}
    data["kind"] = (row["kind"] or DEFAULT_KIND)
    return data


def get_kind(conn):
    """Return 'business' or 'personal' for this set of books."""
    return get_profile(conn)["kind"]


def is_personal(conn):
    """True if this ledger is set up for personal use."""
    return get_kind(conn) == "personal"


def save_profile(conn, name="", address="", contact="", tagline="",
                 kind=None):
    """
    Save (or update) the business profile. Whatever is passed in
    replaces what was there before. Values are trimmed of surrounding
    whitespace; missing values become empty strings.

    `kind` is 'business' or 'personal'. If it is left as None, the
    currently saved kind is kept (so saving the other fields never
    silently changes whether the books are business or personal).
    """
    name = (name or "").strip()
    address = (address or "").strip()
    contact = (contact or "").strip()
    tagline = (tagline or "").strip()

    if kind is None:
        kind = get_kind(conn)
    if kind not in VALID_KINDS:
        kind = DEFAULT_KIND

    # INSERT the single row if it does not exist, otherwise UPDATE it.
    exists = conn.execute(
        "SELECT 1 FROM business_profile WHERE id = 1"
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE business_profile "
            "SET name = ?, address = ?, contact = ?, tagline = ?, kind = ? "
            "WHERE id = 1",
            (name, address, contact, tagline, kind),
        )
    else:
        conn.execute(
            "INSERT INTO business_profile "
            "(id, name, address, contact, tagline, kind) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (name, address, contact, tagline, kind),
        )
    conn.commit()
    return get_profile(conn)


def set_kind(conn, kind):
    """
    Switch this ledger between 'business' and 'personal' without
    touching the name/address/contact/tagline already entered.
    """
    p = get_profile(conn)
    return save_profile(conn, name=p["name"], address=p["address"],
                        contact=p["contact"], tagline=p["tagline"],
                        kind=kind)


def has_profile(conn):
    """True if a business name has been set (the minimum useful profile)."""
    return bool(get_profile(conn)["name"])


def header_lines_from(p):
    """Derive the report-header lines from a profile dict (pure: no database).
    Shared by profile_header_lines() and the data gateway so local and host
    rendering stay identical."""
    lines = []
    if p.get("name"):
        lines.append(p["name"])
    if p.get("tagline"):
        lines.append(p["tagline"])
    if p.get("address"):
        # An address may be typed across several lines; keep them.
        lines.extend(p["address"].splitlines())
    if p.get("contact"):
        lines.extend(p["contact"].splitlines())
    return lines


def profile_header_lines(conn):
    """
    Return the profile as a short list of lines suitable for putting at
    the top of a printed report. Empty fields are skipped. If nothing
    has been entered, returns an empty list (so reports just omit the
    header cleanly).
    """
    return header_lines_from(get_profile(conn))
