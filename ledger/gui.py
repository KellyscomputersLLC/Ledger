# Ledger -- Designed & built by Kelly's Computers LLC
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
Desktop graphical interface for Ledger.

This is a window-based front end that sits on top of exactly the same
accounting engine used by the command line -- the same double-entry
rules, the same database, the same reports. Nothing about how your
data is stored or calculated changes; this just makes it friendlier
to use day to day.

Run it with:   python3 -m ledger.gui
or double-click the launcher (see the README).

Built with tkinter, which is part of Python's standard toolkit. On
Debian you may need to install it once:

    sudo apt install python3-tk
"""

import os
import glob
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from . import (database, seed, formatting, backup, profile, about, paths,
               crypto, printing, roles, users, service, gateway, hostnet,
               clientconf, discovery, host_main, hoststate)


# A small, calm colour palette. tkinter isn't flashy, but a consistent
# set of colours keeps it tidy.
#
# The signature colour is Kelly green -- a nod to Kelly's Computers LLC.
# ACCENT is true Kelly green; the header bar and buttons use slightly
# deeper shades of the same green so white text stays crisp and
# readable on them.
BG = "#f5f6f8"            # soft, cool grey page background
PANEL = "#ffffff"
ACCENT = "#a66e1a"        # brass -- the signature accent (Ink & Brass)
ACCENT_ACTIVE = "#875811"  # deeper brass for hover / pressed
ACCENT_TEXT = "#ffffff"
HEADER_BG = "#1e2a4a"     # deep navy "ink" -- the header bar
HEADER_BTN = "#2b3a5c"    # header buttons, a lighter navy so they read
HEADER_BTN_ACTIVE = "#374a70"  # header buttons while pressed
MUTED = "#5b6472"         # muted slate-grey for secondary text
ERROR = "#b03030"         # error / mismatch (red, semantic)
OK = "#196128"            # success: balanced / reconciled (green, semantic)

# The dark "first-run" dialog palette, matching the welcome tour. The
# encryption setup, recovery-code, and unlock dialogs use it so their white
# entry fields stand out clearly against a deep blue, rather than light
# fields on a light panel (which can wash out, especially on older screens).
DLG_BG = "#34466e"        # deep slate-blue dialog background
DLG_TXT = "#eef1f6"       # light main text
DLG_DIM = "#b6c2da"       # muted light text
DLG_BTN = "#46597f"       # secondary buttons (lighter than the panel)
DLG_BTN_ACTIVE = "#566a92"
DLG_ERR = "#ffb4a8"       # error text that stays readable on the dark blue
DLG_CARD = "#eef1f6"      # light row for choices, so the radio/check boxes
DLG_CARD_TX = "#1e2a4a"   # render and click clearly (they vanish on dark)
DLG_CARD_ACTIVE = "#dfe5ef"

# Fonts. Rather than naming a specific font family (which might exist
# on Linux but not Windows, or vice versa), we build on tkinter's
# built-in *named fonts*. These resolve automatically to whatever the
# current operating system uses for its interface:
#   * TkDefaultFont -- the standard UI font (DejaVu Sans on Linux,
#                      Segoe UI on Windows, etc.)
#   * TkFixedFont   -- the standard monospaced font, used for the
#                      reports so columns line up.
# This is set up properly in LedgerApp.__init__ (see _build_fonts),
# because named fonts can only be created once a Tk root exists. Until
# then these are simple tuples as sensible fallbacks.
FONT = ("TkDefaultFont", 10)
FONT_BOLD = ("TkDefaultFont", 10, "bold")
FONT_TITLE = ("TkDefaultFont", 13, "bold")
FONT_MONO = ("TkFixedFont", 10)
FONT_HEADER = ("TkDefaultFont", 16, "bold")
FONT_BIG = ("TkDefaultFont", 18, "bold")


# --- builders for the dark first-run dialogs ------------------------------
# Classic tk widgets (not ttk) so they can be coloured directly, the same way
# the welcome tour is built. White entry fields on the deep-blue background
# give clear, high-contrast input areas.

def _dlg_label(master, text, *, dim=False, title=False, err=False,
               fg=None, wrap=470):
    colour = fg or (DLG_ERR if err else (DLG_DIM if dim else DLG_TXT))
    font = FONT_TITLE if title else FONT
    return tk.Label(master, text=text, bg=DLG_BG, fg=colour, font=font,
                    wraplength=wrap, justify="left", anchor="w")


def _dlg_entry(master, show=None, width=34):
    return tk.Entry(master, show=show or "", width=width, font=FONT,
                    bg="#ffffff", fg="#1e2a4a", insertbackground="#1e2a4a",
                    relief="flat", highlightthickness=1,
                    highlightbackground="#7f90b5", highlightcolor=ACCENT)


def _dlg_button(master, text, command, *, primary=False):
    if primary:
        return tk.Button(master, text=text, command=command, font=FONT_BOLD,
                         bg=ACCENT, fg=ACCENT_TEXT, activebackground=ACCENT_ACTIVE,
                         activeforeground=ACCENT_TEXT, relief="flat",
                         padx=18, pady=6, cursor="hand2", bd=0)
    return tk.Button(master, text=text, command=command, font=FONT,
                     bg=DLG_BTN, fg=DLG_TXT, activebackground=DLG_BTN_ACTIVE,
                     activeforeground=DLG_TXT, relief="flat",
                     padx=14, pady=6, cursor="hand2", bd=0)


def _dlg_radio(master, text, variable, value):
    # On a light card, not the dark dialog: the classic radio indicator is
    # invisible and unclickable against a dark background, so the choice
    # rows use a light strip where the box renders and clicks normally.
    return tk.Radiobutton(master, text=text, variable=variable, value=value,
                          bg=DLG_CARD, fg=DLG_CARD_TX, selectcolor="#ffffff",
                          activebackground=DLG_CARD_ACTIVE,
                          activeforeground=DLG_CARD_TX, font=FONT, anchor="w",
                          highlightthickness=0, bd=0, padx=10, pady=7)


def _dlg_check(master, text, variable, wrap=470):
    # Same reasoning as _dlg_radio: a light row so the checkbox is visible
    # and clickable rather than lost against the dark dialog.
    return tk.Checkbutton(master, text=text, variable=variable,
                          bg=DLG_CARD, fg=DLG_CARD_TX, selectcolor="#ffffff",
                          activebackground=DLG_CARD_ACTIVE,
                          activeforeground=DLG_CARD_TX, font=FONT, anchor="w",
                          justify="left", wraplength=wrap,
                          highlightthickness=0, bd=0, padx=10, pady=7)


def _show_hide_button(master, *entries):
    """A small 'Show'/'Hide' toggle for password fields, so someone keeping a
    written record can check what they typed before submitting. Styled for the
    dark dialogs. Pass one or more Entry widgets to reveal together."""
    state = {"shown": False}

    def toggle():
        state["shown"] = not state["shown"]
        for e in entries:
            try:
                e.config(show="" if state["shown"] else "\u2022")
            except Exception:
                pass
        btn.config(text="Hide" if state["shown"] else "Show")

    btn = tk.Button(master, text="Show", command=toggle, font=FONT,
                    bg=DLG_BTN, fg=DLG_TXT, activebackground=DLG_BTN_ACTIVE,
                    activeforeground=DLG_TXT, relief="flat", padx=10, pady=2,
                    cursor="hand2", bd=0)
    return btn


def _titled_card(parent, title):
    """A box with a navy header bar and a light body, for the main (light)
    page. Returns (outer, inner): pack/forget `outer` to show/hide the whole
    card; put content in `inner`."""
    outer = tk.Frame(parent, bg=HEADER_BG, bd=0, highlightthickness=0)
    outer.pack(fill="x", pady=(2, 14))
    tk.Label(outer, text=title, bg=HEADER_BG, fg="#ffffff", font=FONT_BOLD,
             anchor="w", padx=12, pady=7).pack(fill="x")
    body = tk.Frame(outer, bg=PANEL)
    body.pack(fill="x", padx=2, pady=(0, 2))   # a thin navy edge around body
    inner = tk.Frame(body, bg=PANEL)
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    return outer, inner


def _card_button(master, text, command):
    """A primary (brass) action button for use inside a light card."""
    return tk.Button(master, text=text, command=command, font=FONT_BOLD,
                     bg=ACCENT, fg=ACCENT_TEXT, activebackground=ACCENT_ACTIVE,
                     activeforeground=ACCENT_TEXT, relief="flat",
                     padx=14, pady=6, cursor="hand2", bd=0)


def _set_enabled(widget, enabled):
    """Enable or disable a tk or ttk widget, tolerating widgets that have no
    state option. Used to gray out controls a signed-in role may not use."""
    try:
        widget.configure(state=("normal" if enabled else "disabled"))
    except Exception:
        pass


_AUDIT_ACTION_LABELS = {
    "enable_multiuser": "Turned on shared access",
    "add_user": "Added user",
    "remove_user": "Removed user",
    "reset_password": "Reset password",
    "change_role": "Changed role",
    "change_own_password": "Changed own password",
    "first_login_password_set": "Set password (first sign-in)",
    "activate": "Reactivated user",
    "deactivate": "Deactivated user",
}


def _audit_action_label(action):
    """A readable label for an audit action code."""
    return _AUDIT_ACTION_LABELS.get(
        action, str(action).replace("_", " ").capitalize())


class _SigninError(Exception):
    """A sign-in failure carrying the message to show inline on the sign-in
    card, so the local and over-the-wire logins report errors the same way."""


class _RemoteSession:
    """A stand-in 'session' for client mode.

    In a local multi-user book the session is a service.Session backed by the
    database. In client mode there is no local database here -- the host holds
    it -- but the rest of the GUI still asks `_session.can(...)` to gray out
    buttons and `_session.username/role` for the header badge. This carries
    the identity and role the HOST reported at login so that same code keeps
    working. It performs no operations itself; every real action goes over the
    wire through the RemoteGateway, where the host enforces the role for real.
    """

    def __init__(self, username, role, host_label=""):
        self.username = username
        self.role = role
        self.host_label = host_label

    def can(self, action):
        return roles.can(self.role, action)


class LedgerApp(tk.Tk):
    """The main application window."""

    def __init__(self):
        super().__init__()
        self.title("Ledger")
        # Open at a generous size that comfortably fits the entry form
        # plus the (coming) help side panel, then maximise so it uses the
        # whole screen -- friendlier for older users, and it gives the
        # help panel room. This geometry is the "restore down" size and
        # the fallback if maximising isn't supported by the platform.
        self.geometry("1180x740")
        self.configure(bg=BG)
        # Minimum keeps the entry form and a docked help panel from ever
        # being squeezed together.
        self.minsize(1000, 600)

        # The database path currently open. None until one is chosen.
        self.db_path = database.DEFAULT_DB_PATH
        self.conn = None
        # The data gateway for the open book: a LocalGateway in ordinary use,
        # or (later) a RemoteGateway when this computer is a client of a host.
        # The tabs perform their work through this, so the same code serves
        # both modes. None until a book is open.
        self.gateway = None
        # Connection mode: "local" (this computer holds the book) or
        # "client" (this computer talks to a host over the network). In client
        # mode `gateway` is a RemoteGateway and `_client` is the live
        # connection; `conn`/`_book_data_key` stay None -- the data lives on
        # the host and is never copied here.
        self.mode = "local"
        # The live network connection to a host when in client mode; None
        # otherwise. Closed on sign-out.
        self._client = None
        # In "host" mode this computer is sharing its books to others. Hosting
        # runs as a SEPARATE background process (so it keeps serving after this
        # window is closed); we track that process here and talk to it as an
        # ordinary client over the loopback. `_host_proc` is the Popen handle if
        # we started it this session; `_host_state` is its recorded
        # pid/port/fingerprint (also recovered from disk on a later launch).
        self._host_proc = None
        self._host_state = None
        self._host_poll_id = None
        # The last set of books that was open here, remembered across a
        # sign-out so the landing page's 'Sign in' button can reopen it.
        self._last_book = None
        # The unlocked data key for the open book (None when the book is not
        # encrypted). Held in memory only, never written to disk.
        self._book_data_key = None
        # Who is signed in to the open book, for role enforcement on
        # multi-user business books (a service.Session, or None for personal
        # and Open books and single-owner business books before login).
        self._session = None
        # True when a brand-new, auto-created book has not yet been offered
        # encryption (first run, or after deleting the last set of books).
        # The encryption step then runs when the user first chooses
        # business/personal and saves their profile.
        self._book_needs_setup = False

        self._build_fonts()
        self._build_style()
        self._build_header()
        self._build_tabs()
        self._build_locked_screen()
        self._build_host_locked_screen()
        self._build_statusbar()

        # Start maximised BEFORE opening the book. Opening a multi-user book
        # shows a modal sign-in dialog, and on some Linux window managers
        # maximising after a modal has grabbed focus doesn't take -- so we
        # maximise the main window first, then the dialog appears over it.
        self._maximize()

        # If a previous run left a host serving these books in the background,
        # adopt it rather than opening the books locally (which would clash with
        # the host that already has them open). The owner can then sign in to
        # use them or stop hosting. We adopt only a host that is genuinely
        # reachable -- a stale or phantom record (e.g. left by a hard kill, or
        # a reused pid) is cleared so it can never trap the app on the wrong
        # book.
        running = None
        try:
            running = hoststate.running_host()
            if running is not None and not hoststate.port_open(
                    running.get("port")):
                hoststate.clear_state()
                running = None
        except Exception:
            running = None
        if running is not None:
            self._adopt_running_host(running)
        elif (self.db_path and os.path.exists(self.db_path)
              and crypto.is_protected(self.db_path)):
            # A protected set of books already exists. Show the universal
            # sign-in screen (branding + the sign-in card) rather than popping
            # the sign-in dialog straight away, so first launch matches every
            # other sign-in/sign-out. 'Sign in' reopens this book.
            self._last_book = self.db_path
            self._back_to_entry("Sign in to open your books.")
        else:
            # Open (and if needed create) the default ledger on startup.
            self._open_database(self.db_path, announce=False)

            # On a brand-new set of books (first run), settle business/personal
            # and encryption up front -- the same step new and replacement
            # books get -- so the profile screen never has to ask again.
            if self._book_needs_setup:
                self._setup_fresh_books(self.db_path)

            # Show the welcome tour for a brand-new set of books.
            self._maybe_welcome()

        # Re-assert the maximised state once the window is fully mapped and any
        # startup dialogs have closed -- belt and braces for window managers
        # that need it applied after mapping.
        self.after(120, self._maximize)

        # Closing the window routes through _on_close, which takes an
        # automatic safety backup if the data has changed since the last
        # one -- so quitting can never silently lose work.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # styling and chrome
    # ------------------------------------------------------------------

    def _build_fonts(self):
        """
        Set up the application fonts so they look right on whatever
        operating system this is -- Linux or Windows.

        tkinter ships with built-in *named fonts* that always resolve to
        the current system's standard fonts: 'TkDefaultFont' for normal
        interface text and 'TkFixedFont' for monospaced text. We build
        our FONT / FONT_BOLD / FONT_TITLE / FONT_MONO on top of those,
        so we never name a font family that might be missing on one
        platform. This replaces the placeholder tuples defined at the
        top of the module.
        """
        global FONT, FONT_BOLD, FONT_TITLE, FONT_MONO, FONT_HEADER, FONT_BIG
        import tkinter.font as tkfont

        # Start from the system's actual default UI and fixed fonts.
        default = tkfont.nametofont("TkDefaultFont")
        fixed = tkfont.nametofont("TkFixedFont")
        family = default.actual("family")
        fixed_family = fixed.actual("family")

        FONT = (family, 10)
        FONT_BOLD = (family, 10, "bold")
        FONT_TITLE = (family, 13, "bold")
        FONT_MONO = (fixed_family, 10)
        FONT_HEADER = (family, 16, "bold")  # the "Ledger" title bar
        FONT_BIG = (family, 18, "bold")     # the About-window title

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), font=FONT,
                        background=BG, foreground=MUTED)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL)],
                  foreground=[("selected", HEADER_BG)])
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, font=FONT)
        style.configure("Panel.TLabel", background=PANEL, font=FONT)
        style.configure("Title.TLabel", background=BG, font=FONT_TITLE)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                        font=FONT)
        style.configure("TButton", font=FONT, padding=6)
        style.configure("Accent.TButton", font=FONT_BOLD,
                        background=ACCENT, foreground=ACCENT_TEXT,
                        bordercolor=ACCENT, focuscolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("active", ACCENT_ACTIVE),
                              ("pressed", ACCENT_ACTIVE)],
                  foreground=[("disabled", "#dddddd")])
        style.configure("TCheckbutton", background=BG, font=FONT)
        style.configure("TEntry", padding=4)
        style.configure("Treeview", font=FONT, rowheight=24,
                        fieldbackground=PANEL, background=PANEL)
        style.configure("Treeview.Heading", font=FONT_BOLD)

    def _build_header(self):
        header = tk.Frame(self, bg=HEADER_BG, height=54)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(header, text="  Ledger", bg=HEADER_BG, fg=ACCENT_TEXT,
                 font=FONT_HEADER).pack(side="left", padx=(6, 0))

        # Right side of header: which business file is open + switch button.
        self.business_label = tk.Label(
            header, text="", bg=HEADER_BG, fg=ACCENT_TEXT, font=FONT)
        self.business_label.pack(side="right", padx=12)

        switch_btn = tk.Button(header, text="Switch books…",
                               command=self._manage_books,
                               font=FONT, relief="flat",
                               bg=HEADER_BTN, fg=ACCENT_TEXT,
                               activebackground=HEADER_BTN_ACTIVE,
                               activeforeground=ACCENT_TEXT, bd=0,
                               padx=10, pady=4, cursor="hand2")
        switch_btn.pack(side="right", padx=4, pady=10)

        about_btn = tk.Button(header, text="About",
                              command=self._show_about,
                              font=FONT, relief="flat",
                              bg=HEADER_BTN, fg=ACCENT_TEXT,
                              activebackground=HEADER_BTN_ACTIVE,
                              activeforeground=ACCENT_TEXT, bd=0,
                              padx=10, pady=4, cursor="hand2")
        about_btn.pack(side="right", padx=4, pady=10)

        # "Pull from QuickBooks..." -- bring in a QuickBooks export file
        # (.IIF / .QBO / .CSV). Shown only once a set of books on THIS
        # computer is open, since the import lands in the open local book;
        # built here, shown/hidden by _refresh_import_button() (mirrors the
        # Sign out button's show/hide).
        self.qb_import_btn = tk.Button(header, text="Pull from QuickBooks\u2026",
                                       command=self._quickbooks_import,
                                       font=FONT, relief="flat",
                                       bg=HEADER_BTN, fg=ACCENT_TEXT,
                                       activebackground=HEADER_BTN_ACTIVE,
                                       activeforeground=ACCENT_TEXT, bd=0,
                                       padx=10, pady=4, cursor="hand2")
        self._qb_import_shown = False

        # "Sign out" -- shown only when signed in to a shared (multi-user)
        # book, so a person can hand the computer to the next user without
        # quitting the program. Built here, shown/hidden by
        # _refresh_signout_button().
        self.signout_btn = tk.Button(header, text="Sign out",
                                     command=self._lock_books,
                                     font=FONT, relief="flat",
                                     bg=HEADER_BTN, fg=ACCENT_TEXT,
                                     activebackground=HEADER_BTN_ACTIVE,
                                     activeforeground=ACCENT_TEXT, bd=0,
                                     padx=10, pady=4, cursor="hand2")
        self._signout_shown = False

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_entry = EntryTab(self.tabs, self)
        self.tab_journal = JournalTab(self.tabs, self)
        self.tab_reports = ReportsTab(self.tabs, self)
        self.tab_reconcile = ReconciliationTab(self.tabs, self)
        self.tab_accounts = AccountsTab(self.tabs, self)
        self.tab_backup = BackupTab(self.tabs, self)
        self.tab_security = SecurityTab(self.tabs, self)
        self.tab_sharing = SharingTab(self.tabs, self)
        self.tab_business = BusinessInfoTab(self.tabs, self)

        self.tabs.add(self.tab_entry, text="Record Entry")
        self.tabs.add(self.tab_journal, text="Journal")
        self.tabs.add(self.tab_reports, text="Reports")
        self.tabs.add(self.tab_reconcile, text="Reconcile")
        self.tabs.add(self.tab_accounts, text="Accounts")
        self.tabs.add(self.tab_backup, text="Backup")
        self.tabs.add(self.tab_security, text="Security")
        self.tabs.add(self.tab_sharing, text="Sharing")
        self.tabs.add(self.tab_business, text="Business Info")

        # When the user switches to a tab, refresh its contents.
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_locked_screen(self):
        """A neutral navy page shown in place of the tabs whenever no book is
        open. It carries the Ledger emblem, wordmark and message on the left;
        the sign-in card (with its own Switch books / Connect to a host
        actions) is opened beside it on the right, so signing in or out always
        lands on one consistent branded page."""
        self.locked_frame = tk.Frame(self, bg=HEADER_BG)
        inner = tk.Frame(self.locked_frame, bg=HEADER_BG)
        inner.place(relx=0.32, rely=0.5, anchor="center")
        self._locked_inner = inner

        # The square emblem (no text), loaded from the file beside the program.
        # The path is handed to Tk with forward slashes so a Windows backslash
        # path is not misread by Tcl (which would show a blank image). A
        # reference is kept on self so the image is not garbage-collected.
        self._locked_logo_img = None
        here = os.path.dirname(os.path.abspath(__file__))
        for fname in ("ledger-icon.png", "ledger-icon.gif"):
            fp = os.path.join(here, fname).replace("\\", "/")
            if not os.path.exists(fp):
                continue
            try:
                self._locked_logo_img = tk.PhotoImage(file=fp)
            except tk.TclError:
                self._locked_logo_img = None
                continue
            break
        if self._locked_logo_img is not None:
            tk.Label(inner, image=self._locked_logo_img,
                     bg=HEADER_BG).pack(pady=(0, 14))

        tk.Label(inner, text="Ledger", bg=HEADER_BG, fg=ACCENT_TEXT,
                 font=FONT_BIG).pack()
        tk.Label(inner, text="Double-entry bookkeeping", bg=HEADER_BG,
                 fg=DLG_DIM, font=FONT).pack(pady=(3, 18))
        self.locked_msg = tk.Label(inner, text="", bg=HEADER_BG, fg=DLG_TXT,
                                   font=FONT_BOLD, justify="center",
                                   wraplength=360)
        self.locked_msg.pack(pady=(0, 16))
        self._locked_attrib = tk.Label(inner, text=about.attribution_line(),
                                       bg=HEADER_BG, fg=DLG_DIM, font=FONT)
        self._locked_attrib.pack(pady=(18, 0))

        # The 3-button card on the right: 'Sign in' (which leads into the
        # username/password card), plus Open books and Connect to a host. Its
        # edge matches the sign-in card so the two read as the same family.
        self._locked_actions = tk.Frame(self.locked_frame, bg=DLG_BG,
                                         highlightthickness=2,
                                         highlightbackground="#6f82a8")
        card = tk.Frame(self._locked_actions, bg=DLG_BG)
        card.pack(padx=42, pady=36)
        tk.Label(card, text="Sign in", bg=DLG_BG, fg=DLG_TXT,
                 font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        tk.Label(card, text="Choose how to continue:", bg=DLG_BG, fg=DLG_DIM,
                 font=("TkDefaultFont", 12), justify="left").pack(
                     anchor="w", pady=(6, 20))
        # 'Sign in' (primary) leads into the username/password card: the books
        # hosted here, the last/default protected books, or the books picker
        # (see _landing_sign_in).
        self.locked_signin_btn = tk.Button(
            card, text="Sign in", command=self._landing_sign_in,
            font=("TkDefaultFont", 14, "bold"), bg=ACCENT, fg=ACCENT_TEXT,
            activebackground=ACCENT_ACTIVE, activeforeground=ACCENT_TEXT,
            relief="flat", padx=22, pady=11, cursor="hand2", bd=0)
        self.locked_signin_btn.pack(fill="x")
        self.locked_action_btn = tk.Button(
            card, text="Open books\u2026", command=self._manage_books,
            font=("TkDefaultFont", 12), bg=DLG_BTN, fg=DLG_TXT,
            activebackground=DLG_BTN_ACTIVE, activeforeground=DLG_TXT,
            relief="flat", padx=18, pady=9, cursor="hand2", bd=0)
        self.locked_action_btn.pack(fill="x", pady=(12, 0))
        self.locked_connect_btn = tk.Button(
            card, text="Connect to a host\u2026",
            command=self._connect_to_host, font=("TkDefaultFont", 12),
            bg=DLG_BTN, fg=DLG_TXT, activebackground=DLG_BTN_ACTIVE,
            activeforeground=DLG_TXT, relief="flat", padx=16, pady=9,
            cursor="hand2", bd=0)
        self.locked_connect_btn.pack(fill="x", pady=(12, 0))
        self._locked_shown = False

    def _landing_sign_in(self):
        """The 3-button card's primary 'Sign in'. Opens the username/password
        card for the right target: the books hosted on this computer, the last/
        default protected books, or -- with nothing remembered -- the books
        picker."""
        if self._host_proc is not None or self._host_state is not None:
            self._host_sign_in()
            return
        for cand in (self._last_book, self.db_path):
            if cand and os.path.exists(cand) and crypto.is_protected(cand):
                self._open_database(cand)
                return
        self._entry_books("Open a set of books, or connect to a host.")

    def _reveal_locked_action(self):
        """Place the 3-button card on the right, beside the branding."""
        self._locked_actions.place(relx=0.62, rely=0.5, anchor="center")

    def _show_locked_screen(self, message, action=True, centered=True):
        """Replace the tabs with the neutral branded page. When `action` is on,
        the 3-button card is shown on the right with the branding on the left.
        When it is off, a username/password card sits there instead, so the
        3-button card is hidden; `centered` then places the branding -- on the
        left beside a right-pinned card, or upper-centre for the personal
        passphrase unlock whose dialog sits centred just below."""
        self.locked_msg.config(text=message)
        if action:
            # The 3-button card: branding on the left, card on the right.
            self._locked_inner.place_configure(relx=0.32, rely=0.5)
            self._reveal_locked_action()
        else:
            # A username/password card will occupy the right; hide the card.
            self._locked_actions.place_forget()
            if centered:
                # Personal unlock: branding upper-centre, dialog centred below.
                self._locked_inner.place_configure(relx=0.5, rely=0.27)
            else:
                # Branding on the left, beside the right-pinned sign-in card.
                self._locked_inner.place_configure(relx=0.32, rely=0.5)
        if not self._locked_shown:
            self.tabs.pack_forget()
            self.locked_frame.pack(fill="both", expand=True, padx=10, pady=10)
            self._locked_shown = True

    def _show_workspace(self):
        """Show the tabs (and hide any locked page) -- a book is open."""
        if self._host_locked_shown:
            self._hide_host_locked_screen()
        if self._locked_shown:
            self.locked_frame.pack_forget()
            self._locked_shown = False
        # Make sure the tabs are actually visible. They are unpacked whenever a
        # locked page is shown -- including the still-hosting screen -- so if
        # they are not currently managed, re-pack them here. Without this,
        # signing in from the still-hosting screen leaves a blank window.
        if not self.tabs.winfo_manager():
            self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_host_locked_screen(self):
        """A branded page shown when the owner signs out on this computer while
        the host keeps running -- so other computers stay connected. From here
        they can sign back in to use the books, or stop hosting."""
        self.host_locked_frame = tk.Frame(self, bg=HEADER_BG)
        inner = tk.Frame(self.host_locked_frame, bg=HEADER_BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        if getattr(self, "_locked_logo_img", None) is not None:
            tk.Label(inner, image=self._locked_logo_img,
                     bg=HEADER_BG).pack(pady=(0, 14))
        tk.Label(inner, text="Ledger", bg=HEADER_BG, fg=ACCENT_TEXT,
                 font=FONT_BIG).pack()
        tk.Label(inner, text="Still hosting these books for other computers",
                 bg=HEADER_BG, fg=DLG_DIM, font=FONT).pack(pady=(3, 16))
        self._host_locked_msg = tk.Label(
            inner, text="", bg=HEADER_BG, fg=DLG_TXT, font=FONT_BOLD,
            justify="center", wraplength=480)
        self._host_locked_msg.pack(pady=(0, 6))
        self._host_locked_count = tk.Label(inner, text="", bg=HEADER_BG,
                                           fg=ACCENT_TEXT, font=FONT_BOLD)
        self._host_locked_count.pack(pady=(0, 18))
        tk.Button(
            inner, text="Sign in to use these books\u2026",
            command=self._host_sign_in, font=FONT_BOLD, bg=ACCENT,
            fg=ACCENT_TEXT, activebackground=ACCENT_ACTIVE,
            activeforeground=ACCENT_TEXT, relief="flat", padx=16, pady=7,
            cursor="hand2", bd=0).pack()
        tk.Button(
            inner, text="Stop hosting", command=self._host_stop_requested,
            font=FONT,
            bg=DLG_BTN, fg=DLG_TXT, activebackground=DLG_BTN_ACTIVE,
            activeforeground=DLG_TXT, relief="flat", padx=14, pady=6,
            cursor="hand2", bd=0).pack(pady=(10, 0))
        self._host_locked_shown = False

    def _show_host_locked_screen(self, message=None):
        """Put the still-hosting page up in place of the tabs. `message` lets
        the caller tailor the explanation (e.g. when adopting a host left
        running by an earlier launch)."""
        self._host_locked_msg.config(text=(message or (
            "You're signed out on this computer. Other computers can still "
            "sign in and work \u2014 the books stay served from here. Sign in "
            "to use them here. Only the owner can stop hosting.")))
        # On this screen we have no authenticated connection, so we cannot ask
        # the host for a live count; just note that it is running.
        self._host_locked_count.config(text="Running in the background")
        self.tabs.pack_forget()
        if self._locked_shown:
            self.locked_frame.pack_forget()
            self._locked_shown = False
        if not self._host_locked_shown:
            self.host_locked_frame.pack(fill="both", expand=True,
                                        padx=10, pady=10)
            self._host_locked_shown = True
        self._refresh_open_badge()

    def _hide_host_locked_screen(self):
        if self._host_locked_shown:
            self.host_locked_frame.pack_forget()
            self._host_locked_shown = False

    def _build_statusbar(self):
        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=FONT,
                               anchor="w", padx=10)
        self.status.pack(fill="x", side="bottom", pady=(0, 4))

    def _maximize(self):
        """Open as large as the screen allows while keeping the title bar
        and window buttons (not borderless full-screen, which would hide
        the close button). Tries the Windows/macOS way, then the Linux
        way, then falls back to sizing to the screen -- so it does
        something sensible everywhere and never errors if a window
        manager doesn't support it."""
        try:
            self.state("zoomed")            # Windows and macOS
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)  # many Linux window managers
            return
        except tk.TclError:
            pass
        try:                                  # last resort: fill the screen
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
            self.geometry(f"{w}x{h}+0+0")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # database handling
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # encryption: setup (new book) and unlock (opening a protected book)
    # ------------------------------------------------------------------
    #
    # A protected book is encrypted at rest: its data file on disk is an
    # encrypted blob, never plaintext, and so are its backups. The live
    # database is held in memory for the session (see database.connect with a
    # data key) and written back, encrypted, on every commit. The passphrase
    # gate, recovery code, and vault file decide and hold the key; the steps
    # below establish that key and then convert the new book to encrypted at
    # rest via _encrypt_open_book_at_rest().

    def _center_dialog(self, win, relx=0.5, rely=None):
        """Place a dialog over the main window. `relx` is where, across the
        free horizontal space, to put it: 0.5 centres it (the default), while
        a larger value such as 0.66 shifts it right -- used by the sign-in
        dialogs so the branding on the locked page stays visible beside it.
        `rely` does the same vertically; None keeps the usual one-third-down
        placement, while 0.5 centres it (to line up with the branding)."""
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        try:
            avail_x = max(self.winfo_width() - w, 0)
            avail_y = max(self.winfo_height() - h, 0)
            px = self.winfo_rootx() + int(avail_x * relx)
            if rely is None:
                py = self.winfo_rooty() + max(avail_y // 3, 0)
            else:
                py = self.winfo_rooty() + int(avail_y * rely)
        except Exception:
            px, py = 220, 160
        win.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _book_count(self):
        """How many sets of books exist on this computer."""
        try:
            return len(glob.glob(os.path.join(paths.data_dir(), "*.db")))
        except Exception:
            return 0

    def _dialog_border(self, win, colour=HEADER_BG):
        """Give a normal (title-barred) dialog a thin navy edge, so its content
        reads as a finished panel rather than a bare slate or grey box. Applied
        when the window is created; for the pinned sign-in cards this is later
        overridden by _make_dialog_static's card edge, so those keep their card
        look. Purely cosmetic -- it adds a border and never moves the layout."""
        try:
            win.configure(highlightbackground=colour, highlightcolor=colour,
                          highlightthickness=2)
        except tk.TclError:
            pass

    def _make_dialog_static(self, win, relx=0.66, rely=0.5):
        """Fix a sign-in dialog in place beside the locked-page branding: no
        title bar (so it cannot be dragged around), a thin edge so it reads as
        a card on the navy page, and firm keyboard focus (needed once the title
        bar is gone). Call after the dialog's contents are built."""
        win.configure(highlightbackground="#6f82a8", highlightcolor="#6f82a8",
                      highlightthickness=2, bd=0)
        # Hide, drop the title bar, then re-show: on several window managers
        # overrideredirect only takes hold when the window is (re)mapped.
        try:
            win.withdraw()
            win.overrideredirect(True)
        except tk.TclError:
            pass
        self._center_dialog(win, relx=relx, rely=rely)
        try:
            win.deiconify()
        except tk.TclError:
            pass
        win.update_idletasks()
        win.lift()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        win.focus_force()

    def _add_switch_books_button(self, parent, win):
        """If more than one set of books exists, add a 'Switch books' button to
        a sign-in dialog so the person can pick a different set without first
        cancelling. It closes the dialog and opens the books manager."""
        if self._book_count() <= 1:
            return

        def switch():
            win.destroy()
            self.after(40, self._manage_books)

        _dlg_button(parent, "Switch books\u2026", switch).pack(
            side="left")

    def _add_connect_host_button(self, parent, win):
        """Add a 'Connect to a host' button to a sign-in dialog, so a person
        can switch from opening books on this computer to connecting to a host
        that holds them -- without having to sign out first. It opens the
        connect window *over* this sign-in dialog, which stays open behind it.
        Cancelling the connect window simply returns to this sign-in; actually
        connecting closes it and moves on to the host."""
        def connect():
            self._connect_to_host(parent_dialog=win)

        _dlg_button(parent, "Connect to a host\u2026", connect).pack(
            side="left", padx=(8, 0))

    def _setup_fresh_books(self, path):
        """Walk a brand-new, blank set of books through its first-time setup:
        choose business or personal, then the encryption step. Used for the
        replacement books created after deleting the last set, so encryption
        is offered there just like when creating a new set."""
        # The blank book already exists and needs a kind, so a choice is
        # required here -- no default, no dismissing without choosing.
        kind = self._choose_book_kind(allow_cancel=False)
        # Record the kind on the books themselves, so the profile knows what
        # this set of books is without asking again. (The name is filled in
        # later on the profile screen; saving kind alone leaves the books
        # 'not yet named', so the user is still guided to the profile tab.)
        try:
            profile.save_profile(self.conn, kind=kind)
        except Exception:
            pass
        # Reflect the choice on the Business Info tab the user will land on.
        try:
            self.tab_business.kind_var.set(kind)
            self.tab_business._apply_kind_labels()
        except Exception:
            pass
        self._setup_protection(path, kind)
        # Handled now, so the first profile save does not ask again.
        self._book_needs_setup = False
        self._refresh_open_badge()

    def _choose_book_kind(self, parent=None, allow_cancel=True):
        """Ask whether a new set of books is for business or personal use, with
        NO silent default -- the person must pick one. Returns 'business' or
        'personal', or (only when allow_cancel) None if they back out. When
        allow_cancel is False the window cannot be dismissed without choosing:
        the X asks them to choose rather than picking a kind for them."""
        owner = parent or self
        win = tk.Toplevel(owner)
        win.title("Business or personal?")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(owner)
        win.resizable(False, False)
        win.grab_set()
        result = {"kind": None}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Business or personal?", title=True).pack(anchor="w")
        _dlg_label(f,
                   "Is this set of books for business or personal use? "
                   "Business books are always encrypted; personal books can "
                   "be either. Please choose one \u2014 there is no default.",
                   dim=True, wrap=430).pack(anchor="w", pady=(4, 16))

        def choose(kind):
            result["kind"] = kind
            win.destroy()

        row = tk.Frame(f, bg=DLG_BG)
        row.pack(fill="x")
        _dlg_button(row, "Business", lambda: choose("business"),
                    primary=True).pack(side="left")
        _dlg_button(row, "Personal", lambda: choose("personal"),
                    primary=True).pack(side="left", padx=(8, 0))

        if allow_cancel:
            def cancel():
                result["kind"] = None
                win.destroy()
            _dlg_button(row, "Cancel", cancel).pack(side="right")
            win.protocol("WM_DELETE_WINDOW", cancel)
        else:
            def must_choose():
                messagebox.showinfo(
                    "Please choose",
                    "Please choose Business or Personal to continue.",
                    parent=win)
            win.protocol("WM_DELETE_WINDOW", must_choose)

        self._center_dialog(win)
        win.focus_force()
        self.wait_window(win)
        return result["kind"]

    def _setup_protection(self, path, kind):
        """Run when a NEW set of books is created. Business books are always
        protected; personal books may be protected or left open. On a
        protected choice this creates the vault (passphrase + recovery code)
        and writes the vault file. Returns 'protected', 'open', or None if
        the user backed out (only possible for personal)."""
        if not crypto.CRYPTO_AVAILABLE:
            messagebox.showinfo(
                "Encryption not available yet",
                "Encryption needs the 'cryptography' library, which isn't "
                "installed on this computer. This set of books will be "
                "created without encryption for now.\n\nTo enable encryption, "
                "install the library (pip install cryptography) and turn "
                "protection on later.")
            return "open"
        win = tk.Toplevel(self)
        win.title("Protect this set of books")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"value": None}

        wrap = tk.Frame(win, bg=DLG_BG)
        wrap.pack(fill="both", expand=True, padx=24, pady=20)

        _dlg_label(wrap, "Encryption", title=True).pack(anchor="w")
        intro = ("Encryption keeps your financial records private. With it "
                 "on, the books and their backups can only be opened with "
                 "your passphrase \u2014 a lost or stolen copy is unreadable.")
        _dlg_label(wrap, intro, dim=True).pack(anchor="w", pady=(4, 14))

        choice = tk.StringVar(value="protected")
        # Personal books may opt out; business books may not.
        if kind != "business":
            _dlg_radio(wrap, "Protected (encrypted) \u2014 recommended",
                       choice, "protected").pack(anchor="w", fill="x")
            _dlg_radio(wrap, "Open (no encryption)",
                       choice, "open").pack(anchor="w", fill="x", pady=(2, 8))
        else:
            _dlg_label(wrap, "Business books are always protected.",
                       title=True).pack(anchor="w", pady=(0, 8))

        # -- protected: passphrase fields --
        prot = tk.Frame(wrap, bg=DLG_BG)
        _dlg_label(prot, "Choose a passphrase:").pack(anchor="w")
        pw1 = _dlg_entry(prot, show="\u2022")
        pw1.pack(anchor="w", ipady=3, pady=(3, 8))
        _dlg_label(prot, "Type it again:").pack(anchor="w")
        pw2 = _dlg_entry(prot, show="\u2022")
        pw2.pack(anchor="w", ipady=3, pady=(3, 4))
        _show_hide_button(prot, pw1, pw2).pack(anchor="w", pady=(0, 8))

        # -- open: the acknowledgement --
        opn = tk.Frame(wrap, bg=DLG_BG)
        ack = tk.BooleanVar(value=False)
        _dlg_check(
            opn,
            ("I understand that my financial records and backups will not be "
             "encrypted, and that anyone who gets access to this computer or "
             "the files will be able to read them. I am choosing to continue "
             "without encryption."), ack).pack(anchor="w", fill="x")

        err = _dlg_label(wrap, "", err=True)

        def refresh_mode(*_):
            prot.pack_forget(); opn.pack_forget(); err.pack_forget()
            if choice.get() == "protected":
                prot.pack(anchor="w", fill="x", pady=(4, 0))
            else:
                opn.pack(anchor="w", fill="x", pady=(4, 0))
        choice.trace_add("write", refresh_mode)
        refresh_mode()

        def proceed():
            err.pack_forget()
            if choice.get() == "open":
                if not ack.get():
                    err.config(text="Please tick the box to confirm, or "
                                    "choose Protected.")
                    err.pack(anchor="w", pady=(8, 0))
                    return
                result["value"] = "open"
                win.destroy()
                return
            # protected
            p1, p2 = pw1.get(), pw2.get()
            if len(p1) < 8:
                err.config(text="Use a passphrase of at least 8 characters.")
                err.pack(anchor="w", pady=(8, 0)); return
            if p1 != p2:
                err.config(text="The two passphrases do not match.")
                err.pack(anchor="w", pady=(8, 0)); return
            vault, recovery_code = crypto.create_vault(p1)
            if not self._show_recovery_code(recovery_code, parent=win,
                                            mandatory=(kind == "business")):
                return  # they didn't confirm saving it; stay on this screen
            crypto.save_vault(path, vault)
            self._book_data_key = crypto.unlock(vault, p1)
            # Now that the key exists, encrypt the new book's data file at
            # rest. If that fails, undo the vault so the book stays a readable
            # Open book rather than a plaintext file that merely looks
            # protected (which would lock the user out on the next open).
            try:
                self._encrypt_open_book_at_rest()
            except Exception as e:
                try:
                    crypto.delete_vault(path)
                except Exception:
                    pass
                self._book_data_key = None
                messagebox.showerror(
                    "Could not finish protecting this book",
                    "The passphrase was set, but the data file could not be "
                    "encrypted:\n\n{}\n\nYour data is safe and unchanged; the "
                    "book has been left unencrypted. Please try again.".format(
                        e), parent=win)
                return
            result["value"] = "protected"
            win.destroy()

        def cancel():
            if kind == "business":
                messagebox.showinfo(
                    "Business books must be protected",
                    "A business set of books is always encrypted. Please "
                    "set a passphrase to continue.", parent=win)
                return
            result["value"] = None
            win.destroy()

        btns = tk.Frame(wrap, bg=DLG_BG)
        btns.pack(anchor="e", pady=(18, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Continue", proceed, primary=True).pack(side="right")

        # The window-close (X) button must not be an escape hatch: route it
        # through the same cancel logic, which refuses to close a business
        # book without a passphrase.
        win.protocol("WM_DELETE_WINDOW", cancel)

        pw1.focus_set()
        self._center_dialog(win)
        self.wait_window(win)
        return result["value"]

    def _protect_window_from_capture(self, win):
        """Best-effort: ask the operating system to keep `win` out of
        screenshots and screen recordings. Used for the recovery-code screen,
        which shows a secret.

        This works on Windows 10 (version 2004) and later, where the window
        appears BLANK in screenshots, the Snipping Tool, screen recorders and
        screen-share. It is a no-op on Linux/X11, where any program can read
        the screen and an application cannot prevent it -- and NOTHING can stop
        a photo taken with a phone camera. Returns True if applied. Never
        raises (a failure just means the window is captured normally).
        """
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes
            win.update_idletasks()
            user32 = ctypes.windll.user32
            user32.GetAncestor.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
            user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND,
                                                        wintypes.DWORD]
            GA_ROOT = 2
            hwnd = user32.GetAncestor(wintypes.HWND(win.winfo_id()), GA_ROOT)
            WDA_EXCLUDEFROMCAPTURE = 0x00000011   # Windows 10 2004+
            WDA_MONITOR = 0x00000001              # older fallback
            if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                return True
            return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR))
        except Exception:
            return False

    def _show_recovery_code(self, code, parent=None, mandatory=False):
        """Show the recovery code once, with the warning that nothing else
        holds it, and require the owner to confirm they have saved it.
        Returns True only if they confirm. When `mandatory` is set (a business
        book being created, where encryption cannot be skipped), the window
        cannot simply be closed with the X -- doing so runs the same 'have you
        saved it?' check rather than quietly backing out."""
        win = tk.Toplevel(parent or self)
        win.title("Save your recovery code")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(parent or self)
        win.resizable(False, False)
        win.grab_set()
        # Keep this secret out of screenshots/recordings where the OS allows
        # it (Windows). On Linux this can't be enforced, and no software can
        # stop a phone camera -- hence the explicit warning below too.
        self._protect_window_from_capture(win)
        confirmed = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Your recovery code", title=True).pack(anchor="w")
        _dlg_label(f,
                   ("This is the ONLY way back in if you forget your "
                    "passphrase. Write it down on paper and keep it somewhere "
                    "safe, like a safe or lockbox. Do NOT save it on this "
                    "computer, and do not take a screenshot or a photo of "
                    "it."), dim=True).pack(anchor="w", pady=(4, 10))

        box = tk.Text(f, height=2, width=42, font=FONT_MONO, wrap="word",
                      relief="flat", bd=0, bg="#ffffff", fg="#1e2a4a",
                      highlightthickness=1, highlightbackground="#7f90b5")
        box.insert("1.0", code)
        box.config(state="disabled")
        box.pack(anchor="w", pady=(0, 10), ipady=4)

        _dlg_label(f,
                   ("No other part of Ledger stores this code. If you lose "
                    "both your passphrase AND this code, the data cannot be "
                    "recovered by anyone, including " + about.builder_name()
                    + "."),
                   fg="#ffcf99").pack(anchor="w", pady=(0, 10))

        saved = tk.BooleanVar(value=False)
        _dlg_check(f, "I have written down or printed this code and stored "
                      "it safely.", saved).pack(anchor="w", fill="x")

        err = _dlg_label(f, "", err=True)

        def done():
            if not saved.get():
                err.config(text="Please confirm you have saved the code.")
                err.pack(anchor="w", pady=(6, 0)); return
            confirmed["ok"] = True
            win.destroy()

        def print_it():
            # Build a small, clear sheet and print it. We deliberately do NOT
            # offer "copy", because the clipboard would keep the secret on the
            # computer (and in clipboard history) -- the opposite of the advice
            # on this screen. Printing sends it to paper without a lasting copy
            # on disk (see the printing module).
            from datetime import datetime
            sheet = (
                "Ledger \u2014 Recovery Code\n"
                "Generated: " + datetime.now().strftime("%Y-%m-%d") + "\n\n"
                + code + "\n\n"
                "Keep this somewhere safe, such as a locked drawer or a safe "
                "\u2014 NOT on this computer.\n"
                "It is the only way back in if you forget your passphrase. If "
                "you lose both your passphrase and this code, no one can "
                "recover the data.\n\n"
                + about.builder_name() + "\n")
            ok, message = printing.print_text(
                sheet,
                schedule_delete=lambda fn, secs: self.after(
                    int(secs * 1000), fn))
            if ok:
                self.set_status("Recovery code sent to the printer.",
                                kind="ok")
            else:
                messagebox.showinfo(
                    "Could not print",
                    "The recovery code could not be printed:\n\n" + message +
                    "\n\nPlease write it down by hand and keep it somewhere "
                    "safe.", parent=win)

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(14, 0))
        _dlg_button(btns, "Print", print_it).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Done", done, primary=True).pack(side="right")

        def on_close():
            # For a business book, encryption is mandatory: the X must not be a
            # quiet way to skip saving the recovery code, so it runs the same
            # check as Done. Elsewhere (optional protection) the X backs out.
            if mandatory:
                done()
            else:
                confirmed["ok"] = False
                win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        self._center_dialog(win)
        self.wait_window(win)
        return confirmed["ok"]

    def _encrypt_open_book_at_rest(self):
        """Convert the currently-open, just-created PLAINTEXT book into an
        encrypted-at-rest book, using the key just established.

        Closes the plaintext connection, encrypts the file in place (which
        verifies the encrypted copy decrypts back to the original BEFORE
        replacing it), and reopens the book as an in-memory encrypted
        connection. On any failure the file is left readable and a working
        connection is restored, so the caller can safely fall back to leaving
        the book Open.
        """
        key = self._book_data_key
        path = self.db_path
        if key is None:
            raise RuntimeError("No data key is set for this book.")
        # Make sure the plaintext file reflects all committed data, then close
        # the plaintext connection so the file can be replaced.
        try:
            self.conn.commit()
        except Exception:
            pass
        self.conn.close()
        try:
            database.encrypt_file_in_place(path, key)
        finally:
            # Whatever happened, reopen a working connection so the app is
            # never left without one. If the file is now encrypted, open it
            # with the key; if encryption failed and the file is still
            # plaintext, reopen it as an ordinary Open book.
            if crypto.is_encrypted_db_file(path):
                self.conn = database.connect(path, data_key=key)
            else:
                self.conn = database.connect(path)

    def _protect_existing_book(self):
        """Turn encryption ON for the book that is open now (currently an Open
        book). Asks for a passphrase, shows the recovery code once, then
        encrypts the data file -- and from now on its backups -- at rest.

        Returns True if the book is now protected. Reuses the same verified
        steps as first-time setup, including the rollback that leaves the book
        readable and Open if the encryption step ever fails.
        """
        path = self.db_path
        if not path or crypto.is_protected(path):
            return False
        if not crypto.CRYPTO_AVAILABLE:
            messagebox.showinfo(
                "Encryption not available",
                "Encryption needs the 'cryptography' library, which isn't "
                "installed on this computer.\n\nInstall it with:  "
                "pip install cryptography")
            return False

        win = tk.Toplevel(self)
        win.title("Turn on protection")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Turn on protection", title=True).pack(anchor="w")
        _dlg_label(
            f,
            ("This encrypts this set of books and its future backups. From now "
             "on it can only be opened with the passphrase you choose here, or "
             "with the recovery code shown next. Keep both safe: if you lose "
             "both, no one can recover the data. Backups you have already made "
             "are not changed -- only new ones will be encrypted."),
            dim=True, wrap=440).pack(anchor="w", pady=(4, 12))

        _dlg_label(f, "Choose a passphrase:").pack(anchor="w")
        pw1 = _dlg_entry(f, show="\u2022")
        pw1.pack(anchor="w", ipady=3, pady=(3, 8))
        _dlg_label(f, "Type it again:").pack(anchor="w")
        pw2 = _dlg_entry(f, show="\u2022")
        pw2.pack(anchor="w", ipady=3, pady=(3, 4))
        _show_hide_button(f, pw1, pw2).pack(anchor="w", pady=(0, 8))
        err = _dlg_label(f, "", err=True, wrap=440)

        def proceed():
            err.pack_forget()
            p1, p2 = pw1.get(), pw2.get()
            if len(p1) < 8:
                err.config(text="Use a passphrase of at least 8 characters.")
                err.pack(anchor="w", pady=(8, 0)); return
            if p1 != p2:
                err.config(text="The two passphrases do not match.")
                err.pack(anchor="w", pady=(8, 0)); return
            vault, recovery_code = crypto.create_vault(p1)
            if not self._show_recovery_code(recovery_code, parent=win):
                return  # didn't confirm saving it; stay on this screen
            crypto.save_vault(path, vault)
            self._book_data_key = crypto.unlock(vault, p1)
            try:
                self._encrypt_open_book_at_rest()
            except Exception as e:
                try:
                    crypto.delete_vault(path)
                except Exception:
                    pass
                self._book_data_key = None
                messagebox.showerror(
                    "Could not protect this book",
                    "The data file could not be encrypted:\n\n{}\n\nYour data "
                    "is safe and unchanged; the book is still Open. Please try "
                    "again.".format(e), parent=win)
                return
            result["ok"] = True
            win.destroy()

        def cancel():
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Continue", proceed, primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        pw1.focus_set()
        self._center_dialog(win)
        self.wait_window(win)

        if result["ok"]:
            self._refresh_open_badge()
            self.set_status("This set of books is now Protected.", kind="ok")
        return result["ok"]

    def _unprotect_existing_book(self):
        """Turn encryption OFF for the book open now. Only personal books may
        do this; business books are always protected. Returns True if the book
        is now Open.

        Safety: the data file is decrypted back to a plaintext database FIRST,
        and only then is the vault removed -- so an interruption can never
        leave an encrypted file with no way in. (_open_database also cleans up
        a stray vault beside a plaintext file, closing even that tiny window.)
        """
        path = self.db_path
        if not path or not crypto.is_protected(path):
            return False
        if self._book_data_key is None:
            messagebox.showerror(
                "Cannot turn off protection",
                "This book is protected but not unlocked, so protection can't "
                "be removed right now.")
            return False
        try:
            kind = profile.get_kind(self.conn)
        except Exception:
            kind = "business"
        if kind == "business":
            messagebox.showinfo(
                "Business books stay protected",
                "A business set of books is always encrypted; this keeps your "
                "financial records private and cannot be turned off.")
            return False

        win = tk.Toplevel(self)
        win.title("Turn off protection")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Turn off protection", title=True).pack(anchor="w")
        _dlg_label(
            f,
            ("This removes encryption from this set of books. The data file "
             "and any new backups will be stored as plain, unencrypted files. "
             "Encrypted backups you already made are left as they are."),
            dim=True, wrap=440).pack(anchor="w", pady=(4, 10))

        ack = tk.BooleanVar(value=False)
        _dlg_check(
            f,
            ("I understand that my financial records and new backups will no "
             "longer be encrypted, and that anyone who gets access to this "
             "computer or the files will be able to read them."),
            ack).pack(anchor="w", fill="x")
        err = _dlg_label(f, "", err=True, wrap=440)

        def proceed():
            err.pack_forget()
            if not ack.get():
                err.config(text="Please tick the box to confirm, or Cancel.")
                err.pack(anchor="w", pady=(8, 0)); return
            key = self._book_data_key
            try:
                self.conn.commit()
            except Exception:
                pass
            self.conn.close()
            try:
                database.decrypt_file_in_place(path, key)
            except Exception as e:
                # Couldn't decrypt: reopen still-encrypted, protection intact.
                self.conn = database.connect(path, data_key=key)
                messagebox.showerror(
                    "Could not turn off protection",
                    "The data file could not be decrypted:\n\n{}\n\nNothing "
                    "was changed; the book is still Protected.".format(e),
                    parent=win)
                return
            # The plaintext file is now in place; remove the vault and reopen
            # as an Open book. (Order matters: file first, vault second.)
            try:
                crypto.delete_vault(path)
            except Exception:
                pass
            self._book_data_key = None
            self.conn = database.connect(path)
            result["ok"] = True
            win.destroy()

        def cancel():
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Turn off protection", proceed,
                    primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        self._center_dialog(win)
        self.wait_window(win)

        if result["ok"]:
            self._refresh_open_badge()
            self.set_status("This set of books is now Open (not encrypted).",
                            kind="ok")
        return result["ok"]

    def _can(self, action):
        """Whether the signed-in user may do `action`. With no multi-user
        session (personal books, Open books, and single-owner business books)
        everything is allowed, so nothing changes for those."""
        sess = self._session
        return True if sess is None else sess.can(action)

    def _session_badge(self):
        """A short 'signed in: name (Role)' tag for the header, shown for
        shared (multi-user) books and for client connections to a host."""
        sess = self._session
        if sess is None or not getattr(sess, "username", None):
            return ""
        if self.mode in ("client", "host"):
            return "    signed in: %s (%s)" % (sess.username,
                                               roles.label(sess.role))
        try:
            if not users.multiuser_enabled(self.conn):
                return ""
        except Exception:
            return ""
        return "    signed in: %s (%s)" % (sess.username,
                                           roles.label(sess.role))

    def _establish_session(self, path, data_key, login_username):
        """Decide who is acting on the freshly opened book, for role
        enforcement. Personal and Open books have no session. A multi-user
        business book uses the signed-in user's role; a single-owner business
        book treats the person at the keyboard as the owner."""
        try:
            kind = profile.get_kind(self.conn)
        except Exception:
            kind = ""
        if data_key is None or kind != "business":
            self._session = None
            return
        vault = None
        try:
            vault = crypto.load_vault(path)
        except Exception:
            vault = None
        if login_username and users.multiuser_enabled(self.conn):
            user = users.get_user(self.conn, login_username)
            # An unknown user (should not happen) falls back to the least
            # privilege, never more.
            role = user["role"] if user else roles.STAFF
            self._session = service.Session(
                self.conn, login_username, role,
                vault=vault, data_key=data_key, db_path=path)
        else:
            # Single-owner business book, or unlocked via the owner's recovery
            # code: the person here is the owner.
            self._session = service.Session(
                self.conn, "owner", roles.OWNER,
                vault=vault, data_key=data_key, db_path=path)

        # Back-fill the owner's username into the vault so the next sign-in can
        # pre-fill it. This brings older shared books (made before this was
        # recorded) up to date the first time they are opened.
        if (vault is not None and users.multiuser_enabled(self.conn)
                and not vault.get("owner_username")):
            owner = service.find_owner_username(self.conn)
            if owner:
                vault["owner_username"] = owner
                try:
                    crypto.save_vault(path, vault)
                except Exception:
                    pass

    def _build_local_gateway(self):
        """Construct the LocalGateway for the open book. Carries the signed-in
        username/role and the vault/key (so user administration can run), all
        drawn from the current session when there is one."""
        sess = self._session
        username = getattr(sess, "username", None) if sess else None
        role = getattr(sess, "role", None) if sess else None
        vault = getattr(sess, "vault", None) if sess else None
        self.gateway = gateway.LocalGateway(
            self.conn, username=username, role=role, vault=vault,
            data_key=self._book_data_key, db_path=self.db_path)
        self.mode = "local"

    def _refresh_signout_button(self):
        """Show a header button to put the open book down without quitting. It
        reads 'Sign out' for every kind of book, matching the 'Sign out of
        these books?' confirmation. Hidden when no book is open -- and, while
        hosting, hidden once signed out locally (the host keeps running)."""
        # Keep the QuickBooks import button in step with the same book-open
        # transitions (this method is already called everywhere those happen),
        # so its visibility never has to be wired at every call site.
        self._refresh_import_button()
        if self.mode == "host":
            show = self._session is not None
        elif self.mode == "client":
            show = True
        else:
            show = self.conn is not None
        if not show:
            if self._signout_shown:
                self.signout_btn.pack_forget()
                self._signout_shown = False
            return
        self.signout_btn.config(text="Sign out")
        if not self._signout_shown:
            self.signout_btn.pack(side="right", padx=4, pady=10)
            self._signout_shown = True

    def _refresh_import_button(self):
        """Show the header 'Pull from QuickBooks...' button only when a set of
        books on THIS computer is open (local mode, connected). Hidden on the
        locked/sign-in screens and when connected to a host -- in those states
        a file import on this computer has no open local book to land in."""
        show = (self.mode == "local" and self.conn is not None)
        if not show:
            if self._qb_import_shown:
                self.qb_import_btn.pack_forget()
                self._qb_import_shown = False
            return
        if not self._qb_import_shown:
            self.qb_import_btn.pack(side="right", padx=4, pady=10)
            self._qb_import_shown = True

    def _lock_open_book(self, show_locked=True):
        """Close and lock the open book: drop the connection, data key,
        session and gateway from memory. The encrypted file on disk is left
        exactly as it was -- this only locks the running program. If this
        computer was a client of a host, the network connection is closed too.

        `show_locked` paints the neutral locked page afterwards. Callers that
        immediately re-open the same book (so its own sign-in page is painted
        once, at the right spot) pass False -- otherwise a placeholder page
        flashes at a different position first, which is what made the branding
        appear to jump on sign-out.
        """
        self._close_client_if_any()
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None
        self.gateway = None
        self._session = None
        self._book_data_key = None
        self.mode = "local"
        self._refresh_signout_button()
        if show_locked:
            try:
                self.refresh_all()
            except Exception:
                pass
            self._back_to_entry(
                "These books are locked. Sign in to continue.")

    def _confirm_blue(self, title, message, ok_label="OK"):
        """A small confirmation dialog in the same dialog-blue as the program's
        other windows (rather than the grey system pop-up). Returns True if the
        person confirms."""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        result = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, message, title=True).pack(anchor="w")

        def ok():
            result["ok"] = True
            win.destroy()

        def cancel():
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(20, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, ok_label, ok, primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        win.grab_set()
        self._center_dialog(win)
        win.focus_force()
        self.wait_window(win)
        return result["ok"]

    def _lock_books(self):
        """Put the open book down without leaving the program. For a shared
        book this signs the current user out; for a protected personal or
        single-owner book it locks it (the passphrase is needed to open it
        again); for an unencrypted book it simply closes it. In every case the
        book's data and key are dropped from memory; the file on disk is left
        as it is."""
        if self.mode == "client":
            if not self._confirm_blue("Sign out", "Disconnect from the host?",
                                      ok_label="Disconnect"):
                return
            self._disconnect_client()
            self.business_label.config(text="No books open")
            self.set_status("Disconnected from the host.", kind="info")
            # All sign-outs land on the same branded entry screen. A client had
            # no local book open, so there is nothing to reopen -- its 'Sign in'
            # falls through to the books picker; 'Connect to a host' reconnects.
            self._last_book = None
            self._back_to_entry(
                "Signed out. Sign in to open books on this computer, or "
                "connect to a host.")
            return
        if self.mode == "host":
            if not self._confirm_blue(
                    "Sign out",
                    "Sign out of your account on this computer?\n\nHosting "
                    "stays on, so other computers stay connected and can keep "
                    "working. You'll return to the start page \u2014 from there "
                    "you can open other books, connect to the hosted books, or "
                    "stop hosting from the Sharing tab.", ok_label="Sign out"):
                return
            self._host_lock_local()
            return
        if self.conn is None:
            return
        path = self.db_path

        if not self._confirm_blue("Sign out", "Sign out of these books?",
                                  ok_label="Sign out"):
            return

        # All sign-outs land on the same branded entry screen. Remember this
        # book so the screen's 'Sign in' button reopens it directly -- a login
        # popup for a protected book, straight in for an unencrypted one. We do
        # not reopen here, so the screen looks identical to every other
        # sign-out (one extra click to sign back in, by design).
        self._last_book = path if (path and os.path.exists(path)) else None
        self._lock_open_book(show_locked=False)
        self.business_label.config(text="No books open")
        self._back_to_entry(
            "Signed out. Sign in to open your books again, or connect to a "
            "host.")
        self.set_status("Signed out.", kind="info")

    # ------------------------------------------------------------------
    # client mode: connecting to another computer that hosts the books
    # ------------------------------------------------------------------
    #
    # The networking underneath (TLS, certificate pinning, login tokens, and
    # the per-role enforcement on the host) is built in hostnet.py/host.py.
    # The methods below are the GUI on top of it: type the host's address,
    # confirm its security fingerprint the first time (trust-on-first-use,
    # like SSH), sign in over the wire, then run the normal workspace with a
    # RemoteGateway so every tab's work is carried out on the host.

    def _close_client_if_any(self):
        """Log out and close the network connection if one is open. Safe to
        call when there is none."""
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass

    def _disconnect_client(self):
        """Leave client mode entirely: close the connection and return to a
        clean, no-book state."""
        self._close_client_if_any()
        self.gateway = None
        self._session = None
        self.mode = "local"
        self.conn = None
        self._book_data_key = None
        self.db_path = None
        self._refresh_signout_button()
        try:
            self.refresh_all()
        except Exception:
            pass

    def _back_to_entry(self, message="Sign in or connect to continue."):
        """The branded entry page with the 3-button card (Sign in / Open books
        / Connect to a host). Every sign-out, cancelled connection or failure
        lands here; 'Sign in' then opens the username/password card. This page
        always carries its own actions, so it is never a dead end."""
        self._show_locked_screen(message, action=True, centered=True)

    def _entry_books(self, message="Open a set of books to continue."):
        """Open the books manager over the branded page -- the explicit 'Open
        books' path and the fallback when there is nothing to sign in to."""
        self._show_locked_screen(message, action=True, centered=True)
        self.after(40, self._manage_books)

    def _connect_to_host(self, parent_dialog=None):
        """Connect to a host. The local network is searched automatically and
        any hosts found are offered first; an address can also be typed by
        hand as a fallback. Either way leads into the same trust-and-sign-in
        path.

        When opened from a sign-in dialog (`parent_dialog`), this window sits
        *over* that dialog, which stays open behind it: cancelling returns
        straight to the sign-in with no page change, and only an actual
        connection closes it. Opened from the locked entry page (no parent),
        cancelling just closes back to that page."""
        last_host, last_port = clientconf.last_connection()
        win = tk.Toplevel(self)
        win.title("Connect to a host")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(parent_dialog or self)
        win.resizable(False, False)

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Connect to a host", title=True).pack(anchor="w")
        _dlg_label(f, "Pick a host found on your network, or enter its "
                      "address below. You'll then sign in with your username "
                      "and password.", dim=True, wrap=460).pack(
                          anchor="w", pady=(4, 12))

        # --- found hosts on the network (the primary, default path) ---
        found_status = _dlg_label(f, "Searching the network\u2026", dim=True,
                                  wrap=460)
        found_status.pack(anchor="w")
        list_frame = tk.Frame(f, bg=DLG_BG)
        list_frame.pack(fill="x", pady=(6, 4))
        again_btn = _dlg_button(f, "Search again", lambda: start_search())
        again_btn.pack(anchor="w", pady=(2, 0))

        # --- manual address entry (the fallback) ---
        tk.Frame(f, bg="#4a5d85", height=1).pack(fill="x", pady=(14, 10))
        _dlg_label(f, "Or enter the address manually:", dim=True).pack(
            anchor="w")
        row = tk.Frame(f, bg=DLG_BG)
        row.pack(anchor="w", pady=(6, 0))
        _dlg_label(row, "Address:").pack(side="left")
        host_entry = _dlg_entry(row, width=20)
        host_entry.pack(side="left", padx=(6, 10), ipady=3)
        _dlg_label(row, "Port:").pack(side="left")
        port_entry = _dlg_entry(row, width=8)
        port_entry.pack(side="left", padx=(6, 0), ipady=3)
        if last_host:
            host_entry.insert(0, last_host)
        port_entry.insert(0, str(last_port or hostnet.DEFAULT_PORT))

        err = _dlg_label(f, "", err=True, wrap=460)
        err.pack(anchor="w", pady=(8, 0))

        state = {"hosts": None, "error": None, "done": False, "gen": 0}

        def launch(host, port):
            # Move on to the connection. If we were layered over a sign-in
            # dialog, close it now -- and suppress the locked page it would
            # otherwise repaint, since client mode is about to take the screen.
            if parent_dialog is not None and parent_dialog.winfo_exists():
                self._suppress_locked_repaint = True
                parent_dialog.destroy()
            self.after(30, lambda: self._begin_client_connection(host, port))

        def do_connect(_e=None):
            host = host_entry.get().strip()
            try:
                port = int(port_entry.get().strip())
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                err.config(text="Enter a valid port number (1-65535).")
                port_entry.focus_set()
                return
            if not host:
                err.config(text="Enter the host address.")
                host_entry.focus_set()
                return
            win.destroy()
            launch(host, port)

        def choose(h):
            win.destroy()
            launch(h["address"], h["port"])

        def render():
            again_btn.config(state="normal")
            if state["error"] is not None:
                found_status.config(text="Couldn't search the network \u2014 "
                                         "enter the address below instead.")
                return
            hosts = state["hosts"] or []
            if not hosts:
                found_status.config(text="No hosts found. Make sure the host "
                                         "is running, or enter its address "
                                         "below.")
                return
            found_status.config(text="Hosts found on your network "
                                     "(click one to connect):")
            for h in hosts:
                label = "%s \u2014 %s:%d" % (h["name"], h["address"],
                                             h["port"])
                _dlg_button(list_frame, label,
                            lambda hh=h: choose(hh)).pack(
                                anchor="w", fill="x", pady=(0, 6))

        def poll(gen):
            if not win.winfo_exists() or gen != state["gen"]:
                return
            if not state["done"]:
                win.after(150, lambda: poll(gen))
                return
            render()

        def start_search():
            state["gen"] += 1
            gen = state["gen"]
            state["done"] = False
            state["hosts"] = None
            state["error"] = None
            found_status.config(text="Searching the network\u2026")
            for child in list_frame.winfo_children():
                child.destroy()
            again_btn.config(state="disabled")

            def worker():
                try:
                    hosts = discovery.discover_hosts(timeout=1.5)
                except Exception as e:                 # network errors, etc.
                    if gen == state["gen"]:
                        state["error"] = str(e)
                else:
                    if gen == state["gen"]:
                        state["hosts"] = hosts
                finally:
                    if gen == state["gen"]:
                        state["done"] = True

            threading.Thread(target=worker, name="ledger-discover",
                             daemon=True).start()
            win.after(150, lambda: poll(gen))

        host_entry.bind("<Return>", lambda _e: port_entry.focus_set())
        port_entry.bind("<Return>", do_connect)

        def cancel():
            win.destroy()
            if parent_dialog is not None and parent_dialog.winfo_exists():
                # Return to the sign-in dialog still open behind us -- no page
                # change. Restore its modal grab and focus.
                try:
                    parent_dialog.grab_set()
                    parent_dialog.lift()
                    parent_dialog.focus_force()
                except Exception:
                    pass

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Connect", do_connect,
                    primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        # Make it a borderless 'static' card like the sign-in dialogs, so it
        # sits in the same top layer and shows ABOVE the sign-in dialog it was
        # opened over (a normal window would render behind that borderless
        # dialog). _make_dialog_static handles centring, grab, lift and focus.
        self._make_dialog_static(win, relx=0.5, rely=0.5)
        start_search()


    def _begin_client_connection(self, host, port):
        """Step 2: open the connection, handling first-time fingerprint trust
        and a changed-certificate warning, then move on to signing in."""
        pin = clientconf.get_pin(host, port)
        client = hostnet.HostClient(host, port, pinned_fingerprint=pin)
        try:
            fp = client.connect()
        except hostnet.HostCertMismatch:
            client.close()
            if not self._warn_cert_mismatch(host, port):
                self._back_to_entry()
                return
            # The person chose to trust the new certificate: drop the old pin
            # and connect again without pinning, then re-pin what we see.
            clientconf.forget_host(host, port)
            client = hostnet.HostClient(host, port, pinned_fingerprint=None)
            try:
                fp = client.connect()
            except hostnet.HostConnectionError as e:
                client.close()
                self._client_error(host, port, str(e))
                return
            clientconf.remember_host(host, port, fp)
        except hostnet.HostConnectionError as e:
            client.close()
            self._client_error(host, port, str(e))
            return

        if pin is None:
            # First time we have seen this host: confirm its fingerprint.
            if not self._confirm_first_fingerprint(host, port, fp):
                client.close()
                self._back_to_entry()
                return
            clientconf.remember_host(host, port, fp)

        clientconf.set_last_connection(host, port)

        result = self._login_over_wire(client, host)
        if result is None:
            try:
                client.logout()
            except Exception:
                pass
            client.close()
            self._back_to_entry()
            return
        self._enter_client_mode(client, result, host, port)

    def _client_error(self, host, port, message):
        messagebox.showerror(
            "Could not connect",
            f"Could not connect to {host}:{port}.\n\n{message}")
        self._back_to_entry()

    def _confirm_first_fingerprint(self, host, port, fp):
        """First-contact trust: show the host's security fingerprint and ask
        the person to confirm it matches what the host displays. Returns True
        to trust and continue."""
        pretty = hostnet.pretty_fingerprint(fp or "")
        win = tk.Toplevel(self)
        win.title("Confirm the host")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        result = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Is this the right computer?", title=True).pack(
            anchor="w")
        _dlg_label(f, f"This is the first time connecting to \u201c{host}\u201d. "
                      "Check that the security fingerprint below matches the "
                      "one shown on the host. Only continue if they match \u2014 "
                      "this is what protects you against connecting to an "
                      "impostor.", dim=True, wrap=440).pack(anchor="w",
                                                            pady=(4, 12))
        tk.Label(f, text=pretty, bg="#1e2a4a", fg="#ffffff",
                 font=("TkFixedFont", 11), padx=12, pady=10,
                 wraplength=440, justify="left").pack(anchor="w", fill="x")

        def trust():
            result["ok"] = True
            win.destroy()

        def cancel():
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(18, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Trust and continue", trust,
                    primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        win.grab_set()
        self._center_dialog(win)
        win.focus_force()
        self.wait_window(win)
        return result["ok"]

    def _warn_cert_mismatch(self, host, port):
        """The host presented a different certificate than the one pinned.
        Warn strongly. Returns True only if the person deliberately chooses to
        trust the new certificate (e.g. the host was legitimately
        reinstalled)."""
        win = tk.Toplevel(self)
        win.title("Security certificate changed")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        result = {"ok": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Warning: the host's certificate has changed",
                   title=True, err=True).pack(anchor="w")
        _dlg_label(f, f"The security fingerprint for \u201c{host}\u201d is not "
                      "the one trusted before. This can happen if the host was "
                      "reinstalled or its certificate was renewed \u2014 but it "
                      "can also mean something is impersonating it. If you are "
                      "not certain why it changed, do not continue, and check "
                      "with whoever runs the host.", dim=True,
                   wrap=440).pack(anchor="w", pady=(6, 12))

        def trust_new():
            result["ok"] = True
            win.destroy()

        def cancel():
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(8, 0))
        _dlg_button(btns, "Cancel (recommended)", cancel).pack(
            side="right", padx=(8, 0))
        _dlg_button(btns, "Trust the new certificate", trust_new).pack(
            side="right")
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        win.grab_set()
        self._center_dialog(win)
        win.focus_force()
        self.wait_window(win)
        return result["ok"]

    def _signin_card(self, title, subtitle, do_login, do_recovery=None):
        """The shared username/password sign-in card, used by both the local
        multi-user login and the over-the-wire host login so the two are
        identical. `do_login(username, password)` returns the success result
        (any value) or raises _SigninError(message) to show an inline error.

        When `do_recovery` is given, a 'Use a security code' caret appears
        below Show; opening it reveals a Security code field, and signing in
        with a code there calls do_recovery(code) -- which returns a success
        result or raises _SigninError -- to unlock the books with the recovery
        code instead of a password. Returns the success result, or None if
        cancelled."""
        win = tk.Toplevel(self)
        win.title("Sign in")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        result = {"data": None}
        rec = {"open": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, title, title=True).pack(anchor="w")
        _dlg_label(f, subtitle, dim=True, wrap=420).pack(
            anchor="w", pady=(4, 10))

        _dlg_label(f, "Username:").pack(anchor="w")
        user_entry = _dlg_entry(f, width=30)
        user_entry.pack(anchor="w", ipady=3, pady=(2, 8))
        _dlg_label(f, "Password:").pack(anchor="w")
        pass_entry = _dlg_entry(f, show="\u2022", width=30)
        pass_entry.pack(anchor="w", ipady=3, pady=(2, 4))
        _show_hide_button(f, pass_entry).pack(anchor="w", pady=(2, 0))

        # Optional recovery: a caret below Show that expands an inline Security
        # code field. Signing in with a code there unlocks the books via the
        # recovery code from setup, for when a password is forgotten.
        code_entry = None
        rec_frame = None
        caret = None
        if do_recovery is not None:
            caret = _dlg_label(
                f, "\u25b8 Forgot your password? Use a security code")
            caret.config(fg="#d8a657", cursor="hand2")
            caret.pack(anchor="w", pady=(12, 0))
            rec_frame = tk.Frame(f, bg=DLG_BG)
            _dlg_label(rec_frame, "Security code:").pack(anchor="w")
            code_entry = _dlg_entry(rec_frame, width=30)
            code_entry.pack(anchor="w", ipady=3, pady=(2, 0))

        err = _dlg_label(f, "", err=True, wrap=420)

        def show_err(msg):
            err.config(text=msg)
            err.pack(anchor="w", pady=(8, 0))

        def toggle_recovery(_e=None):
            rec["open"] = not rec["open"]
            if rec["open"]:
                caret.config(
                    text="\u25be Forgot your password? Use a security code")
                rec_frame.pack(anchor="w", pady=(8, 0), before=btns)
                code_entry.focus_set()
            else:
                caret.config(
                    text="\u25b8 Forgot your password? Use a security code")
                rec_frame.pack_forget()

        def try_login(_e=None):
            # If the security-code section is open and filled, unlock with the
            # recovery code instead of a username/password.
            if (do_recovery is not None and rec["open"]
                    and code_entry.get().strip()):
                try:
                    result["data"] = do_recovery(code_entry.get())
                except _SigninError as exc:
                    show_err(str(exc))
                    code_entry.delete(0, "end")
                    code_entry.focus_set()
                    return
                win.destroy()
                return
            uname = users.normalize_username(user_entry.get())
            secret = pass_entry.get()
            if not uname or not secret:
                show_err("Enter your username and password.")
                return
            try:
                result["data"] = do_login(uname, secret)
            except _SigninError as exc:
                show_err(str(exc))
                pass_entry.delete(0, "end")
                pass_entry.focus_set()
                return
            win.destroy()

        def cancel():
            result["data"] = None
            win.destroy()

        pass_entry.bind("<Return>", try_login)
        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Sign in", try_login, primary=True).pack(
            side="right")
        if caret is not None:
            caret.bind("<Button-1>", toggle_recovery)
            code_entry.bind("<Return>", try_login)
        win.protocol("WM_DELETE_WINDOW", cancel)
        self._make_dialog_static(win)
        user_entry.focus_set()
        self.wait_window(win)
        return result["data"]

    def _login_over_wire(self, client, host_label):
        """Sign in to the host with a username and password (the shared sign-in
        card). Returns the host's login result dict on success, or None if
        cancelled."""
        def do_login(uname, secret):
            try:
                resp = client.login(uname, secret)
            except hostnet.HostConnectionError:
                raise _SigninError("Lost the connection to the host.")
            if not resp.get("ok"):
                raise _SigninError(resp.get(
                    "error", "That username or password is not correct."))
            return resp.get("result") or {}
        return self._signin_card(
            f"Sign in to {host_label}",
            "Enter your username and password for these books.", do_login)

    def _enter_client_mode(self, client, result, host, port):
        """We are connected and signed in: switch the window into client mode,
        wiring the RemoteGateway and a session carrying the host-reported
        role, then show the normal workspace."""
        self._client = client
        self.mode = "client"
        self.conn = None
        self._book_data_key = None
        self.db_path = None
        username = result.get("username") or ""
        role = result.get("role") or roles.STAFF
        host_label = host if port == hostnet.DEFAULT_PORT else f"{host}:{port}"
        self._session = _RemoteSession(username, role, host_label=host_label)
        self.gateway = gateway.RemoteGateway(client)

        # If the host requires a password change (a one-time password, or one
        # past the rotation age), force it now -- the host refuses all other
        # work until it is done. Cancelling disconnects.
        reason = result.get("change_required")
        if reason and not self._force_remote_password_change(reason):
            self._disconnect_client()
            self._back_to_entry("Connect again to continue.")
            return

        self._show_workspace()
        self._refresh_signout_button()
        self._refresh_open_badge()
        try:
            self.refresh_all()
        except Exception:
            pass
        self.set_status(
            f"Connected to {host_label} as {username} "
            f"({roles.label(role)}).", kind="ok")

    def _force_remote_password_change(self, reason):
        """In client mode, require the signed-in user to set a new password
        over the wire before working -- when they hold a one-time password, or
        their password has passed the rotation age. They either set a new
        password or disconnect; there is no skip (the host enforces this too).
        Returns True if changed, False if they chose to disconnect."""
        result = {"ok": False}
        win = tk.Toplevel(self)
        win.title("Set a new password")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Set a new password", title=True).pack(anchor="w")
        if reason == "expired":
            intro = ("Your password is more than %d days old. For security on "
                     "shared books, please set a new one to continue."
                     % service.PASSWORD_MAX_AGE_DAYS)
        else:
            intro = ("You signed in with a one-time password. Please choose "
                     "your own password now \u2014 only you will know it.")
        _dlg_label(f, intro, dim=True, wrap=420).pack(anchor="w", pady=(4, 12))
        _dlg_label(f, "Current password:").pack(anchor="w")
        e0 = _dlg_entry(f, show="\u2022", width=30)
        e0.pack(anchor="w", ipady=3, pady=(2, 6))
        _dlg_label(f, "New password:").pack(anchor="w")
        e1 = _dlg_entry(f, show="\u2022", width=30)
        e1.pack(anchor="w", ipady=3, pady=(2, 6))
        _dlg_label(f, "Confirm:").pack(anchor="w")
        e2 = _dlg_entry(f, show="\u2022", width=30)
        e2.pack(anchor="w", ipady=3, pady=(2, 4))
        _show_hide_button(f, e0, e1, e2).pack(anchor="w", pady=(2, 0))
        err = _dlg_label(f, "", err=True, wrap=420)

        def save():
            if e1.get() != e2.get():
                err.config(text="The two new passwords do not match.")
                err.pack(anchor="w", pady=(8, 0))
                return
            try:
                self.gateway.change_own_password(e0.get(), e1.get())
            except gateway.GatewayError as ex:
                err.config(text=str(ex) or "Could not set the password.")
                err.pack(anchor="w", pady=(8, 0))
                return
            except Exception as ex:
                err.config(text=str(ex) or ex.__class__.__name__)
                err.pack(anchor="w", pady=(8, 0))
                return
            result["ok"] = True
            win.destroy()

        def decline():
            # No skip: disconnecting is the only alternative to setting one.
            result["ok"] = False
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(14, 0))
        _dlg_button(btns, "Set password", save, primary=True).pack(
            side="right")
        _dlg_button(btns, "Disconnect", decline).pack(side="right",
                                                      padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", decline)
        self._center_dialog(win)
        win.focus_force()
        e0.focus_set()
        self.wait_window(win)
        return result["ok"]

    # ------------------------------------------------------------------
    # host mode: sharing the open book to other computers (host console)
    # ------------------------------------------------------------------
    #
    # When the owner starts hosting, the book is re-opened on a thread-safe
    # connection and a HostServer is started on it (host_main.start_local_
    # host). While hosting, the normal tabs are put away and this window
    # becomes a read-only console showing how to connect and who is connected;
    # only the lock-serialised host engine touches the data, so there is no
    # concurrent-access hazard. To do bookkeeping while hosting, a person
    # connects as a client (from another computer, or another window to this
    # one). Stopping hosting returns to the book's normal sign-in.

    def _host_display(self):
        """Connection details for the running host, for the Hosting card:
        book name, LAN addresses, port, whether it is discoverable, and the
        security fingerprint. Returns None when not hosting."""
        st = self._host_state
        if st is None:
            return None
        try:
            addrs = host_main._lan_addresses()
        except Exception:
            addrs = []
        try:
            fp = hostnet.pretty_fingerprint(st.get("fingerprint") or "")
        except Exception:
            fp = "(unavailable)"
        return {
            "book": os.path.basename(st.get("book") or self.db_path or ""),
            "addrs": addrs,
            "port": st.get("port"),
            "advertising": True,
            "fingerprint": fp,
        }

    def _host_connected_count(self):
        """How many other computers are connected, from the host's own count.
        We ask the host over our local client connection; when signed out
        locally (no connection) the count is unavailable, so we report 0."""
        if self._host_state is None or self.gateway is None:
            return 0
        try:
            n = int(self.gateway.host_status().get("session_count", 0))
        except Exception:
            return 0
        # Exclude our own session while signed in here.
        if self._session is not None:
            n -= 1
        return max(0, n)

    def _start_hosting(self):
        """Begin sharing the open book on the network. Hosting runs as a
        separate background process, so it keeps serving even after this window
        is closed. Owner only; the book must be a protected, shared
        (multi-user) book. Once it is up, this computer connects to it as a
        local client so the owner can keep working."""
        if self.mode != "local" or self.conn is None \
                or self._book_data_key is None:
            messagebox.showinfo("Not available",
                                "Open the shared books on this computer "
                                "first.")
            return
        if self._host_state is not None or self._host_proc is not None:
            messagebox.showinfo(
                "Already hosting",
                "A set of books is already being hosted on this computer. "
                "Stop hosting first (Sharing tab) before hosting a different "
                "set.")
            return
        if not self._can(roles.MANAGE_USERS):
            messagebox.showinfo("Not available",
                                "Only the owner can host these books.")
            return
        path = self.db_path
        if not (path and crypto.is_protected(path)):
            messagebox.showinfo("Not available",
                                "Only protected, shared books can be hosted.")
            return
        try:
            shared = users.multiuser_enabled(self.conn)
        except Exception:
            shared = False
        if not shared:
            messagebox.showinfo(
                "Set up sharing first",
                "Set up shared access first (Sharing tab \u2192 Shared "
                "access), so each person has their own sign-in.")
            return
        if not self._confirm_blue(
                "Host these books",
                "Share these books on the network so other computers can "
                "sign in?\n\nHosting runs in the background and keeps serving "
                "even if you close this program. After it starts, sign in to "
                "keep working here. While hosting, making local backups and "
                "changing encryption pause \u2014 stop hosting to do those.",
                ok_label="Start hosting"):
            return

        data_key = self._book_data_key
        # Flush to disk, then close the single-thread connection so the host
        # process can open a thread-safe one from the up-to-date file.
        try:
            self.conn.commit()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = None
        self.gateway = None

        self.set_status("Starting hosting in the background\u2026", kind="info")
        try:
            self.update_idletasks()
        except Exception:
            pass
        try:
            proc, state = host_main.spawn_detached(path, data_key,
                                                   advertise=True)
        except Exception as e:
            messagebox.showerror(
                "Could not start hosting",
                "Hosting could not be started:\n\n%s\n\nThe books were not "
                "changed." % e)
            # Re-open the book locally so the owner is not stranded.
            self._session = None
            self._open_database(path)
            return

        # The background host now holds the key; we no longer keep it here.
        self._book_data_key = None
        self._host_proc = proc
        self._host_state = state
        self.mode = "host"
        self.db_path = state.get("book") or path
        self._session = None
        self._refresh_signout_button()
        self._update_host_count()
        self.set_status(
            "Now hosting in the background. Sign in to keep working here.",
            kind="ok")
        # Offer to sign in straight away so work continues without a gap.
        self._host_sign_in()

    def _adopt_running_host(self, state):
        """A previous run -- or another window -- left a host serving in the
        background. Take it over so this session can use those books or stop
        them. Present the ordinary branded sign-in for the hosted books right
        away (over the loopback), so launching or opening a second window while
        hosting looks like a normal sign-in rather than a management page.
        Cancelling the sign-in falls back to the landing page (via
        _host_sign_in). We did not spawn the host this session, so there is no
        Popen handle -- stopping is by pid via the recorded state."""
        self._host_proc = None
        self._host_state = state
        self.mode = "local"
        self.db_path = None
        self._session = None
        self.gateway = None
        self.conn = None
        self._book_data_key = None
        self._refresh_signout_button()
        self.set_status(
            "These books are being hosted on this computer.", kind="info")
        # Branded sign-in: branding on the left, the sign-in card pinned on the
        # right (the same layout as the local sign-in). _host_sign_in opens the
        # loopback sign-in card; cancel/failure lands on the landing page.
        self._show_locked_screen("Sign in to continue.", action=False,
                                 centered=False)
        self._host_sign_in()

    def _update_host_count(self):
        """Refresh the 'N connected' line every couple of seconds while
        hosting. When signed in we ask the host for its live count; when signed
        out locally we cannot ask. Idempotent: any pending tick is cancelled
        first, so re-entering host mode never stacks two timers."""
        if self._host_poll_id is not None:
            try:
                self.after_cancel(self._host_poll_id)
            except Exception:
                pass
            self._host_poll_id = None
        if self.mode != "host" or self._host_state is None:
            return
        if self.gateway is not None:
            n = self._host_connected_count()
            try:
                self.tab_sharing.refresh_host_count(n)
            except Exception:
                pass
            if self._host_locked_shown:
                word = "person" if n == 1 else "people"
                try:
                    self._host_locked_count.config(
                        text="%d %s connected" % (n, word))
                except Exception:
                    pass
        elif self._host_locked_shown:
            try:
                self._host_locked_count.config(
                    text="Running in the background")
            except Exception:
                pass
        self._host_poll_id = self.after(2000, self._update_host_count)

    def _terminate_host_process(self):
        """Stop the background host process -- by Popen handle if we started it
        this session, otherwise by pid from its recorded state."""
        proc = self._host_proc
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=6)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        else:
            st = self._host_state or {}
            if st.get("pid"):
                hoststate.terminate(st.get("pid"), timeout=6.0)
        # The host clears its own state on a clean stop; make sure it is gone.
        hoststate.clear_state()

    def _stop_hosting(self):
        """Stop hosting from the workspace/Sharing tab. Owner only: a manager
        or staff member working on the host machine must not be able to stop
        sharing for everyone. (When signed in, the role is known directly.)"""
        if self._host_state is None and self._host_proc is None:
            return
        if self._session is None or not self._session.can(roles.MANAGE_USERS):
            messagebox.showinfo(
                "Only the owner can stop hosting",
                "Only the owner can stop sharing these books.")
            return
        self._do_stop_hosting()

    def _host_stop_requested(self):
        """Stop hosting when no owner is signed in to the host on this computer
        -- from the Sharing tab while signed out, working in another book, or
        connected elsewhere. Anyone could be sitting at this computer, so we
        require the OWNER's username and password against the running host
        before shutting it down -- otherwise anyone with physical access (e.g.
        via their own personal, unencrypted books) could stop sharing for
        everyone. A non-owner's valid sign-in is refused; hosting keeps going."""
        st = self._host_state
        if st is None:
            return
        port = st.get("port") or hostnet.DEFAULT_PORT
        try:
            client = hostnet.HostClient("127.0.0.1", port)
            client.connect()
        except Exception as e:
            messagebox.showerror(
                "Could not reach the host",
                "Could not contact the books being hosted on this "
                "computer:\n\n%s" % e)
            return
        result = self._login_over_wire(client, "stop hosting")
        # We stop the host by its process, not over this connection, so close
        # it either way.
        try:
            client.logout()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        if result is None:
            # Cancelled or failed sign-in -> hosting keeps running.
            return
        role = result.get("role") or roles.STAFF
        if not roles.can(role, roles.MANAGE_USERS):
            messagebox.showinfo(
                "Only the owner can stop hosting",
                "Those credentials are not the owner's. Only the owner can "
                "stop sharing these books \u2014 hosting is still running.")
            return
        self._do_stop_hosting()

    def _do_stop_hosting(self):
        """Shut the background host down and return to using the books normally
        on this computer. Authorization is checked by the callers above."""
        if self._host_state is None and self._host_proc is None:
            return
        if not self._confirm_blue(
                "Stop hosting", "Stop sharing these books on the network?\n\n"
                "The background host will be shut down and anyone connected "
                "will be disconnected. The books then return to their sign-in "
                "on this computer.", ok_label="Stop hosting"):
            return
        if self._host_poll_id is not None:
            try:
                self.after_cancel(self._host_poll_id)
            except Exception:
                pass
            self._host_poll_id = None
        self._close_client_if_any()
        path = (self._host_state or {}).get("book") or self.db_path
        self._terminate_host_process()
        self._host_proc = None
        self._host_state = None
        self.mode = "local"
        self.gateway = None
        self._session = None
        self.conn = None
        self._book_data_key = None
        self._hide_host_locked_screen()
        self._refresh_signout_button()
        self.set_status("Hosting stopped.", kind="info")
        # Re-open the book locally so the owner lands back at its sign-in.
        self._open_database(path or database.DEFAULT_DB_PATH)

    def _host_lock_local(self):
        """Sign out on this computer while the background host keeps running,
        so other computers stay connected. Returns to the branded landing page
        -- the owner can open other books, connect to a host (including the
        books hosted here, over the loopback), or stop hosting from the Sharing
        tab. The host process is untouched."""
        # Drop our local client connection and session; the host process stays
        # up and keeps serving the network. We become an ordinary local session
        # with no book open -- the running host is tracked by _host_state.
        self._close_client_if_any()
        self.gateway = None
        self._session = None
        self.conn = None
        self._book_data_key = None
        self.db_path = None
        self.mode = "local"
        self._last_book = None
        try:
            self.business_label.config(text="No books open")
        except Exception:
            pass
        self._refresh_signout_button()       # now hidden (no book open)
        self._back_to_entry(
            "Signed out. Your books are still being hosted in the background "
            "\u2014 sign in to use them here, open another set of books, or "
            "connect to a host.")
        self.set_status(
            "Signed out here. Hosting is still running for other computers.",
            kind="info")

    def _host_sign_in(self):
        """Sign in to the background host as a local client, to use the books
        on this computer. Hosting continues throughout. On cancel or failure,
        lands on the branded landing page (the host keeps running)."""
        st = self._host_state
        if st is None:
            return
        port = st.get("port") or hostnet.DEFAULT_PORT
        try:
            client = hostnet.HostClient("127.0.0.1", port)
            client.connect()
        except Exception as e:
            messagebox.showerror(
                "Could not reach the host",
                "Could not connect to the books being hosted on this "
                "computer:\n\n%s" % e)
            self._back_to_entry(
                "Hosting is running in the background. Open a set of books, or "
                "connect to a host.")
            return
        # We trust our own host implicitly (we launched it and hold its
        # fingerprint), so there is no first-contact prompt here.
        result = self._login_over_wire(client, "these books")
        if result is None:
            try:
                client.logout()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
            self._back_to_entry(
                "Hosting is running in the background. Open a set of books, or "
                "connect to a host.")
            return
        self._resume_host_session(client, result)

    def _resume_host_session(self, client, result):
        """Enter 'hosting and using' mode after signing in to the background
        host as a local client."""
        self._client = client
        self.mode = "host"
        self.conn = None
        username = result.get("username") or ""
        role = result.get("role") or roles.STAFF
        self._session = _RemoteSession(username, role,
                                       host_label="this computer")
        self.gateway = gateway.RemoteGateway(client)
        reason = result.get("change_required")
        if reason and not self._force_remote_password_change(reason):
            # They cancelled the forced change -> back to the landing page;
            # the host stays up.
            self.gateway = None
            self._session = None
            self._close_client_if_any()
            self.conn = None
            self._book_data_key = None
            self.db_path = None
            self.mode = "local"
            self._back_to_entry(
                "Hosting is running in the background. Open a set of books, or "
                "connect to a host.")
            self._refresh_signout_button()
            return
        self._show_workspace()
        self._refresh_signout_button()
        self._refresh_open_badge()
        try:
            self.refresh_all()
        except Exception:
            pass
        # Restart the live connected-count poll: it stops when we sign out
        # (mode leaves "host"), so re-entering host mode must kick it off again.
        self._update_host_count()
        self.set_status(
            "Signed in \u2014 you can keep working while hosting.", kind="ok")

    def _enable_multiuser_flow(self):
        """Switch a single-owner protected business book into shared
        (multi-user) mode: register the owner under a username and confirm
        their passphrase. Returns True on success."""
        if self._session is None or self._book_data_key is None:
            messagebox.showerror(
                "Not available",
                "Open a protected business book first.")
            return False
        win = tk.Toplevel(self)
        win.title("Set up shared access")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"ok": False}
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Set up shared access", title=True).pack(anchor="w")
        _dlg_label(f, "Shared access lets employees sign in with their own "
                      "username and password, each with a role. You are the "
                      "owner. Choose a username for yourself and confirm your "
                      "passphrase to begin.", dim=True, wrap=460).pack(
            anchor="w", pady=(4, 12))
        _dlg_label(f, "Your username:").pack(anchor="w")
        uname_e = _dlg_entry(f, width=30)
        uname_e.insert(0, "owner")
        uname_e.pack(anchor="w", ipady=3, pady=(2, 8))
        _dlg_label(f, "Your display name (optional):").pack(anchor="w")
        disp_e = _dlg_entry(f, width=30)
        disp_e.pack(anchor="w", ipady=3, pady=(2, 8))
        _dlg_label(f, "Confirm your passphrase:").pack(anchor="w")
        pass_e = _dlg_entry(f, show="\u2022", width=30)
        pass_e.pack(anchor="w", ipady=3, pady=(2, 4))
        _show_hide_button(f, pass_e).pack(anchor="w", pady=(2, 0))
        err = _dlg_label(f, "", err=True, wrap=460)

        def proceed():
            try:
                service.enable_multiuser(self._session, pass_e.get(),
                                         uname_e.get(),
                                         display_name=disp_e.get())
            except Exception as e:
                err.config(text=str(e) or e.__class__.__name__)
                err.pack(anchor="w", pady=(8, 0))
                return
            result["ok"] = True
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(16, 0))
        _dlg_button(btns, "Cancel", win.destroy).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Turn on shared access", proceed,
                    primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        uname_e.focus_set()
        self._center_dialog(win)
        self.wait_window(win)
        if result["ok"]:
            self.set_status("Shared access is on. You can now add users.",
                            kind="ok")
        return result["ok"]

    def _open_users_manager(self):
        """The owner's screen to add people, set roles, reset passwords, and
        remove people."""
        if self._session is None or not self._session.can(roles.MANAGE_USERS):
            messagebox.showinfo("Not available",
                                "Only an owner can manage users.")
            return
        win = tk.Toplevel(self)
        win.title("Users")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Users on these books", title=True).pack(anchor="w")
        _dlg_label(f, "Add people, set their role, reset a forgotten "
                      "password, or remove someone. Removing a person stops "
                      "their password from opening the books.", dim=True,
                   wrap=520).pack(anchor="w", pady=(4, 10))
        lst = tk.Listbox(f, width=64, height=8)
        lst.pack(anchor="w", pady=(0, 8))

        def reload_list():
            lst.delete(0, "end")
            try:
                people = self.gateway.list_users()
            except gateway.GatewayError:
                people = []
            for u in people:
                mark = "" if u["active"] else "  (inactive)"
                disp = ("  - " + u["display_name"]) if u["display_name"] else ""
                lst.insert("end", "%s   [%s]%s%s" % (
                    u["username"], roles.label(u["role"]), disp, mark))

        def selected_username():
            sel = lst.curselection()
            if not sel:
                messagebox.showinfo("Pick a user",
                                    "Select a user in the list first.",
                                    parent=win)
                return None
            return lst.get(sel[0]).split("   ")[0].strip()

        def do_add():
            info = self._prompt_new_user(win)
            if not info:
                return
            try:
                self.gateway.add_user(info["username"], info["role"],
                                      info["password"],
                                      display_name=info["display"],
                                      must_change=info["must_change"])
            except gateway.GatewayError as e:
                messagebox.showerror("Could not add user", str(e), parent=win)
                return
            if info.get("generated"):
                uname = users.normalize_username(info["username"])
                messagebox.showinfo(
                    "User added",
                    "User '%s' was created.\n\n"
                    "One-time password:\n\n    %s\n\n"
                    "Give this to them. Spaces and capitals don't matter when "
                    "they type it. They'll be asked to set their own password "
                    "the first time they sign in." % (uname, info["password"]),
                    parent=win)
            reload_list()

        def do_reset():
            uname = selected_username()
            if not uname:
                return
            pw = self._prompt_password(win, "Reset password",
                                       "New password for '%s':" % uname)
            if not pw:
                return
            try:
                self.gateway.reset_password(uname, pw)
            except gateway.GatewayError as e:
                messagebox.showerror("Could not reset password", str(e),
                                     parent=win)
                return
            messagebox.showinfo("Password reset",
                                "Password updated for '%s'." % uname,
                                parent=win)

        def do_role():
            uname = selected_username()
            if not uname:
                return
            cur_role = roles.STAFF
            try:
                for u in self.gateway.list_users():
                    if u["username"] == uname:
                        cur_role = u["role"]
                        break
            except gateway.GatewayError:
                pass
            new = self._prompt_choose_role(win, cur_role)
            if not new:
                return
            try:
                self.gateway.change_role(uname, new)
            except gateway.GatewayError as e:
                messagebox.showerror("Could not change role", str(e),
                                     parent=win)
                return
            reload_list()

        def do_remove():
            uname = selected_username()
            if not uname:
                return
            if not messagebox.askyesno(
                    "Remove user",
                    "Remove '%s'? Their password will no longer open these "
                    "books." % uname, parent=win):
                return
            try:
                self.gateway.remove_user(uname)
            except gateway.GatewayError as e:
                messagebox.showerror("Could not remove user", str(e),
                                     parent=win)
                return
            reload_list()

        row = tk.Frame(f, bg=DLG_BG)
        row.pack(anchor="w", pady=(0, 8))
        _dlg_button(row, "Add user\u2026", do_add).pack(side="left",
                                                        padx=(0, 6))
        _dlg_button(row, "Reset password\u2026", do_reset).pack(side="left",
                                                                padx=6)
        _dlg_button(row, "Change role\u2026", do_role).pack(side="left",
                                                            padx=6)
        _dlg_button(row, "Remove\u2026", do_remove).pack(side="left", padx=6)
        _dlg_button(f, "Close", win.destroy, primary=True).pack(
            anchor="e", pady=(8, 0))
        reload_list()
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._center_dialog(win)
        self.wait_window(win)

    def _open_password_reset(self):
        """A manager's focused screen to give a staff member a new one-time
        password. The whole roster is shown -- owner first, then managers, then
        staff -- so the manager can find the person, but only staff rows can be
        reset here; owner and manager rows are greyed and refused. This is the
        same staff-only limit that service.reset_password enforces, and the
        one-time password is the same kind the owner's new-user setup issues."""
        sess = self._session
        if sess is None or not sess.can(roles.RESET_PASSWORD):
            messagebox.showinfo(
                "Not available",
                "You don't have permission to reset passwords.")
            return
        win = tk.Toplevel(self)
        win.title("Reset a password")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Reset a password", title=True).pack(anchor="w")
        _dlg_label(f, "Pick a person and Ledger sets a one-time password for "
                      "you to give them. They choose their own the next time "
                      "they sign in. You can reset a staff member's password; "
                      "only the owner can reset an owner's or another "
                      "manager's.", dim=True, wrap=520).pack(
                          anchor="w", pady=(4, 10))
        lst = tk.Listbox(f, width=64, height=8)
        lst.pack(anchor="w", pady=(0, 4))
        hint = _dlg_label(f, "", dim=True, wrap=520)
        hint.pack(anchor="w", pady=(0, 8))
        rows = []  # parallel to listbox lines: (username, role)
        order = {roles.OWNER: 0, roles.MANAGER: 1, roles.STAFF: 2}

        def reload_list():
            lst.delete(0, "end")
            rows.clear()
            hint.config(text="")
            try:
                people = self.gateway.list_people()
            except gateway.GatewayError as e:
                hint.config(text=(
                    "Couldn't load the list of people: %s\nIf these books are "
                    "being hosted, the host may need to be stopped and "
                    "restarted to pick up this update." % e))
                return
            people.sort(key=lambda u: (order.get(u["role"], 9), u["username"]))
            staff_n = 0
            for u in people:
                disp = ("  - " + u["display_name"]) if u["display_name"] else ""
                mark = "" if u["active"] else "  (inactive)"
                is_staff = (u["role"] == roles.STAFF)
                tag = "" if is_staff else "   (owner only)"
                lst.insert("end", "%s   [%s]%s%s%s" % (
                    u["username"], roles.label(u["role"]), disp, mark, tag))
                if not is_staff:
                    lst.itemconfig(lst.size() - 1, foreground="#9aa6bd")
                else:
                    staff_n += 1
                rows.append((u["username"], u["role"]))
            if staff_n == 0:
                hint.config(text=(
                    "No staff members yet. Staff accounts are added from the "
                    "owner's \u2018Manage users\u2019 screen; once added they "
                    "appear here to reset."))

        def do_reset():
            sel = lst.curselection()
            if not sel:
                messagebox.showinfo("Pick a person",
                                    "Select someone in the list first.",
                                    parent=win)
                return
            uname, role = rows[sel[0]]
            if role != roles.STAFF:
                messagebox.showinfo(
                    "Owner only",
                    "You can reset a staff member's password. Only the owner "
                    "can reset an owner's or another manager's.", parent=win)
                return
            temp = crypto.generate_temp_password()
            try:
                self.gateway.reset_password(uname, temp, must_change=True)
            except gateway.GatewayError as e:
                messagebox.showerror("Could not reset password", str(e),
                                     parent=win)
                return
            messagebox.showinfo(
                "Temporary password set",
                "One-time password for '%s':\n\n    %s\n\n"
                "Give this to them. Spaces and capitals don't matter when "
                "they type it. They'll be asked to set their own password the "
                "first time they sign in." % (uname, temp), parent=win)

        row = tk.Frame(f, bg=DLG_BG)
        row.pack(anchor="w", pady=(0, 8))
        _dlg_button(row, "Reset password\u2026", do_reset,
                    primary=True).pack(side="left")
        _dlg_button(f, "Close", win.destroy).pack(anchor="e", pady=(8, 0))
        reload_list()
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._center_dialog(win)
        self.wait_window(win)

    def _open_audit_log(self):
        """A read-only window of the activity log (who did what, when),
        visible to owner and manager."""
        sess = self._session
        if sess is None or not sess.can(roles.VIEW_AUDIT):
            messagebox.showinfo(
                "Not available",
                "Only an owner or manager can view the activity log.")
            return
        try:
            entries = self.gateway.view_audit(limit=500)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not load the activity log", str(e))
            return
        except Exception as e:
            messagebox.showerror("Could not load the activity log", str(e))
            return

        win = tk.Toplevel(self)
        win.title("Activity log")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(True, True)
        win.grab_set()
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=20, pady=16)
        _dlg_label(f, "Activity log", title=True).pack(anchor="w")
        _dlg_label(f, "Actions taken through Ledger on these books, newest "
                      "first. (This records what is done in the program; it "
                      "is an accountability aid, not tamper-proof evidence.)",
                   dim=True, wrap=600).pack(anchor="w", pady=(4, 10))

        table = tk.Frame(f, bg=DLG_BG)
        table.pack(fill="both", expand=True)
        cols = ("when", "who", "action", "details")
        tree = ttk.Treeview(table, columns=cols, show="headings", height=16)
        for c, label, w in (("when", "When", 160), ("who", "User", 120),
                            ("action", "Action", 190),
                            ("details", "Details", 240)):
            tree.heading(c, text=label)
            tree.column(c, width=w, anchor="w", stretch=True)
        vsb = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        if not entries:
            tree.insert("", "end",
                        values=("", "", "(no activity recorded yet)", ""))
        else:
            for e in entries:
                when = (e.get("at") or "").replace("T", "   ")
                tree.insert("", "end", values=(
                    when, e.get("username", ""),
                    _audit_action_label(e.get("action", "")),
                    e.get("detail", "")))

        _dlg_button(f, "Close", win.destroy, primary=True).pack(
            anchor="e", pady=(10, 0))
        win.geometry("760x480")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._center_dialog(win)
        self.wait_window(win)

    def _prompt_new_user(self, parent):
        """Collect the details for a new user. Returns a dict or None."""
        win = tk.Toplevel(parent)
        win.title("Add user")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(parent)
        win.resizable(False, False)
        win.grab_set()
        res = {"info": None}
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Add a user", title=True).pack(anchor="w")
        _dlg_label(f, "Username:").pack(anchor="w", pady=(8, 0))
        uname_e = _dlg_entry(f, width=30)
        uname_e.pack(anchor="w", ipady=3, pady=(2, 6))
        _dlg_label(f, "Display name (optional):").pack(anchor="w")
        disp_e = _dlg_entry(f, width=30)
        disp_e.pack(anchor="w", ipady=3, pady=(2, 6))
        _dlg_label(f, "Role:").pack(anchor="w")
        var = tk.StringVar(value=roles.STAFF)
        for r in (roles.STAFF, roles.MANAGER, roles.OWNER):
            _dlg_radio(f, roles.label(r), var, r).pack(anchor="w", pady=1)
        _dlg_label(f, "Password:").pack(anchor="w", pady=(6, 0))
        p1 = _dlg_entry(f, show="\u2022", width=30)
        p1.pack(anchor="w", ipady=3, pady=(2, 4))
        _dlg_label(f, "Confirm password:").pack(anchor="w")
        p2 = _dlg_entry(f, show="\u2022", width=30)
        p2.pack(anchor="w", ipady=3, pady=(2, 4))
        prow = tk.Frame(f, bg=DLG_BG)
        prow.pack(anchor="w", pady=(2, 0))
        _show_hide_button(prow, p1, p2).pack(side="left")
        generated = {"on": False}
        must_change = tk.BooleanVar(value=False)

        def generate():
            temp = crypto.generate_temp_password()
            for e in (p1, p2):
                e.delete(0, "end")
                e.insert(0, temp)
                e.config(show="")          # reveal so the owner can record it
            generated["on"] = True
            must_change.set(True)
            err.pack_forget()

        tk.Button(prow, text="Generate one-time password", command=generate,
                  font=FONT, bg=DLG_BTN, fg=DLG_TXT,
                  activebackground=DLG_BTN_ACTIVE, activeforeground=DLG_TXT,
                  relief="flat", padx=10, pady=2, cursor="hand2",
                  bd=0).pack(side="left", padx=(8, 0))
        _dlg_check(f, "Require this person to set their own password the first "
                      "time they sign in", must_change, wrap=380).pack(
            anchor="w", pady=(8, 0), fill="x")
        err = _dlg_label(f, "", err=True, wrap=380)

        def ok():
            if p1.get() != p2.get():
                err.config(text="The two passwords do not match.")
                err.pack(anchor="w", pady=(8, 0))
                return
            if len(p1.get()) < service.MIN_PASSWORD_LEN:
                err.config(text="Password must be at least %d characters."
                           % service.MIN_PASSWORD_LEN)
                err.pack(anchor="w", pady=(8, 0))
                return
            res["info"] = {"username": uname_e.get(),
                           "display": disp_e.get(),
                           "role": var.get(), "password": p1.get(),
                           "must_change": bool(must_change.get()),
                           "generated": generated["on"]}
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(14, 0))
        _dlg_button(btns, "Cancel", win.destroy).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Add", ok, primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        uname_e.focus_set()
        self._center_dialog(win)
        self.wait_window(win)
        return res["info"]

    def _prompt_password(self, parent, title, prompt):
        """Ask for a new password twice. Returns the password or None."""
        win = tk.Toplevel(parent)
        win.title(title)
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(parent)
        win.resizable(False, False)
        win.grab_set()
        res = {"pw": None}
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, prompt, wrap=380).pack(anchor="w")
        e1 = _dlg_entry(f, show="\u2022", width=30)
        e1.pack(anchor="w", ipady=3, pady=(6, 6))
        _dlg_label(f, "Confirm:").pack(anchor="w")
        e2 = _dlg_entry(f, show="\u2022", width=30)
        e2.pack(anchor="w", ipady=3, pady=(2, 4))
        _show_hide_button(f, e1, e2).pack(anchor="w", pady=(2, 0))
        err = _dlg_label(f, "", err=True, wrap=380)

        def ok():
            if e1.get() != e2.get():
                err.config(text="The two passwords do not match.")
                err.pack(anchor="w", pady=(8, 0))
                return
            if len(e1.get()) < service.MIN_PASSWORD_LEN:
                err.config(text="At least %d characters."
                           % service.MIN_PASSWORD_LEN)
                err.pack(anchor="w", pady=(8, 0))
                return
            res["pw"] = e1.get()
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(14, 0))
        _dlg_button(btns, "Cancel", win.destroy).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "OK", ok, primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        e1.focus_set()
        self._center_dialog(win)
        self.wait_window(win)
        return res["pw"]

    def _prompt_choose_role(self, parent, current):
        """Pick a role. Returns the role string or None."""
        win = tk.Toplevel(parent)
        win.title("Choose role")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(parent)
        win.resizable(False, False)
        win.grab_set()
        res = {"role": None}
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Choose a role", title=True).pack(anchor="w")
        _dlg_label(f, "Owner: full control. Manager: day-to-day books and "
                      "reports. Staff: record entries and view reports.",
                   dim=True, wrap=420).pack(anchor="w", pady=(4, 10))
        var = tk.StringVar(value=current)
        for r in roles.assignable_roles():
            _dlg_radio(f, roles.label(r), var, r).pack(anchor="w", pady=1)

        def ok():
            res["role"] = var.get()
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(anchor="e", pady=(14, 0))
        _dlg_button(btns, "Cancel", win.destroy).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "OK", ok, primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._center_dialog(win)
        self.wait_window(win)
        return res["role"]

    def _unlock_book(self, path):
        """Ask for the passphrase (or recovery code) to open a protected
        book. Returns (data_key, username) -- username is None unless a
        multi-user login identified the signer. (None, None) if cancelled."""
        if not crypto.CRYPTO_AVAILABLE:
            messagebox.showerror(
                "Encryption library needed",
                "This set of books is encrypted, but the 'cryptography' "
                "library isn't installed on this computer, so it can't be "
                "opened here.\n\nInstall it with:  pip install cryptography")
            return None, None
        try:
            vault = crypto.load_vault(path)
        except Exception as e:
            messagebox.showerror(
                "Cannot open this set of books",
                f"Its security file could not be read:\n\n{e}")
            return None, None

        # Multi-user business books use a username + password login instead of
        # a single passphrase. The flag is in the (non-secret) vault file, so
        # we can tell before unlocking which screen to show.
        if service.is_multiuser_vault(vault):
            return self._login_book(path, vault)

        win = tk.Toplevel(self)
        win.title("Unlock this set of books")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        result = {"key": None}
        using_recovery = {"on": False}

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "This set of books is protected", title=True).pack(
            anchor="w")
        prompt = _dlg_label(f, "Enter your passphrase to open it.", dim=True,
                            wrap=420)
        prompt.pack(anchor="w", pady=(4, 10))

        entry = _dlg_entry(f, show="\u2022", width=38)
        entry.pack(anchor="w", ipady=3)
        err = _dlg_label(f, "", err=True, wrap=420)

        toggle = _dlg_button(f, "Use recovery code instead", lambda: flip())

        def flip():
            using_recovery["on"] = not using_recovery["on"]
            if using_recovery["on"]:
                entry.config(show="")
                prompt.config(text="Enter your recovery code.")
                toggle.config(text="Use passphrase instead")
            else:
                entry.config(show="\u2022")
                prompt.config(text="Enter your passphrase to open it.")
                toggle.config(text="Use recovery code instead")
            entry.delete(0, "end"); entry.focus_set()
        toggle.pack(anchor="w", pady=(10, 0))

        def try_open(_e=None):
            secret = entry.get()
            try:
                result["key"] = crypto.unlock(vault, secret)
                win.destroy()
            except ValueError:
                err.config(text="That was not correct. Please try again.")
                err.pack(anchor="w", pady=(8, 0))
                entry.delete(0, "end"); entry.focus_set()

        def cancel():
            result["key"] = None
            win.destroy()

        entry.bind("<Return>", try_open)
        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(18, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Unlock", try_open, primary=True).pack(side="right")
        self._add_switch_books_button(btns, win)
        self._add_connect_host_button(btns, win)
        self._make_dialog_static(win, relx=0.5, rely=0.63)
        entry.focus_set()
        self.wait_window(win)
        return result["key"], None

    def _login_book(self, path, vault):
        """Username + password login for a multi-user business book, on the
        shared sign-in card (identical to the over-the-wire login). Returns
        (data_key, username) on success, or (None, None) if cancelled. The
        owner may fall back to the recovery code, which logs them in as the
        owner."""
        def do_login(uname, secret):
            try:
                key = crypto.unlock_as(vault, uname, secret)
            except ValueError:
                raise _SigninError(
                    "That username or password is not correct.")
            return {"key": key, "user": uname}

        def do_recovery(code):
            # The security code is the book's recovery code from setup. It
            # unlocks the vault directly, signing the owner in (no username).
            try:
                key = crypto.unlock(vault, code)
            except ValueError:
                raise _SigninError("That security code is not correct.")
            return {"key": key, "user": None}

        data = self._signin_card(
            "Sign in to these books",
            "Enter your username and password for these books.",
            do_login, do_recovery=do_recovery)
        if data is None:
            return None, None
        return data["key"], data["user"]

    def _open_database(self, path, announce=True, known_key=None):
        """Open a ledger database, creating and seeding it if new.

        For a protected book, `known_key` lets a caller reopen it with a key
        already held in memory (for example right after a restore) instead of
        prompting for the passphrase again."""
        is_new = not os.path.exists(path)

        # If this existing book is protected, it must be unlocked before we
        # open it. (A brand-new book has no vault yet -- its protection, if
        # any, is set up just after creation.) The data key is held only in
        # memory for as long as the book is open.
        data_key = None
        login_username = None
        if not is_new and crypto.is_protected(path):
            if not crypto.is_encrypted_db_file(path):
                # A vault file sits beside a PLAINTEXT data file: an earlier
                # "turn on protection" or "turn off protection" was interrupted
                # before it finished. The data is readable as-is, so rather
                # than lock the user out (the vault would make us expect an
                # encrypted file), remove the stray vault and open this as an
                # Open book.
                try:
                    crypto.delete_vault(path)
                except Exception:
                    pass
            elif known_key is not None:
                data_key = known_key
            else:
                # Put the neutral navy page behind the sign-in / unlock dialog
                # instead of whatever was on screen (or the default Record
                # Entry tab at startup). The on-page button is hidden while the
                # dialog is up (the dialog itself offers switching books).
                msg, centered = "Opening these books\u2026", True
                try:
                    _vault = crypto.load_vault(path)
                    if service.is_multiuser_vault(_vault):
                        msg, centered = "Sign in to continue.", False
                    else:
                        msg = "Enter your passphrase to open these books."
                        centered = True
                except Exception:
                    pass
                self._show_locked_screen(msg, action=False, centered=centered)
                data_key, login_username = self._unlock_book(path)
                if data_key is None:
                    # Cancelled or failed. If we left this sign-in to connect
                    # to a host (client mode is taking the screen), do not
                    # repaint the local locked page over it.
                    if getattr(self, "_suppress_locked_repaint", False):
                        self._suppress_locked_repaint = False
                        return False
                    # Otherwise the sign-in was cancelled: show the 3-button
                    # card so there is always a way forward (sign in again,
                    # open another set, or connect to a host).
                    if self._locked_shown:
                        self._back_to_entry(
                            "Sign in, open a set of books, or connect to a "
                            "host.")
                    return False

        try:
            conn = database.connect(path, data_key=data_key)
            database.init_db(conn)
            if is_new:
                seed.seed_accounts(conn)
        except Exception as e:
            messagebox.showerror("Could not open ledger",
                                 f"There was a problem opening:\n{path}\n\n{e}")
            return False

        if self.conn:
            self.conn.close()
        self.conn = conn
        self.db_path = path
        # Opening a book here always means working locally. Close any lingering
        # client connection and assert local mode, so the freshly opened book
        # can never be read through a stale host/client gateway (which would
        # make it look like "the same set of books" as before).
        self._close_client_if_any()
        self.mode = "local"
        # Bring an older multi-user book's tables up to date (e.g. add columns
        # introduced by a later version) before anything reads the user list.
        # A no-op for personal/single-owner books.
        try:
            users.migrate(self.conn)
        except Exception:
            pass
        # The unlocked data key for this book (None for an open/unencrypted
        # book). Held in memory only; used to load and save the encrypted data
        # file at rest and to read/verify encrypted backups.
        self._book_data_key = data_key

        # Establish who is acting on these books, for role enforcement on
        # multi-user business books. Personal and Open books have no session.
        if known_key is not None and self._session is not None:
            # Reopening after a restore: keep the same signed-in user, but
            # refresh the handles that changed.
            self._session.conn = self.conn
            self._session.data_key = data_key
            try:
                self._session.vault = crypto.load_vault(path)
            except Exception:
                pass
        else:
            self._establish_session(path, data_key, login_username)
        # Remember whether this open created a brand-new set of books; the
        # welcome tour keys off this so it appears for every new book.
        self._opened_new = is_new
        # A brand-new book that has not yet had encryption decided. Cleared
        # once handled (by the new-book flow, or at first profile save).
        self._book_needs_setup = is_new

        # Build the data gateway for the open book. In ordinary local use this
        # is a LocalGateway over the open connection -- the same operations the
        # tabs perform directly, just behind one interface, so the same tab
        # code can later run against a host (client mode) without change.
        self._build_local_gateway()

        # Show a friendly name for the open business in the header, with a
        # small badge so it is always clear whether a book is protected.
        nice = os.path.basename(path)
        badge = "  \U0001F512 Protected" if crypto.is_protected(path) else ""
        self.business_label.config(text=f"Open: {nice}{badge}"
                                   f"{self._session_badge()}")
        self._refresh_signout_button()

        if announce:
            if is_new:
                self.set_status(f"Created a new ledger: {path}")
            else:
                self.set_status(f"Opened ledger: {path}")
        else:
            self.set_status(f"Ledger ready: {path}")

        self.refresh_all()
        self._show_workspace()
        self._select_startup_tab()
        # If this person needs a new password (one-time password not yet
        # replaced, or it has passed the rotation age), require it now. (Not on
        # a restore-reopen, which keeps the same session.)
        if known_key is None:
            self._force_password_change()
        return True

    def _force_password_change(self):
        """On a shared (multi-user) book, require the signed-in user to set a
        new password before working when they still hold a one-time password,
        or when their password has passed the rotation age (see
        service.PASSWORD_MAX_AGE_DAYS). They either set a new password or sign
        out -- there is no way to skip it and keep working. Shown after the
        book opens."""
        reason = service.password_change_required(self._session)
        if reason is None:
            return

        win = tk.Toplevel(self)
        win.title("Set a new password")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Set a new password", title=True).pack(anchor="w")
        if reason == "expired":
            intro = ("Your password is more than %d days old. For security on "
                     "shared books, please set a new one to continue."
                     % service.PASSWORD_MAX_AGE_DAYS)
        else:
            intro = ("You signed in with a one-time password. Please choose "
                     "your own password now \u2014 only you will know it.")
        _dlg_label(f, intro, dim=True, wrap=420).pack(anchor="w", pady=(4, 12))
        _dlg_label(f, "New password:").pack(anchor="w")
        e1 = _dlg_entry(f, show="\u2022", width=30)
        e1.pack(anchor="w", ipady=3, pady=(2, 6))
        _dlg_label(f, "Confirm:").pack(anchor="w")
        e2 = _dlg_entry(f, show="\u2022", width=30)
        e2.pack(anchor="w", ipady=3, pady=(2, 4))
        _show_hide_button(f, e1, e2).pack(anchor="w", pady=(2, 0))
        err = _dlg_label(f, "", err=True, wrap=420)

        def save():
            if e1.get() != e2.get():
                err.config(text="The two passwords do not match.")
                err.pack(anchor="w", pady=(8, 0))
                return
            try:
                service.complete_first_login(self._session, e1.get())
            except Exception as e:
                err.config(text=str(e) or e.__class__.__name__)
                err.pack(anchor="w", pady=(8, 0))
                return
            win.destroy()
            self.set_status("Your new password has been set.", kind="ok")

        def decline():
            # Skipping is not allowed: signing out is the only alternative to
            # setting a new password. They are prompted again next sign-in.
            win.destroy()
            self._lock_open_book()
            self.set_status(
                "Signed out \u2014 a new password is needed to continue.",
                kind="info")

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(14, 0))
        _dlg_button(btns, "Set password", save, primary=True).pack(
            side="right")
        _dlg_button(btns, "Sign out", decline).pack(side="right", padx=(0, 8))
        # The X does not skip the requirement -- it signs out.
        win.protocol("WM_DELETE_WINDOW", decline)
        self._center_dialog(win)
        win.focus_force()
        e1.focus_set()
        self.wait_window(win)

    def _refresh_open_badge(self):
        """Update the header to show the open book's name and, if it is
        encrypted, a small Protected badge. In client mode it shows the host
        being worked on instead of a local file name."""
        if self.mode == "client":
            host = ""
            sess = self._session
            if sess is not None:
                host = getattr(sess, "host_label", "") or ""
            where = f"Connected to {host}" if host else "Connected to host"
            self.business_label.config(text=f"{where}{self._session_badge()}")
            return
        if self.mode == "host":
            book = os.path.basename(self.db_path or "")
            if self._session is None:
                self.business_label.config(
                    text="\U0001F310 Hosting: %s  (signed out here)" % book)
            else:
                self.business_label.config(
                    text="\U0001F310 Hosting: %s%s" % (book,
                                                       self._session_badge()))
            return
        nice = os.path.basename(self.db_path or "")
        badge = "  \U0001F512 Protected" if (
            self.db_path and crypto.is_protected(self.db_path)) else ""
        self.business_label.config(text=f"Open: {nice}{badge}"
                                   f"{self._session_badge()}")

    # ------------------------------------------------------------------
    # closing the program: the automatic safety backup
    # ------------------------------------------------------------------

    def _book_backup_dir(self):
        """The default backup folder for the book that is open now: a
        folder named for the business (or person) inside
        Documents/Ledger Backups. Used by the Backup tab and by the
        automatic backup taken on exit, so both agree on one location."""
        name = ""
        if self.conn:
            try:
                name = profile.get_profile(self.conn)["name"]
            except Exception:
                name = ""
        if not name:
            # Fall back to the data file's own name if there's no profile yet.
            name = os.path.splitext(os.path.basename(self.db_path or ""))[0]
        return backup.business_backup_dir(name)

    def _flush_book(self):
        """Force the open book's latest committed data out to its file on
        disk. For an encrypted book this re-writes the encrypted file; for an
        Open book it is a harmless no-op commit. Used before a backup so the
        copy captures the current state."""
        if self.conn is not None:
            try:
                self.conn.commit()
            except Exception:
                pass

    def _autosave_on_exit(self):
        """Take an automatic backup on the way out, but only if the data
        has changed since the last backup -- so a manual backup the user
        just made is not duplicated.

        Manual backups stay the main habit; this is a safety net for the
        times someone closes the program without one. A backup is never
        allowed to stop the program from closing, so any problem here is
        swallowed: the worst case is simply no extra copy, never a stuck
        window.

        Returns the path of the backup made, or None if none was needed
        (or it could not be made)."""
        if not self.conn:
            return None
        # Flush any pending write so the file on disk reflects the latest
        # data before we copy or fingerprint it.
        try:
            self.conn.commit()
        except Exception:
            pass
        try:
            book_dir = self._book_backup_dir()
        except Exception:
            return None
        made = None
        try:
            if not backup.is_current_state_backed_up(
                    self.db_path, book_dir, data_key=self._book_data_key):
                made = backup.backup(db_path=self.db_path,
                                     backup_dir=backup.auto_dir(book_dir),
                                     create=True, name_tag="_auto")
        except Exception:
            # Never block the close on a backup failure.
            made = None
        # Tidy away automatic copies older than the keep window so they
        # can't accumulate. Manual backups are left untouched, and the
        # newest copy is always kept.
        try:
            backup.prune_backups(book_dir, days=backup.AUTO_BACKUP_KEEP_DAYS)
        except Exception:
            pass
        return made

    def _on_close(self):
        """Window-close handler: save a safety backup if needed, then quit."""
        self._autosave_on_exit()
        self.destroy()

    def _select_startup_tab(self):
        """First-run friendliness.

        If this ledger has no profile yet (a brand-new user), open on the
        setup tab so the first thing they do is choose business or personal
        use and enter their details. Once a profile exists, open straight
        on Record Entry -- the day-to-day screen -- every time after that.
        """
        try:
            configured = profile.has_profile(self.conn)
        except Exception:
            configured = True  # if in doubt, don't nag; go to the normal tab
        if configured:
            self.tabs.select(self.tab_entry)
        else:
            self.tabs.select(self.tab_business)
            self.set_status(
                "Welcome! Start here: choose business or personal use and "
                "enter your details. After this, the program opens on "
                "Record Entry.", kind="ok")

    def _ledger_summary(self, path):
        """Read a ledger file's profile name and kind for labelling it in
        the books manager. This opens the file read-only and never changes
        or migrates it.

        A protected (encrypted) book cannot be read without its key -- and the
        manager lists books that have not been unlocked yet -- so for those we
        fall back to the file's own name and report the kind as 'protected'.
        """
        # A protected book's file is encrypted; don't try to read it as a
        # plain database. Use the file's own name as a friendly label.
        if crypto.is_protected(path):
            stem = os.path.splitext(os.path.basename(path))[0]
            return stem, "protected"
        name, kind = "", "business"
        try:
            c = sqlite3.connect(path)
            c.row_factory = sqlite3.Row
            try:
                row = c.execute(
                    "SELECT name, kind FROM business_profile WHERE id = 1"
                ).fetchone()
            except sqlite3.OperationalError:
                try:
                    row = c.execute(
                        "SELECT name FROM business_profile WHERE id = 1"
                    ).fetchone()
                except sqlite3.OperationalError:
                    row = None
            if row is not None:
                name = row["name"] or ""
                try:
                    kind = row["kind"] or "business"
                except (IndexError, KeyError):
                    kind = "business"
            c.close()
        except sqlite3.Error:
            pass
        return name, kind

    def _new_book_path(self, name):
        """Build a fresh, non-colliding .db path in the data folder from a
        chosen name (so new books sit alongside the others, easy to find)."""
        base = "".join(ch if (ch.isalnum() or ch in " -_") else "_"
                       for ch in (name or "")).strip().replace(" ", "_")
        if not base:
            base = "ledger"
        folder = paths.data_dir()
        candidate = os.path.join(folder, base + ".db")
        n = 2
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base}_{n}.db")
            n += 1
        return candidate

    # ------------------------------------------------------------------
    # Pull data from QuickBooks (import from an export file)
    # ------------------------------------------------------------------
    #
    # Slice 1 is the UI shell only: the two cards below let a person pick a
    # QuickBooks export file and choose what to bring in, but reading the file
    # and staging records is deliberately not wired yet -- that is the next
    # slice. Nothing here touches the open book's data.

    def _qb_detect_format(self, path):
        """A friendly note about the export format, from the file extension.
        Returns "" for an unrecognised extension."""
        ext = os.path.splitext(path)[1].lower()
        return {
            ".iif": "IIF detected",
            ".qbo": "OFX / Web Connect detected",
            ".ofx": "OFX / Web Connect detected",
            ".csv": "CSV detected",
        }.get(ext, "")

    def _quickbooks_import(self):
        """First card of the QuickBooks import: choose the export file.

        Opens a titled, centred dialog (the same in-app dialog style as the
        books manager) where the person picks a .IIF, .QBO/OFX, or .CSV file
        that QuickBooks exported. Continue then opens the 'what to import'
        card. Reading the file is the next slice; this only collects choices.
        """
        # Defensive: the header button is only shown with a local book open,
        # but guard anyway so the action is safe if ever reached otherwise.
        if self.mode != "local" or self.conn is None:
            messagebox.showinfo(
                "Open a set of books first",
                "Open a set of books on this computer before pulling data "
                "from QuickBooks. The import adds the data into the set of "
                "books that is open here.")
            return

        win = tk.Toplevel(self)
        win.title("Pull data from QuickBooks")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "Import from a QuickBooks export file",
                   title=True).pack(anchor="w")
        _dlg_label(f, "Choose the .IIF, .QBO / OFX, or .CSV file that "
                      "QuickBooks exported.", dim=True, wrap=430).pack(
                          anchor="w", pady=(4, 12))

        chosen = {"path": None}

        # A light row (like the choice rows elsewhere) showing the chosen file
        # on the left and the detected format on the right.
        file_row = tk.Frame(f, bg=DLG_CARD)
        file_row.pack(fill="x")
        file_lbl = tk.Label(file_row, text="No file chosen", bg=DLG_CARD,
                            fg=DLG_CARD_TX, font=FONT, anchor="w",
                            justify="left", padx=10, pady=7, wraplength=300)
        file_lbl.pack(side="left", fill="x", expand=True)
        fmt_lbl = tk.Label(file_row, text="", bg=DLG_CARD, fg=OK,
                           font=FONT_BOLD, padx=10, pady=7)
        fmt_lbl.pack(side="right")

        err = _dlg_label(f, "", err=True, wrap=430)

        def choose():
            path = filedialog.askopenfilename(
                parent=win, title="Choose a QuickBooks export file",
                filetypes=[
                    ("QuickBooks export files", "*.iif *.qbo *.ofx *.csv"),
                    ("IIF files", "*.iif"),
                    ("Web Connect / OFX", "*.qbo *.ofx"),
                    ("CSV files", "*.csv"),
                    ("All files", "*.*"),
                ])
            if not path:
                return
            chosen["path"] = path
            file_lbl.config(text=os.path.basename(path))
            fmt_lbl.config(text=self._qb_detect_format(path))
            err.config(text="")
            err.pack_forget()

        def cont():
            if not chosen["path"]:
                err.config(text="Choose a file to continue.")
                err.pack(anchor="w", pady=(8, 0))
                return
            win.destroy()
            self._quickbooks_scope(chosen["path"])

        def cancel():
            win.destroy()

        choose_row = tk.Frame(f, bg=DLG_BG)
        choose_row.pack(fill="x", pady=(10, 0))
        _dlg_button(choose_row, "Choose file\u2026", choose).pack(side="left")

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Continue", cont, primary=True).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", cancel)
        self._center_dialog(win)
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _quickbooks_scope(self, path):
        """Second card of the QuickBooks import: choose what to bring in.

        Checkboxes for the chart of accounts, customers & vendors, and
        transactions, plus a date range. 'Pull data' confirms the choices but,
        in this slice, imports nothing -- the file parser and the staged
        Imports review come next. Nothing here changes the open book.
        """
        win = tk.Toplevel(self)
        win.title("Pull data from QuickBooks")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.resizable(False, False)

        f = tk.Frame(win, bg=DLG_BG)
        f.pack(fill="both", expand=True, padx=24, pady=20)
        _dlg_label(f, "What to import", title=True).pack(anchor="w")
        _dlg_label(f, "Source: " + os.path.basename(path), dim=True,
                   wrap=430).pack(anchor="w", pady=(4, 12))

        want_accounts = tk.BooleanVar(value=True)
        want_contacts = tk.BooleanVar(value=True)
        want_txns = tk.BooleanVar(value=True)
        _dlg_check(f, "Chart of accounts", want_accounts).pack(
            anchor="w", fill="x", pady=(0, 4))
        _dlg_check(f, "Customers & vendors", want_contacts).pack(
            anchor="w", fill="x", pady=(0, 4))
        _dlg_check(f, "Transactions", want_txns).pack(
            anchor="w", fill="x", pady=(0, 4))

        date_row = tk.Frame(f, bg=DLG_BG)
        date_row.pack(fill="x", pady=(12, 0))
        _dlg_label(date_row, "Date range:").pack(side="left")
        from_e = _dlg_entry(date_row, width=12)
        from_e.insert(0, "2025-01-01")
        from_e.pack(side="left", padx=(8, 4), ipady=2)
        _dlg_label(date_row, "to").pack(side="left")
        to_e = _dlg_entry(date_row, width=12)
        to_e.insert(0, "today")
        to_e.pack(side="left", padx=(4, 0), ipady=2)

        def pull():
            picks = [name for name, var in (
                ("accounts", want_accounts),
                ("customers & vendors", want_contacts),
                ("transactions", want_txns)) if var.get()]
            if not picks:
                messagebox.showinfo(
                    "Nothing selected",
                    "Tick at least one kind of data to import.", parent=win)
                return
            win.destroy()
            # Slice 1 stops here on purpose: the file parser and the staged
            # Imports review are the next slices. Nothing is changed yet.
            messagebox.showinfo(
                "Not wired up yet",
                "Reading the file isn't connected yet -- that is the next "
                "step. Nothing was imported.\n\nWould import: "
                + ", ".join(picks) + ".",
                parent=self)
            self.set_status(
                "QuickBooks import: reading the file isn't wired up yet "
                "(coming next).", kind="info")

        def cancel():
            win.destroy()

        btns = tk.Frame(f, bg=DLG_BG)
        btns.pack(fill="x", pady=(16, 0))
        _dlg_button(btns, "Cancel", cancel).pack(side="right", padx=(8, 0))
        _dlg_button(btns, "Pull data", pull, primary=True).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", cancel)
        self._center_dialog(win)
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _manage_books(self):
        """The 'Your sets of books' manager.

        Most users keep one set of books, but the same program can hold a
        separate business and personal set on one computer. This is the one
        place to switch between them, start a new set, or remove one -- and
        it always shows each file's exact location on disk, so a file is
        never hard to find if it must be deleted by hand.
        """
        if self.mode == "client":
            messagebox.showinfo(
                "Connected to a host",
                "You are connected to a host, so these are not books on this "
                "computer. Sign out first to open books stored here.")
            return
        win = tk.Toplevel(self)
        win.title("Your sets of books")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.transient(self)
        win.geometry("780x480")

        _dlg_label(win, "Your sets of books", title=True).pack(
            anchor="w", padx=18, pady=(16, 2))
        _dlg_label(win,
                   "Each set of books is a separate file on this computer "
                   "\u2014 for example one for your business and one for "
                   "personal use. Select one and choose Open to switch to it. "
                   "The file's exact location is shown below so you can always "
                   "find it.", dim=True, wrap=730).pack(
                       anchor="w", padx=18, pady=(0, 10))

        cols = ("type", "file")
        tree = ttk.Treeview(win, columns=cols, show="tree headings",
                            height=10)
        tree.heading("#0", text="Name")
        tree.heading("type", text="Type")
        tree.heading("file", text="File")
        tree.column("#0", width=280, stretch=False)
        tree.column("type", width=90, anchor="w", stretch=False)
        tree.column("file", width=380, anchor="w")
        tree.pack(fill="both", expand=True, padx=18)

        path_var = tk.StringVar(value="")
        tk.Label(win, textvariable=path_var, bg=DLG_BG, fg=DLG_DIM,
                 font=FONT, wraplength=730, justify="left").pack(
            anchor="w", padx=18, pady=(8, 0))

        item_path = {}

        def populate():
            tree.delete(*tree.get_children())
            item_path.clear()
            files = sorted(glob.glob(os.path.join(paths.data_dir(), "*.db")))
            current = os.path.abspath(self.db_path) if self.db_path else None
            hosted = (self._host_state or {}).get("book")
            hosted = os.path.abspath(hosted) if hosted else None
            sel_iid = None
            for fp in files:
                name, kind = self._ledger_summary(fp)
                shown = name or "(not set up yet)"
                if os.path.abspath(fp) == current:
                    shown += "    \u2190 open now"
                    is_open = True
                elif os.path.abspath(fp) == hosted:
                    shown += "    \u2190 hosting"
                    is_open = False
                else:
                    is_open = False
                iid = tree.insert("", "end", text=shown,
                                  values=(kind.capitalize(),
                                          os.path.basename(fp)))
                item_path[iid] = fp
                if is_open:
                    sel_iid = iid
            if sel_iid:
                tree.selection_set(sel_iid)
                tree.see(sel_iid)
            on_select()

        def selected_path():
            sel = tree.selection()
            return item_path.get(sel[0]) if sel else None

        def on_select(_e=None):
            fp = selected_path()
            path_var.set(f"File location:   {fp}" if fp
                         else "Select a set of books to see where its file is.")

        tree.bind("<<TreeviewSelect>>", on_select)

        def do_open():
            fp = selected_path()
            if not fp:
                messagebox.showinfo("Choose a set of books",
                                    "Select one from the list first.",
                                    parent=win)
                return
            hosted = (self._host_state or {}).get("book")
            if hosted and os.path.abspath(fp) == os.path.abspath(hosted):
                # This set is being hosted on this computer, so the host
                # process holds the file. Don't open a second local copy --
                # sign in to the host over the loopback to get back into them.
                win.destroy()
                self._host_sign_in()
                return
            win.destroy()
            self._open_database(fp)

        def do_new():
            name = simpledialog.askstring(
                "New set of books",
                "Name for this new set of books\n(your business name, or "
                "your own name for personal books):", parent=win)
            if name is None:
                return
            name = name.strip()
            # Explicit choice, no silent default. Backing out here aborts the
            # new book (nothing is created) and leaves the manager open.
            kind = self._choose_book_kind(parent=win, allow_cancel=True)
            if kind is None:
                return
            fp = self._new_book_path(name)
            win.destroy()
            if self._open_database(fp):
                try:
                    profile.save_profile(self.conn, name=name, kind=kind)
                    self.tab_business.refresh()
                except Exception:
                    pass
                # Set up encryption for the brand-new book: business books
                # are always protected; personal books may choose.
                self._setup_protection(fp, kind)
                self._book_needs_setup = False
                self._refresh_open_badge()
                self.set_status(f"Created a new set of books: {name}",
                                kind="ok")
                # A new set of books gets the welcome walk-through.
                self._maybe_welcome()

        def do_delete():
            fp = selected_path()
            if not fp:
                messagebox.showinfo("Choose a set of books",
                                    "Select one from the list first.",
                                    parent=win)
                return
            name, _ = self._ledger_summary(fp)
            shown = name or os.path.basename(fp)
            if not messagebox.askyesno(
                    "Delete this set of books?",
                    f"Permanently delete this set of books?\n\n"
                    f"{shown}\n{fp}\n\n"
                    "A safety backup is saved first, but this removes the "
                    "working file. This cannot be easily undone. Continue?",
                    parent=win):
                return
            # Safety backup first, into that book's own Documents folder so
            # it can be found and recovered if the deletion was a mistake.
            safety = None
            try:
                bname, _ = self._ledger_summary(fp)
                safety = backup.backup(
                    db_path=fp,
                    backup_dir=backup.business_backup_dir(bname),
                    create=True)
            except Exception:
                safety = None
            deleting_current = bool(self.db_path) and (
                os.path.abspath(fp) == os.path.abspath(self.db_path))
            if deleting_current and self.conn:
                self.conn.close()
                self.conn = None
            try:
                os.remove(fp)
            except OSError as e:
                messagebox.showerror("Could not delete", str(e), parent=win)
                if deleting_current:
                    self._open_database(fp)  # file still there; reopen it
                return
            if deleting_current:
                msg = f"Deleted '{shown}'."
                if safety:
                    msg += f"  Safety backup saved to: {safety}"
                win.destroy()
                self.set_status(msg, kind="ok")
                # If other sets of books still exist, switch to one of them --
                # do NOT create or prompt for a brand-new set. Only when the
                # set just deleted was the LAST one do we start over (open a
                # blank default set and walk through business/personal +
                # encryption, so encryption is never skipped).
                remaining = sorted(
                    p for p in glob.glob(
                        os.path.join(paths.data_dir(), "*.db"))
                    if os.path.abspath(p) != os.path.abspath(fp))
                if remaining:
                    self._open_database(remaining[0])
                else:
                    self._open_database(database.DEFAULT_DB_PATH)
                    if not profile.has_profile(self.conn):
                        self._setup_fresh_books(self.db_path)
                    self._maybe_welcome()
                return
            msg = f"Deleted '{shown}'."
            if safety:
                msg += f"  Safety backup saved to: {safety}"
            self.set_status(msg, kind="ok")
            populate()

        def copy_path():
            fp = selected_path()
            if not fp:
                return
            self.clipboard_clear()
            self.clipboard_append(fp)
            self.set_status("File location copied to the clipboard.",
                            kind="ok")

        tree.bind("<Double-1>", lambda _e: do_open())

        # 'Copy file location' and 'Delete' are account tools, not sign-in
        # tools: neither is offered on the sign-in screen (no one has signed
        # in yet). They appear only once a book is open from the toolbar's
        # 'Manage books' -- always for a personal set (the owner's own), and
        # for a business set only when the signed-in person is the owner.
        show_book_tools = False
        if self.conn is not None and not self._locked_shown:
            try:
                _kind = profile.get_kind(self.conn)
            except Exception:
                _kind = ""
            if _kind == "personal":
                show_book_tools = True
            else:  # business or unknown -> owner only
                show_book_tools = self._can(roles.MANAGE_USERS)

        btns = tk.Frame(win, bg=DLG_BG)
        btns.pack(fill="x", padx=18, pady=14)
        _dlg_button(btns, "Open selected", do_open, primary=True).pack(
            side="left")
        _dlg_button(btns, "New set of books\u2026", do_new).pack(
            side="left", padx=6)
        if show_book_tools:
            _dlg_button(btns, "Copy file location", copy_path).pack(
                side="left", padx=6)
            _dlg_button(btns, "Delete selected\u2026", do_delete).pack(
                side="left", padx=6)
        def close_manager():
            win.destroy()
            # If the manager stood over an empty branded page (no book open),
            # return to the 3-button card so the person is never stranded.
            if (self._locked_shown and self.conn is None
                    and self.mode == "local"):
                self.after(40, lambda: self._back_to_entry(
                    "Sign in, open a set of books, or connect to a host."))

        win.protocol("WM_DELETE_WINDOW", close_manager)
        _dlg_button(btns, "Close", close_manager).pack(side="right")

        populate()
        win.lift()
        try:
            win.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # shared helpers used by the tabs
    # ------------------------------------------------------------------

    def set_status(self, message, kind="info"):
        colour = {"info": MUTED, "ok": OK, "error": ERROR}.get(kind, MUTED)
        self.status.config(text=message, fg=colour)

    def refresh_all(self):
        """Refresh every tab -- called after the data changes. Each tab is
        refreshed independently so that one tab raising (for example, a tab
        that has nothing to show in client mode) cannot stop the others."""
        for tab in (self.tab_entry, self.tab_journal, self.tab_reports,
                    self.tab_reconcile, self.tab_accounts, self.tab_backup,
                    self.tab_security, self.tab_sharing, self.tab_business):
            if hasattr(tab, "refresh"):
                try:
                    tab.refresh()
                except Exception:
                    pass

    def _on_tab_changed(self, event):
        idx = self.tabs.index(self.tabs.select())
        tab = (self.tab_entry, self.tab_journal, self.tab_reports,
               self.tab_reconcile, self.tab_accounts, self.tab_backup,
               self.tab_security, self.tab_sharing, self.tab_business)[idx]
        if hasattr(tab, "refresh"):
            tab.refresh()

    def _show_about(self):
        """Pop up the About window: the program's own attribution."""
        win = tk.Toplevel(self)
        win.title("About Ledger")
        win.configure(bg=DLG_BG)
        self._dialog_border(win)
        win.resizable(False, False)
        win.transient(self)

        tk.Label(win, text="Ledger", bg=DLG_BG, fg=DLG_TXT,
                 font=FONT_BIG).pack(pady=(20, 4))
        tk.Label(win, text=about.attribution_line(), bg=DLG_BG, fg=DLG_TXT,
                 font=FONT_BOLD).pack()

        # Anchor the buttons to the bottom FIRST so they always keep their full
        # height, then let the body fill the space above. The window is left to
        # size itself to its contents (no fixed geometry): a fixed 460x440 was
        # too short once the system font or attribution text ran a little
        # taller, which pushed this row past the bottom edge and clipped the
        # button text. Auto-sizing fits the buttons every time.
        btnrow = tk.Frame(win, bg=DLG_BG)
        btnrow.pack(side="bottom", pady=(8, 16))
        _dlg_button(btnrow, "Show the welcome tour again",
                    lambda: (win.destroy(), self._show_welcome())).pack(
                        side="left", padx=(0, 8))
        _dlg_button(btnrow, "Close", win.destroy, primary=True).pack(
            side="left")

        body = tk.Message(win, text=about.about_text(), bg=DLG_BG,
                          fg=DLG_DIM, font=FONT, width=380, justify="left")
        body.pack(padx=24, pady=16)

        self._center_dialog(win)

    # ------------------------------------------------------------------
    # First-run welcome tour
    # ------------------------------------------------------------------
    #
    # A short, skippable overlay shown the very first time Ledger is
    # opened. It orients a new user (the program is written with older and
    # first-time users in mind) to the tabs and the built-in Help, in no
    # more than three pages. After the first time it stays out of the way,
    # but can always be reopened from the About window.

    # The three pages. Kept plain-spoken on purpose -- no jargon.
    WELCOME_PAGES = [
        ("Welcome to Ledger",
         "Accounting for both your business and personal use.\n\n"
         "Let's take a quick walk through the basics \u2014 the tabs you'll "
         "use, the built-in help, and keeping business and personal books "
         "apart. It only takes a minute."),
        ("Moving around: the tabs",
         "Click a tab along the top to move around. You'll spend most of "
         "your time on Record Entry, where you log money in and out."),
        ("Help is always close by",
         "On the Record Entry screen, the Help panel on the right explains "
         "each task in plain words \u2014 look there whenever you need a "
         "reminder."),
        ("Business and personal, side by side",
         "You can keep a separate set of books for your business and for "
         "personal use. The \"Switch books\" button at the top right moves "
         "between them, starts a new set, and shows where each file is "
         "saved."),
        ("Your work is kept safe",
         "Save a backup whenever you like from the Backup tab \u2014 and if "
         "you forget, or would rather not, Ledger saves one for you "
         "automatically when you close. Your work is never lost. Backups "
         "sit in your Documents folder, kept in two places (\"Manual "
         "Backups\" and \"Automatic Backups\") so a copy survives even if "
         "one is removed."),
    ]

    def _welcome_dismissed(self):
        """Whether the welcome has been turned off for THIS set of books.
        It is stored inside the book itself, so every new set of books still
        shows the tour, and silencing one set never affects the others."""
        if not self.conn:
            return False
        try:
            return database.get_setting(
                self.conn, "welcome_dismissed", "0") == "1"
        except Exception:
            return False

    def _dismiss_welcome_forever(self):
        """Turn the welcome off for the open set of books only."""
        try:
            database.set_setting(self.conn, "welcome_dismissed", "1")
        except Exception:
            pass  # a nicety; if it can't be written, no harm done

    def _maybe_welcome(self):
        """Show the welcome tour for a brand-new set of books -- unless the
        user has told us they've used Ledger before. This runs for the
        first ever run, for each 'New set of books', and for the fresh book
        created after deleting the only one."""
        show = getattr(self, "_opened_new", False) and not self._welcome_dismissed()
        self._opened_new = False
        if show:
            self._show_welcome()

    def _show_welcome(self):
        """Build and show the welcome overlay. Called automatically for a
        new set of books, or on demand from the About window. Each page has
        a simple drawn illustration so the words can stay short."""
        # A lighter slate-navy than the very dark header -- easier on the
        # eye while still keeping white text crisp.
        WBG = "#34466e"          # window / panel background
        TXT = "#eef1f6"          # main light text
        DIM = "#b6c2da"          # muted light text (step indicator, captions)
        BTN = "#46597f"          # secondary buttons (lighter than the panel)
        BTN_ACTIVE = "#566a92"
        PANEL2 = "#3f5279"       # a slightly lighter block, for the mock screen
        LINE = "#7f90b5"         # faint "writing" lines in the mock screen

        win = tk.Toplevel(self)
        win.title("Welcome to Ledger by " + about.builder_name())
        win.configure(bg=WBG)
        self._dialog_border(win)
        win.resizable(False, False)
        win.transient(self)
        # Stay hidden while we build, measure every page, and position the
        # window. Otherwise the user sees it flit through all the pages as it
        # sizes itself and then jump into place -- the "jumpy" load. We show
        # it once, fully formed, at the end (deiconify below).
        win.withdraw()
        win._imgs = []           # keep image references alive

        heading_font = (FONT[0], 17, "bold")
        body_font = (FONT[0], 13)
        step_font = (FONT[0], 10)

        heading_box = tk.Frame(win, bg=WBG)
        heading_box.pack(side="top", fill="x", padx=34, pady=(24, 8))
        heading = tk.Label(heading_box, bg=WBG, fg=ACCENT_TEXT,
                           font=heading_font, justify="center",
                           anchor="center")
        heading.pack(fill="both", expand=True)

        nav = tk.Frame(win, bg=WBG)
        nav.pack(side="bottom", fill="x", padx=34, pady=(10, 22))

        step = tk.Label(win, bg=WBG, fg=DIM, font=step_font)
        step.pack(side="bottom", anchor="w", padx=34, pady=(0, 4))

        # The illustration area. A fixed height keeps every page the same
        # size; each page draws its own picture here.
        CANVAS_W, CANVAS_H = 520, 188
        canvas = tk.Canvas(win, width=CANVAS_W, height=CANVAS_H, bg=WBG,
                           highlightthickness=0, bd=0)
        canvas.pack(side="top", pady=(2, 4))

        body_box = tk.Frame(win, bg=WBG)
        body_box.pack(side="top", fill="x", padx=34, pady=(2, 8))
        body = tk.Label(body_box, bg=WBG, fg=TXT, font=body_font,
                        justify="left", anchor="nw", wraplength=500)
        body.pack(fill="both", expand=True)

        # -- drawing helpers ------------------------------------------------
        def round_rect(x1, y1, x2, y2, r, **kw):
            pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
                   x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
                   x1, y1 + r, x1, y1]
            return canvas.create_polygon(pts, smooth=True, **kw)

        def _usable(img):
            """True only if the image really decoded into something we can
            show. Some Tk builds hand back an image that reports a size but
            renders blank; sampling a few pixels catches that, so we can fall
            back to the drawn emblem instead of leaving an empty space."""
            try:
                if img is None or img.width() < 4 or img.height() < 4:
                    return False
                w, h = img.width(), img.height()
                seen = set()
                for x, y in ((w // 2, h // 2), (w // 3, h // 2),
                             (2 * w // 3, h // 2), (w // 2, h // 3)):
                    seen.add(img.get(x, y))
                # A real logo has variety; a blank image reads as one value.
                return len(seen) > 1
            except Exception:
                return False

        def load_logo_image():
            """Show the Ledger logo. A logo.png/logo.gif placed in the
            package folder wins (so it can be customised); otherwise the
            logo built into the program is used. Only if every option fails
            do we fall back to a drawn emblem."""
            here = os.path.dirname(os.path.abspath(__file__))
            for fname in ("logo.png", "logo.gif"):
                fp = os.path.join(here, fname)
                if os.path.exists(fp):
                    try:
                        img = tk.PhotoImage(file=fp)
                        if _usable(img):
                            win._imgs.append(img)
                            return img
                    except tk.TclError:
                        pass
            # The logo carried inside the program itself. GIF is tried first
            # because it loads on every Tk build; PNG-from-data is unreliable
            # on some Tk 8.6 builds (it can return a blank image), so it is
            # only a secondary attempt.
            for blob in (_LEDGER_LOGO_GIF_B64, _LEDGER_LOGO_PNG_B64):
                try:
                    img = tk.PhotoImage(data=blob)
                    if _usable(img):
                        win._imgs.append(img)
                        return img
                except tk.TclError:
                    continue
            return None

        def draw_logo():
            cx = CANVAS_W // 2
            cy = CANVAS_H // 2 - 2
            # The Ledger icon, bundled as a file next to the program. It is
            # loaded from disk (not embedded data) and the path is given to
            # Tk with forward slashes -- on Windows a backslash path can be
            # misread by Tcl and the image then shows blank.
            here = os.path.dirname(os.path.abspath(__file__))
            for fname in ("ledger-icon.png", "ledger-icon.gif"):
                fp = os.path.join(here, fname).replace("\\", "/")
                if not os.path.exists(fp):
                    continue
                try:
                    img = tk.PhotoImage(file=fp)
                except tk.TclError:
                    continue
                if _usable(img):
                    win._imgs.append(img)
                    canvas.create_image(cx, cy, image=img)
                    return
            # Fallback only if the icon file is missing or unreadable, so the
            # panel is never empty.
            TILE = "#2e3d57"; MFRAME = HEADER_BG; SCREEN = "#eef1f6"
            LINES = "#aebccf"; INK = "#1e2a4a"

            # rounded app tile
            round_rect(cx - 66, cy - 66, cx + 66, cy + 66, 20,
                       fill=TILE, outline="")
            # monitor frame + light screen
            round_rect(cx - 52, cy - 56, cx + 52, cy + 24, 12,
                       fill=MFRAME, outline="")
            round_rect(cx - 43, cy - 48, cx + 43, cy + 15, 7,
                       fill=SCREEN, outline="")
            # stand
            canvas.create_rectangle(cx - 7, cy + 24, cx + 7, cy + 34,
                                    fill=MFRAME, outline="")
            round_rect(cx - 22, cy + 33, cx + 22, cy + 42, 4,
                       fill=MFRAME, outline="")

            # soft shadow under the book
            canvas.create_oval(cx - 30, cy + 2, cx + 30, cy + 11,
                               fill="#d9dde4", outline="")
            # open ledger: two pages meeting at a centre spine
            lpage = [cx - 2, cy - 33, cx - 33, cy - 38, cx - 34, cy - 6,
                     cx - 2, cy - 2]
            rpage = [cx + 2, cy - 33, cx + 33, cy - 38, cx + 34, cy - 6,
                     cx + 2, cy - 2]
            canvas.create_polygon(lpage, fill="#ffffff", outline=INK, width=2)
            canvas.create_polygon(rpage, fill="#ffffff", outline=INK, width=2)
            canvas.create_line(cx, cy - 33, cx, cy - 2, fill=INK, width=2)
            # ruled text lines on each page
            for k in range(5):
                yy = cy - 30 + k * 5
                canvas.create_line(cx - 29, yy, cx - 7, yy - 1,
                                   fill=LINES, width=2)
                canvas.create_line(cx + 7, yy - 1, cx + 29, yy,
                                   fill=LINES, width=2)
            # bronze check on the page
            canvas.create_line(cx + 9, cy - 11, cx + 14, cy - 6,
                               cx + 25, cy - 18, fill=ACCENT, width=3,
                               capstyle="round", joinstyle="round")

        def draw_pill_row(items, y, highlight=None):
            from tkinter import font as tkfont
            f = (FONT[0], 9, "bold")
            fnt = tkfont.Font(font=f)
            widths = [fnt.measure(t) + 26 for t in items]
            gap = 8
            total = sum(widths) + gap * (len(items) - 1)
            x = (CANVAS_W - total) // 2
            for t, wdt in zip(items, widths):
                hi = (t == highlight)
                round_rect(x, y, x + wdt, y + 28, 9,
                           fill=(ACCENT if hi else BTN),
                           outline=(ACCENT_ACTIVE if hi else "#5b6e94"),
                           width=2)
                canvas.create_text(x + wdt / 2, y + 14, text=t,
                                   fill=ACCENT_TEXT, font=f)
                x += wdt + gap

        def draw_tabs():
            canvas.create_text(CANVAS_W // 2, 16, text="Your tabs",
                               fill=DIM, font=(FONT[0], 10))
            draw_pill_row(["Record Entry", "Journal", "Reports", "Reconcile"],
                          36, highlight="Record Entry")
            draw_pill_row(["Accounts", "Backup", "Business Info"], 84)
            canvas.create_text(CANVAS_W // 2, 140,
                               text="Record Entry (highlighted) is where "
                                    "you'll work most.",
                               fill=TXT, font=(FONT[0], 10))

        def draw_help():
            # A little mock of the Record Entry screen: a wide form area on
            # the left and the Help panel highlighted on the right.
            top, bottom = 18, CANVAS_H - 30
            left, right = 70, CANVAS_W - 70
            split = left + int((right - left) * 0.60)
            # form area
            round_rect(left, top, split - 8, bottom, 8,
                       fill=PANEL2, outline="#5b6e94", width=2)
            for i in range(4):
                yy = top + 22 + i * 22
                canvas.create_line(left + 16, yy, split - 26, yy,
                                   fill=LINE, width=3)
            # help panel (highlighted)
            round_rect(split, top, right, bottom, 8,
                       fill=ACCENT, outline=ACCENT_ACTIVE, width=2)
            canvas.create_text((split + right) / 2, top + 16, text="Help",
                               fill=ACCENT_TEXT, font=(FONT[0], 11, "bold"))
            for i in range(4):
                yy = top + 34 + i * 16
                canvas.create_line(split + 14, yy, right - 14, yy,
                                   fill="#f0e2cf", width=2)
            canvas.create_text((split + right) / 2, bottom + 16,
                               text="\u2191 always here on the right",
                               fill=DIM, font=(FONT[0], 10))

        def draw_switch():
            # A mini header strip with the "Switch books" button highlighted,
            # and two tiles (Business / Personal) with a switch arrow between.
            cx = CANVAS_W // 2
            # header strip
            round_rect(40, 8, CANVAS_W - 40, 42, 8,
                       fill=HEADER_BG, outline="#2b3a5c", width=1)
            canvas.create_text(58, 25, text="Ledger", anchor="w",
                               fill=ACCENT_TEXT, font=(FONT[0], 11, "bold"))
            # the highlighted Switch books button (top right, like the app)
            round_rect(CANVAS_W - 170, 14, CANVAS_W - 50, 36, 7,
                       fill=ACCENT, outline=ACCENT_ACTIVE, width=2)
            canvas.create_text(CANVAS_W - 110, 25, text="Switch books\u2026",
                               fill=ACCENT_TEXT, font=(FONT[0], 9, "bold"))
            # two book tiles
            ty, by = 70, 150
            tw = 104
            for x, label in ((130, "Business"), (CANVAS_W - 130 - tw,
                                                 "Personal")):
                round_rect(x, ty, x + tw, by, 10, fill=PANEL2,
                           outline="#5b6e94", width=2)
                canvas.create_rectangle(x + tw / 2 - 20, ty + 22,
                                        x + tw / 2 + 20, ty + 50,
                                        fill="#eef2f7", outline="#5b6e94")
                canvas.create_line(x + tw / 2, ty + 22, x + tw / 2, ty + 50,
                                   fill="#5b6e94")
                canvas.create_text(x + tw / 2, by - 16, text=label,
                                   fill=TXT, font=(FONT[0], 11, "bold"))
            # switch arrows between the two tiles
            canvas.create_text(cx, 100, text="\u21c4", fill=ACCENT,
                               font=(FONT[0], 26, "bold"))
            canvas.create_text(cx, by + 20, text="switch any time",
                               fill=DIM, font=(FONT[0], 10))

        def draw_backup():
            # Two "folder" tiles -- Manual and Automatic -- with a tick
            # between them, picturing the two places backups are kept.
            cx = CANVAS_W // 2
            tw, th = 150, 92
            ty = 50
            for x, label in ((cx - tw - 20, "Manual"),
                             (cx + 20, "Automatic")):
                # folder tab, then folder body
                round_rect(x + 12, ty - 12, x + 64, ty + 6, 6,
                           fill=PANEL2, outline="")
                round_rect(x, ty, x + tw, ty + th, 12,
                           fill=PANEL2, outline="#5b6e94", width=2)
                # a few "document" lines inside
                for k in range(3):
                    yy = ty + 26 + k * 17
                    canvas.create_line(x + 20, yy, x + tw - 20, yy,
                                       fill=LINE, width=3)
                canvas.create_text(x + tw / 2, ty + th + 18,
                                   text=label + " Backups",
                                   fill=TXT, font=(FONT[0], 11, "bold"))
            # a brass tick in the gap between the two folders
            canvas.create_text(cx, ty + th / 2, text="\u2713",
                               fill=ACCENT, font=(FONT[0], 30, "bold"))
            canvas.create_text(cx, 22,
                               text="saved automatically when you close",
                               fill=DIM, font=(FONT[0], 10))

        page_visual = {0: draw_logo, 1: draw_tabs, 2: draw_help,
                       3: draw_switch, 4: draw_backup}

        state = {"i": 0}

        def close():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

        def render():
            i = state["i"]
            title, text = self.WELCOME_PAGES[i]
            heading.config(text=title)
            body.config(text=text)
            step.config(text=f"Step {i + 1} of {len(self.WELCOME_PAGES)}")
            back_btn.config(state=("normal" if i > 0 else "disabled"))
            last = (i == len(self.WELCOME_PAGES) - 1)
            next_btn.config(text="Start" if last else "Next")
            canvas.delete("all")
            draw = page_visual.get(i)
            if draw:
                try:
                    draw()
                except Exception:
                    pass

        def go_next():
            if state["i"] >= len(self.WELCOME_PAGES) - 1:
                close()
            else:
                state["i"] += 1
                render()

        def go_back():
            if state["i"] > 0:
                state["i"] -= 1
                render()

        def not_first_time():
            # The user already knows Ledger: stop the tour from popping up
            # on its own for future new books. Still reopenable from About.
            self._dismiss_welcome_forever()
            close()

        # Left: a one-time opt-out. Right: Back / Next (Start on the last
        # page). Brass for the primary action; lighter slate for the rest.
        tk.Button(nav, text="I have used Ledger before",
                  command=not_first_time, font=step_font,
                  bg=BTN, fg=ACCENT_TEXT, relief="flat",
                  activebackground=BTN_ACTIVE,
                  activeforeground=ACCENT_TEXT, padx=12, pady=4).pack(
                      side="left")
        next_btn = tk.Button(nav, text="Next", command=go_next,
                             font=FONT_BOLD, padx=20, pady=6,
                             bg=ACCENT, fg=ACCENT_TEXT,
                             activebackground=ACCENT_ACTIVE,
                             activeforeground=ACCENT_TEXT,
                             relief="flat")
        next_btn.pack(side="right")
        back_btn = tk.Button(nav, text="Back", command=go_back, font=FONT,
                             padx=16, pady=6, bg=BTN, fg=ACCENT_TEXT,
                             relief="flat", activebackground=BTN_ACTIVE,
                             activeforeground=ACCENT_TEXT,
                             disabledforeground="#6f7ea0")
        back_btn.pack(side="right", padx=(0, 8))

        # Decide the window width FIRST so wrapped text always fits inside
        # it. Floor at 600; widen only if the button row (which can grow with
        # translated/!larger fonts) needs more room.
        win.update_idletasks()
        W = max(600, min(nav.winfo_reqwidth() + 2 * 34, 720))
        inner = W - 2 * 34
        heading.config(wraplength=inner - 24)
        body.config(wraplength=inner - 44)

        # Reserve fixed heights for the heading and body, sized to the
        # tallest page. With these locked, every page asks for exactly the
        # same overall size, so the window never grows or shrinks and the
        # Back / Next buttons stay in one spot instead of jumping as you
        # click through.
        max_head_h = max_body_h = 0
        for title, text in self.WELCOME_PAGES:
            heading.config(text=title)
            body.config(text=text)
            win.update_idletasks()
            max_head_h = max(max_head_h, heading.winfo_reqheight())
            max_body_h = max(max_body_h, body.winfo_reqheight())
        heading_box.configure(height=max_head_h)
        heading_box.pack_propagate(False)
        body_box.configure(height=max_body_h)
        body_box.pack_propagate(False)

        state["i"] = 0
        render()

        win.update_idletasks()
        H = win.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() - W) // 2
        py = self.winfo_rooty() + (self.winfo_height() - H) // 3
        win.geometry(f"{W}x{H}+{max(px, 0)}+{max(py, 0)}")
        # Lock the size hard. resizable() alone let some window managers
        # shrink the window to its content -- which clipped the text on the
        # right and squeezed the button row. Pinning min == max == our size
        # stops that everywhere.
        win.minsize(W, H)
        win.maxsize(W, H)
        win.protocol("WM_DELETE_WINDOW", close)
        # Fully built, sized and positioned now -- reveal it in one go.
        win.deiconify()
        win.lift()
        try:
            win.grab_set()   # keep focus on the tour while it is open
        except tk.TclError:
            pass

    def account_choices(self):
        """A list of 'CODE  Name' strings for dropdowns, active accounts."""
        if not self.gateway:
            return []
        try:
            rows = self.gateway.list_accounts(include_inactive=False)
        except gateway.GatewayError:
            return []
        return [f"{r['code']}  {r['name']}" for r in rows]

    @staticmethod
    def code_from_choice(choice):
        """Pull the account code back out of a 'CODE  Name' string."""
        return choice.split()[0] if choice else ""


# ----------------------------------------------------------------------
# Help system: a small markdown subset rendered into a side panel
# ----------------------------------------------------------------------

# Light amber for the "check with your tax expert" callout boxes.
CALLOUT_BG = "#fdf3e0"
CALLOUT_FG = "#7a4f0a"


def _load_help_text():
    """Read the help content markdown that ships with the program."""
    path = os.path.join(os.path.dirname(__file__), "help_content.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "# Help\nHelp content could not be loaded."


def _parse_help_sections(text):
    """Split the help markdown into (title, body_lines) sections, one per
    top-level '# ' heading. Order is preserved."""
    sections = []
    title = None
    body = []
    for line in text.splitlines():
        if line.startswith("# "):
            if title is not None:
                sections.append((title, body))
            title = line[2:].strip()
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, body))
    return sections


def _split_subsections(lines):
    """Split a section body into the intro (everything before the first
    '## ' heading) and a list of (subtitle, sub_lines) for each '## '
    sub-heading. This drives the second, nested level of the help
    accordion -- each '## ' becomes its own collapsible sub-section."""
    intro, subs = [], []
    cur_title, cur = None, []
    for line in lines:
        if line.startswith("## "):
            if cur_title is None:
                intro = cur
            else:
                subs.append((cur_title, cur))
            cur_title, cur = line[3:].strip(), []
        else:
            cur.append(line)
    if cur_title is None:
        intro = cur
    else:
        subs.append((cur_title, cur))
    return intro, subs


def _centered(parent, padx=16, pady=14, fill_y=False):
    """Return a content frame centred horizontally in `parent`. Empty
    weighted columns on each side absorb the extra width, so fixed-width
    content sits as a balanced 'page' on a wide or maximised window
    instead of being shoved to the left. With fill_y=True the content
    also stretches to the full height (for tabs with a tall area such as
    a report or comparison panel); otherwise it stays top-aligned."""
    host = ttk.Frame(parent)
    host.pack(fill="both", expand=True)
    host.grid_columnconfigure(0, weight=1)
    host.grid_columnconfigure(2, weight=1)
    sticky = "n"
    if fill_y:
        host.grid_rowconfigure(0, weight=1)
        sticky = "nsew"
    inner = ttk.Frame(host)
    inner.grid(row=0, column=1, sticky=sticky, padx=padx, pady=pady)
    return inner


class HelpPanel(ttk.Frame):
    """A static help panel that sits beside the entry form.

    The content is a single markdown file (help_content.md) split into
    sections shown as an accordion: click a header to open it, and only
    one section is open at a time. It renders a deliberately small
    markdown subset -- headings, paragraphs, bullets, a monospaced
    table, and 'tax expert' callouts -- so it needs no third-party
    dependency. The panel is always visible (no hide control), so the
    reference is simply there whenever the user wants it.
    """

    WIDTH = 340

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.sections = _parse_help_sections(_load_help_text())
        self.open_index = None
        self.section_widgets = []
        self._build()
        self.panel.pack(fill="both", expand=True)

    # -- layout -------------------------------------------------------
    def _build(self):
        # A fixed-width header strip plus a scrollable accordion.
        self.panel = ttk.Frame(self, width=self.WIDTH)
        self.panel.pack_propagate(False)

        head = tk.Frame(self.panel, bg=HEADER_BG, height=34)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="  Help", bg=HEADER_BG, fg=ACCENT_TEXT,
                 font=FONT_BOLD).pack(side="left")

        body = ttk.Frame(self.panel)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical",
                            command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        # Keep the content exactly the canvas width so nothing (text or a
        # long heading) spills past the scrollbar; headings too long for one
        # line wrap instead of being clipped on the right.
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._win, width=e.width))

        for idx, (title, body_lines) in enumerate(self.sections):
            sec = ttk.Frame(self.inner, style="Panel.TFrame")
            sec.pack(fill="x")
            btn = tk.Button(sec, text="\u25B8  " + title, anchor="w",
                            font=FONT_BOLD, relief="flat", bg=PANEL,
                            fg=HEADER_BG, activebackground="#eef2f7",
                            bd=0, padx=10, pady=8, cursor="hand2",
                            justify="left", wraplength=self.WIDTH - 38,
                            command=lambda i=idx: self._toggle(i))
            btn.pack(fill="x")
            ttk.Separator(sec, orient="horizontal").pack(fill="x")
            content = ttk.Frame(sec, style="Panel.TFrame")
            self.section_widgets.append(
                {"btn": btn, "content": content, "rendered": False,
                 "body": body_lines, "title": title})

    # -- accordion ----------------------------------------------------
    def _toggle(self, i):
        if self.open_index == i:
            self._close(i)
            self.open_index = None
            return
        if self.open_index is not None:
            self._close(self.open_index)
        self._open(i)
        self.open_index = i

    def _open(self, i):
        sw = self.section_widgets[i]
        if not sw["rendered"]:
            intro, subs = _split_subsections(sw["body"])
            self._render_body(sw["content"], intro)
            sw["subs"] = []        # close callback for each sub-section
            sw["open_sub"] = None  # index of the sub-section open right now
            for stitle, slines in subs:
                self._build_subsection(sw, stitle, slines)
            sw["rendered"] = True
        sw["content"].pack(fill="x", padx=10, pady=(2, 10))
        sw["btn"].config(text="\u25BE  " + sw["title"])
        self.after(10, lambda: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))

    def _close(self, i):
        sw = self.section_widgets[i]
        # Collapse any open sub-section too, so the section reopens tidy
        # rather than with a stray sub still expanded.
        prev = sw.get("open_sub")
        if prev is not None:
            sw["subs"][prev]()
            sw["open_sub"] = None
        sw["content"].pack_forget()
        sw["btn"].config(text="\u25B8  " + sw["title"])

    def _build_subsection(self, sw, title, lines):
        """A collapsible sub-section nested under an open section. Indented
        and shown in brass so the two levels read as a clear hierarchy.
        Only one sub-section is open at a time: opening one closes the
        sibling that was open, matching the top-level accordion."""
        parent = sw["content"]
        sub = ttk.Frame(parent, style="Panel.TFrame")
        sub.pack(fill="x", pady=(1, 0))
        content = ttk.Frame(sub, style="Panel.TFrame")
        st = {"open": False, "rendered": False}
        my_index = len(sw["subs"])  # this sub's slot in sw["subs"]
        btn = tk.Button(sub, text="\u25B8  " + title, anchor="w",
                        font=FONT_BOLD, relief="flat", bg=PANEL, fg=ACCENT,
                        activebackground="#eef2f7", bd=0, padx=18, pady=5,
                        cursor="hand2", justify="left",
                        wraplength=self.WIDTH - 54)

        def close():
            if st["open"]:
                content.pack_forget()
                btn.config(text="\u25B8  " + title)
                st["open"] = False

        def open_():
            if not st["rendered"]:
                self._render_body(content, lines, self.WIDTH - 78)
                st["rendered"] = True
            content.pack(fill="x", padx=(22, 4), pady=(0, 6))
            btn.config(text="\u25BE  " + title)
            st["open"] = True

        def toggle():
            if st["open"]:
                close()
                sw["open_sub"] = None
            else:
                prev = sw["open_sub"]
                if prev is not None and prev != my_index:
                    sw["subs"][prev]()  # close the sibling that was open
                open_()
                sw["open_sub"] = my_index
            self.after(10, lambda: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))

        sw["subs"].append(close)  # register so siblings can close this one
        btn.config(command=toggle)
        btn.pack(fill="x")

    # -- markdown subset rendering -----------------------------------
    def _render_body(self, parent, lines, wrap=None):
        # Default wrap leaves a clear margin before the scrollbar. Nested
        # sub-sections pass a narrower wrap to account for their indent so
        # their text does not run under the scrollbar.
        if wrap is None:
            wrap = self.WIDTH - 52
        para = []

        def flush():
            text = " ".join(s.strip() for s in para).strip().replace("**", "")
            para.clear()
            if text:
                ttk.Label(parent, text=text, style="Panel.TLabel",
                          wraplength=wrap, justify="left").pack(
                    anchor="w", fill="x", pady=(0, 6))

        i, n = 0, len(lines)
        while i < n:
            s = lines[i].strip()
            if not s:
                flush()
                i += 1
                continue
            if s.startswith("## "):
                flush()
                ttk.Label(parent, text=s[3:].strip(), style="Panel.TLabel",
                          font=FONT_BOLD, wraplength=wrap,
                          justify="left").pack(anchor="w", pady=(4, 3))
                i += 1
                continue
            if s.startswith("|"):
                flush()
                tbl = []
                while i < n and lines[i].strip().startswith("|"):
                    tbl.append(lines[i].strip())
                    i += 1
                self._render_table(parent, tbl)
                continue
            if s.startswith(">"):
                flush()
                call = []
                while i < n and lines[i].strip().startswith(">"):
                    call.append(lines[i].strip().lstrip(">").strip())
                    i += 1
                text = " ".join(call).replace("**", "")
                tk.Label(parent, text=text, font=FONT, wraplength=wrap,
                         justify="left", bg=CALLOUT_BG, fg=CALLOUT_FG,
                         padx=8, pady=6, anchor="w").pack(
                    anchor="w", fill="x", pady=(4, 8))
                continue
            if s.startswith("- "):
                flush()
                ttk.Label(parent, text="\u2022  " + s[2:].replace("**", ""),
                          style="Panel.TLabel", wraplength=wrap,
                          justify="left").pack(anchor="w", fill="x",
                                               pady=(0, 2))
                i += 1
                continue
            para.append(s)
            i += 1
        flush()

    def _render_table(self, parent, rows):
        parsed = []
        for r in rows:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if cells and all(set(c) <= set("-: ") for c in cells):
                continue  # the |---|---| separator row
            parsed.append(cells)
        if not parsed:
            return
        ncol = max(len(r) for r in parsed)
        widths = [0] * ncol
        for r in parsed:
            for j, c in enumerate(r):
                widths[j] = max(widths[j], len(c))
        out = []
        for r in parsed:
            cells = [(r[j] if j < len(r) else "").ljust(widths[j])
                     for j in range(ncol)]
            out.append("  ".join(cells).rstrip())
        if len(out) > 1:
            out.insert(1, "-" * max(len(line) for line in out))
        tk.Label(parent, text="\n".join(out), font=FONT_MONO, bg=PANEL,
                 justify="left", anchor="w").pack(anchor="w", pady=(2, 8))


class RecentPanel(ttk.Frame):
    """A quiet, read-only list of the most recently recorded entries,
    shown beside the entry form. It gives immediate confirmation that an
    entry saved, plus a little context, without the full Journal table.
    Deliberately minimal -- text on the plain background, no card, no
    grid -- so the main screen stays calm for a brand-new user (whose
    ledger is empty and who simply sees a one-line invitation)."""

    MAX_ITEMS = 6

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ttk.Label(self, text="Recently recorded",
                  font=FONT_BOLD).pack(anchor="w")
        self.body = ttk.Frame(self)
        self.body.pack(fill="x", pady=(6, 0))
        self.refresh()

    def refresh(self):
        for w in self.body.winfo_children():
            w.destroy()
        g = getattr(self.app, "gateway", None)
        entries = []
        if g:
            try:
                entries = g.list_entries()
            except Exception:
                entries = []
        if not entries:
            ttk.Label(self.body,
                      text="The entries you record will show up here, "
                           "newest first.",
                      style="Muted.TLabel", wraplength=300,
                      justify="left").pack(anchor="w")
            return
        for item in entries[:self.MAX_ITEMS]:
            e = item["entry"]
            amount = sum((ln["debit"] or 0) for ln in item["lines"])
            self._stub(e["description"] or "(no description)",
                       e["date"], amount)
        if len(entries) > self.MAX_ITEMS:
            ttk.Label(self.body, text="See all entries in the Journal tab.",
                      style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    def _stub(self, desc, date, amount):
        row = ttk.Frame(self.body)
        row.pack(anchor="w", pady=(7, 7))
        ttk.Label(row, text=desc, wraplength=320,
                  justify="left").pack(anchor="w")
        ttk.Label(row, text=f"{date}     {amount:,.2f}",
                  style="Muted.TLabel").pack(anchor="w", pady=(1, 0))
        ttk.Separator(row, orient="horizontal").pack(fill="x", pady=(7, 0))


# ----------------------------------------------------------------------
# Tab 1: Record an entry
# ----------------------------------------------------------------------

class EntryTab(ttk.Frame):
    """A form for recording a journal entry, with account dropdowns."""

    MAX_LINES = 8  # how many debit/credit rows to offer

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.line_widgets = []
        self._build()

    def _build(self):
        cluster = _centered(self, padx=0, pady=0)
        self._cluster = cluster
        wrap = ttk.Frame(cluster)
        wrap.pack(side="left", fill="y", anchor="n", padx=16, pady=14)

        ttk.Label(wrap, text="Record a journal entry",
                  style="Title.TLabel").grid(row=0, column=0, columnspan=4,
                                             sticky="w", pady=(0, 4))
        ttk.Label(wrap, text="Every entry must balance: total debits "
                             "must equal total credits.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=4,
                                             sticky="w", pady=(0, 12))

        # --- date / description / reference ---
        ttk.Label(wrap, text="Date").grid(row=2, column=0, sticky="w")
        self.date_var = tk.StringVar()
        date_entry = ttk.Entry(wrap, textvariable=self.date_var, width=16)
        date_entry.grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(wrap, text="(YYYY-MM-DD)",
                  style="Muted.TLabel").grid(row=2, column=2, sticky="w")

        ttk.Label(wrap, text="Description").grid(row=3, column=0, sticky="w")
        self.desc_var = tk.StringVar()
        ttk.Entry(wrap, textvariable=self.desc_var, width=48).grid(
            row=3, column=1, columnspan=3, sticky="we", pady=3)

        ttk.Label(wrap, text="Reference").grid(row=4, column=0, sticky="w")
        self.ref_var = tk.StringVar()
        ttk.Entry(wrap, textvariable=self.ref_var, width=24).grid(
            row=4, column=1, sticky="w", pady=3)
        ttk.Label(wrap, text="(optional: invoice or check number)",
                  style="Muted.TLabel").grid(row=4, column=2, columnspan=2,
                                             sticky="w")

        # --- line items header ---
        hdr = ttk.Frame(wrap)
        hdr.grid(row=5, column=0, columnspan=4, sticky="we", pady=(14, 2))
        ttk.Label(hdr, text="Account", width=34,
                  style="TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hdr, text="Debit", width=14).grid(row=0, column=1)
        ttk.Label(hdr, text="Credit", width=14).grid(row=0, column=2)

        # --- the line item rows ---
        self.lines_frame = ttk.Frame(wrap)
        self.lines_frame.grid(row=6, column=0, columnspan=4, sticky="we")
        for i in range(self.MAX_LINES):
            self._build_line_row(i)

        # --- running totals ---
        self.totals_var = tk.StringVar(value="Debits 0.00    Credits 0.00")
        self.totals_label = ttk.Label(wrap, textvariable=self.totals_var,
                                      style="TLabel", font=FONT_BOLD)
        self.totals_label.grid(row=7, column=0, columnspan=4, sticky="w",
                               pady=(10, 4))

        # --- buttons ---
        btns = ttk.Frame(wrap)
        btns.grid(row=8, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="Check balance",
                   command=self._update_totals).pack(side="left")
        ttk.Button(btns, text="Record entry",
                   style="Accent.TButton",
                   command=self._record).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear form",
                   command=self._clear).pack(side="left")

        # A hint area showing the everyday debit/credit patterns.
        hint = ("Common patterns:   "
                "Paid by customer -> Debit Checking, Credit Income      "
                "Paid a bill -> Debit Expense, Credit Checking      "
                "Sent an invoice -> Debit Accounts Receivable, Credit Income")
        ttk.Label(wrap, text=hint, style="Muted.TLabel",
                  wraplength=500, justify="left").grid(
            row=9, column=0, columnspan=4, sticky="w", pady=(16, 0))

        # Static help panel, set a little apart from the form. The form and
        # help move together as one centred block, so a full-screen window
        # shows balanced margins instead of a left-shoved form.
        #
        # Put about two and a half inches of breathing room between the
        # form and the help panel -- close enough to read as one unit, far
        # enough that the help doesn't feel like it's crowding the form.
        # winfo_fpixels('2.5i') converts that into pixels for this display;
        # we subtract the 16px the form already pads on its right so the
        # visible gap comes out to roughly two and a half inches. The block
        # stays centred as a whole.
        gap = max(48, int(self.winfo_fpixels("2.5i")) - 16)
        self.help = HelpPanel(self._cluster, self.app)
        self.help.pack(side="left", fill="y", pady=14, padx=(gap, 8))

    def _build_line_row(self, i):
        row = ttk.Frame(self.lines_frame)
        row.grid(row=i, column=0, sticky="we", pady=2)

        acct_var = tk.StringVar()
        acct_box = ttk.Combobox(row, textvariable=acct_var, width=32,
                                state="readonly", values=[])
        acct_box.grid(row=0, column=0, padx=(0, 8))

        debit_var = tk.StringVar()
        debit_entry = ttk.Entry(row, textvariable=debit_var, width=14)
        debit_entry.grid(row=0, column=1, padx=4)

        credit_var = tk.StringVar()
        credit_entry = ttk.Entry(row, textvariable=credit_var, width=14)
        credit_entry.grid(row=0, column=2, padx=4)

        # Recalculate totals whenever an amount changes.
        debit_var.trace_add("write", lambda *_: self._update_totals())
        credit_var.trace_add("write", lambda *_: self._update_totals())

        self.line_widgets.append({
            "account": acct_var, "account_box": acct_box,
            "debit": debit_var, "credit": credit_var,
        })

    @staticmethod
    def _parse_amount(text):
        """Turn a box's text into a number. Blank -> 0. Bad text -> None."""
        text = (text or "").strip().replace(",", "")
        if not text:
            return 0.0
        try:
            value = float(text)
        except ValueError:
            return None
        return value if value >= 0 else None

    def _update_totals(self):
        total_debit = 0.0
        total_credit = 0.0
        bad = False
        for lw in self.line_widgets:
            d = self._parse_amount(lw["debit"].get())
            c = self._parse_amount(lw["credit"].get())
            if d is None or c is None:
                bad = True
                continue
            total_debit += d
            total_credit += c

        if bad:
            self.totals_var.set("Some amounts are not valid numbers")
            self.totals_label.config(foreground=ERROR)
            return

        balanced = abs(total_debit - total_credit) < 0.005
        self.totals_var.set(
            f"Debits {total_debit:,.2f}    Credits {total_credit:,.2f}    "
            + ("BALANCED" if balanced else "not balanced yet"))
        self.totals_label.config(foreground=OK if balanced else ERROR)

    def _record(self):
        date_str = self.date_var.get().strip()
        desc = self.desc_var.get().strip()
        ref = self.ref_var.get().strip() or None

        lines = []
        for lw in self.line_widgets:
            choice = lw["account"].get()
            if not choice:
                continue
            code = self.app.code_from_choice(choice)
            d = self._parse_amount(lw["debit"].get())
            c = self._parse_amount(lw["credit"].get())
            if d is None or c is None:
                messagebox.showerror(
                    "Invalid amount",
                    "One of the amounts isn't a valid number. "
                    "Use digits only, e.g. 1500 or 1500.00.")
                return
            if d == 0 and c == 0:
                continue  # an empty line, just skip it
            lines.append({"code": code, "debit": d, "credit": c})

        if not lines:
            messagebox.showerror(
                "Nothing to record",
                "Add at least one debit line and one credit line.")
            return

        try:
            result = self.app.gateway.record_entry(
                date_str, desc, lines, reference=ref)
            entry_id = result["entry_id"]
        except gateway.GatewayError as e:
            messagebox.showerror("Could not record this entry", str(e))
            return

        self.app.set_status(f"Recorded entry #{entry_id}: {desc}", kind="ok")
        self._clear()
        self.app.refresh_all()

    def _clear(self):
        self.desc_var.set("")
        self.ref_var.set("")
        for lw in self.line_widgets:
            lw["account"].set("")
            lw["debit"].set("")
            lw["credit"].set("")
        self._update_totals()

    def refresh(self):
        """Reload account dropdowns (the chart may have changed)."""
        if not self.app.gateway:
            return
        choices = self.app.account_choices()
        for lw in self.line_widgets:
            current = lw["account"].get()
            lw["account_box"]["values"] = choices
            if current not in choices:
                lw["account"].set("")
        # Default the date box to the most recent date used, or today.
        if not self.date_var.get():
            from datetime import date
            self.date_var.set(date.today().isoformat())


# ----------------------------------------------------------------------
# Tab 2: Journal (list of entries)
# ----------------------------------------------------------------------

class JournalTab(ttk.Frame):
    """A scrollable list of journal entries, newest first."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=16, pady=14)

        top = ttk.Frame(wrap)
        top.pack(fill="x")
        ttk.Label(top, text="Journal entries",
                  style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Refresh",
                   command=self.refresh).pack(side="right")
        self.void_btn = ttk.Button(top, text="Void selected entry…",
                                   command=self._void_selected)
        self.void_btn.pack(side="right", padx=6)

        ttk.Label(wrap, text="The most recent entries are at the top. "
                             "Select one and use 'Void' to remove a "
                             "mistake.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        # A tree showing one row per line, grouped under each entry.
        columns = ("date", "account", "debit", "credit", "ref")
        self.tree = ttk.Treeview(wrap, columns=columns, show="tree headings",
                                 height=18)
        self.tree.heading("#0", text="Entry")
        self.tree.heading("date", text="Date")
        self.tree.heading("account", text="Account")
        self.tree.heading("debit", text="Debit")
        self.tree.heading("credit", text="Credit")
        self.tree.heading("ref", text="Reference")
        # Size the description and reference columns to match the input
        # fields on the Record Entry tab, so what you see while typing is
        # the same width as what you see here. The Description box there
        # is 48 characters wide and the Reference box is 24; we measure
        # those character counts in the same font the tree draws with so
        # the columns line up. (A small allowance is added to "#0" for
        # the tree's indent and the little open/close arrow.)
        from tkinter import font as tkfont
        cell_font = tkfont.Font(font=FONT)
        desc_w = cell_font.measure("0" * 48) + 28
        ref_w = cell_font.measure("0" * 24) + 12

        self.tree.column("#0", width=desc_w, minwidth=desc_w, stretch=False)
        self.tree.column("date", width=90, anchor="w", stretch=False)
        # The account column takes up any leftover width on a wide window,
        # which keeps the description and reference columns fixed at their
        # Record-Entry sizes.
        self.tree.column("account", width=230, anchor="w")
        self.tree.column("debit", width=100, anchor="e", stretch=False)
        self.tree.column("credit", width=100, anchor="e", stretch=False)
        self.tree.column("ref", width=ref_w, minwidth=ref_w, anchor="w",
                         stretch=False)

        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.app.gateway:
            return
        try:
            entries = self.app.gateway.list_entries()
        except gateway.GatewayError as e:
            self.app.set_status(f"Could not load the journal: {e}",
                                kind="error")
            return
        for item in entries:
            e = item["entry"]
            parent = self.tree.insert(
                "", "end",
                text=f"#{e['id']}  {e['description']}",
                values=(e["date"], "", "", "", e["reference"] or ""))
            for ln in item["lines"]:
                debit = f"{ln['debit']:,.2f}" if ln["debit"] else ""
                credit = f"{ln['credit']:,.2f}" if ln["credit"] else ""
                self.tree.insert(
                    parent, "end", text="",
                    values=("", f"{ln['code']}  {ln['name']}",
                            debit, credit, ""))
            self.tree.item(parent, open=True)

        # Role enforcement: voiding entries needs VOID_ENTRY (owner/manager).
        _set_enabled(self.void_btn, self.app._can(roles.VOID_ENTRY))

    def _void_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Nothing selected",
                "Click on an entry's top row first, then choose Void.")
            return
        item = sel[0]
        # Walk up to the parent entry row if a line was selected.
        parent = self.tree.parent(item)
        entry_row = parent if parent else item
        text = self.tree.item(entry_row, "text")  # like "#5  Description"
        if not text.startswith("#"):
            messagebox.showinfo("Select an entry",
                                "Please select an entry's top row.")
            return
        entry_id = int(text.split()[0][1:])

        if not messagebox.askyesno(
                "Void this entry?",
                f"Permanently remove entry {text}?\n\n"
                "This cannot be undone. (Your periodic backups would "
                "still have it.)"):
            return
        try:
            self.app.gateway.void_entry(entry_id)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not void", str(e))
            return
        self.app.set_status(f"Voided entry #{entry_id}", kind="ok")
        self.app.refresh_all()


# ----------------------------------------------------------------------
# Tab 3: Reports
# ----------------------------------------------------------------------

class ReportsTab(ttk.Frame):
    """Generates the four reports and shows them as clean text."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = _centered(self, fill_y=True)

        ttk.Label(wrap, text="Reports",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap, text="Pick a report and an optional date range. "
                             "Use 'Save to file…' to hand a copy to your "
                             "tax expert.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        controls = ttk.Frame(wrap)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Report:").pack(side="left")
        self.report_var = tk.StringVar(value="Trial Balance")
        report_box = ttk.Combobox(
            controls, textvariable=self.report_var, state="readonly",
            width=20,
            values=["Trial Balance", "Income Statement",
                    "Balance Sheet", "General Ledger"])
        report_box.pack(side="left", padx=(4, 14))

        ttk.Label(controls, text="From:").pack(side="left")
        self.start_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.start_var, width=12).pack(
            side="left", padx=4)
        ttk.Label(controls, text="To:").pack(side="left")
        self.end_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.end_var, width=12).pack(
            side="left", padx=4)
        ttk.Label(controls, text="(YYYY-MM-DD, optional)",
                  style="Muted.TLabel").pack(side="left", padx=(2, 0))

        btns = ttk.Frame(wrap)
        btns.pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Generate report", style="Accent.TButton",
                   command=self._generate).pack(side="left")
        ttk.Button(btns, text="Print…",
                   command=self._print).pack(side="left", padx=6)
        ttk.Button(btns, text="Save to file…",
                   command=self._save).pack(side="left", padx=6)

        # The report text area.
        text_frame = ttk.Frame(wrap)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, font=FONT_MONO, wrap="none",
                            bg=PANEL, relief="solid", bd=1,
                            padx=10, pady=10, width=96, height=24)
        vsb = ttk.Scrollbar(text_frame, orient="vertical",
                            command=self.text.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal",
                            command=self.text.xview)
        self.text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.text.configure(state="disabled")

    def _date_or_none(self, value):
        value = value.strip()
        return value or None

    def _generate(self):
        if not self.app.gateway:
            return
        g = self.app.gateway
        start = self._date_or_none(self.start_var.get())
        end = self._date_or_none(self.end_var.get())
        kind = self.report_var.get()

        try:
            # The business profile header goes at the top of every report.
            header = g.profile_header_lines()
            if kind == "Trial Balance":
                data = g.report("trial_balance", start=start, end=end)
                text = formatting.format_trial_balance(data, header)
            elif kind == "Income Statement":
                data = g.report("income_statement", start=start, end=end)
                text = formatting.format_income_statement(
                    data, header, personal=g.is_personal())
            elif kind == "Balance Sheet":
                data = g.report("balance_sheet", start=start, end=end)
                text = formatting.format_balance_sheet(data, header)
            else:  # General Ledger
                data = g.report("general_ledger", start=start, end=end)
                text = formatting.format_general_ledger(data, header)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not generate report", str(e))
            return
        except Exception as e:
            messagebox.showerror("Could not generate report", str(e))
            return

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self.app.set_status(f"Generated: {kind}", kind="ok")

    def _print(self):
        content = self.text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Nothing to print",
                                "Generate a report first.")
            return
        ok, message = printing.print_text(
            content,
            schedule_delete=lambda fn, secs: self.after(int(secs * 1000), fn))
        if ok:
            self.app.set_status("Report sent to the printer.", kind="ok")
        else:
            messagebox.showinfo(
                "Could not print",
                "The report could not be printed:\n\n" + message +
                "\n\nYou can use \u201cSave to file\u2026\u201d instead and "
                "print it from there.")

    def _save(self):
        content = self.text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Nothing to save",
                                "Generate a report first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save report",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w") as f:
                f.write(content + "\n")
        except OSError as e:
            messagebox.showerror("Could not save", str(e))
            return
        self.app.set_status(f"Saved report to {path}", kind="ok")

    def refresh(self):
        # Reports are generated on demand; nothing to preload.
        pass


# ----------------------------------------------------------------------
# Tab: Reconcile (compare the books against a bank statement)
# ----------------------------------------------------------------------

class ReconciliationTab(ttk.Frame):
    """
    Compare Ledger against a bank (or credit-card) statement.

    Deliberately framed as "money in / money out" with beginning and
    ending balances -- the four numbers a statement shows -- rather than
    debits and credits, so someone learning the books can check their
    work without thinking in accounting terms. It never changes the
    books; it only compares and reports.
    """

    FIELDS = (
        ("beginning", "Beginning"),
        ("money_in", "Money in"),
        ("money_out", "Money out"),
        ("ending", "Ending"),
    )

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.rows = {}          # account code -> {vars, status widget}
        self._built_codes = None
        self._last_report = ""  # text of the latest comparison, for saving
        self._build()

    def _build(self):
        wrap = _centered(self, fill_y=True)

        ttk.Label(wrap, text="Reconcile against your bank statement",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap,
                  text="Enter the figures from your bank or credit-card "
                       "statement, then compare them with Ledger. "
                       "Nothing here changes your books.",
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 10))

        # --- statement period ---
        controls = ttk.Frame(wrap)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Statement period   From:").pack(side="left")
        self.start_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.start_var, width=12).pack(
            side="left", padx=4)
        ttk.Label(controls, text="To:").pack(side="left")
        self.end_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.end_var, width=12).pack(
            side="left", padx=4)
        ttk.Label(controls, text="(YYYY-MM-DD)",
                  style="Muted.TLabel").pack(side="left", padx=(2, 0))

        # --- one shared grid holds the column headers AND the account
        # rows, so a header sits directly above its boxes. (Two separate
        # grids do not share column tracks and drift out of line.)
        self.grid_frame = ttk.Frame(wrap)
        self.grid_frame.pack(fill="x", pady=(6, 8))

        ttk.Label(self.grid_frame, text="Account", anchor="w",
                  font=FONT_BOLD).grid(row=0, column=0, sticky="w",
                                       padx=(0, 8), pady=(0, 2))
        for c, (_key, label) in enumerate(self.FIELDS, start=1):
            ttk.Label(self.grid_frame, text=label, anchor="center",
                      font=FONT_BOLD).grid(row=0, column=c, sticky="we",
                                           padx=3, pady=(0, 2))
        ttk.Label(self.grid_frame, text="Status", anchor="w",
                  font=FONT_BOLD).grid(row=0, column=5, sticky="w",
                                       padx=(10, 0), pady=(0, 2))
        # Make the four figure columns equal width and aligned.
        for c in range(1, 5):
            self.grid_frame.grid_columnconfigure(c, uniform="recon",
                                                 minsize=92)

        # --- buttons ---
        btns = ttk.Frame(wrap)
        btns.pack(fill="x", pady=(4, 8))
        self.compare_btn = ttk.Button(btns, text="Compare to Ledger",
                                      style="Accent.TButton",
                                      command=self._compare)
        self.compare_btn.pack(side="left")
        ttk.Button(btns, text="Clear figures",
                   command=self._clear).pack(side="left", padx=6)
        ttk.Button(btns, text="Save report\u2026",
                   command=self._save).pack(side="left")

        self.summary_var = tk.StringVar(value="")
        self.summary_label = ttk.Label(wrap, textvariable=self.summary_var,
                                       style="TLabel", font=FONT_BOLD)
        self.summary_label.pack(anchor="w", pady=(2, 6))

        # --- side-by-side comparison output ---
        text_frame = ttk.Frame(wrap)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, font=FONT_MONO, wrap="none",
                            bg=PANEL, relief="solid", bd=1,
                            padx=10, pady=10, height=12, width=92)
        vsb = ttk.Scrollbar(text_frame, orient="vertical",
                            command=self.text.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal",
                            command=self.text.xview)
        self.text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.text.tag_configure("good", foreground=OK)
        self.text.tag_configure("bad", foreground=ERROR)
        self.text.configure(state="disabled")

    def _build_rows(self, accts):
        """(Re)create one input row per asset/liability account, in the
        shared grid below the header (header is row 0, accounts from row 1)."""
        for w in getattr(self, "_row_cells", []):
            w.destroy()
        self._row_cells = []
        self.rows = {}
        for i, acct in enumerate(accts, start=1):
            lbl = ttk.Label(self.grid_frame,
                            text=f"{acct['code']}  {acct['name']}", anchor="w")
            lbl.grid(row=i, column=0, sticky="w", padx=(0, 8), pady=1)
            self._row_cells.append(lbl)
            vars_ = {}
            for c, (key, _label) in enumerate(self.FIELDS, start=1):
                v = tk.StringVar()
                ent = ttk.Entry(self.grid_frame, textvariable=v, width=12)
                ent.grid(row=i, column=c, sticky="we", padx=3, pady=1)
                self._row_cells.append(ent)
                vars_[key] = v
            status = ttk.Label(self.grid_frame, text="", anchor="w")
            status.grid(row=i, column=5, sticky="w", padx=(10, 0), pady=1)
            self._row_cells.append(status)
            self.rows[acct["code"]] = {"vars": vars_, "status": status}

    @staticmethod
    def _read_amount(text):
        """Returns ('blank', None) / ('ok', number) / ('bad', None)."""
        text = (text or "").strip().replace(",", "")
        if not text:
            return ("blank", None)
        try:
            return ("ok", float(text))
        except ValueError:
            return ("bad", None)

    def _gather_inputs(self):
        """Read the entry boxes into a bank_inputs dict. Returns
        (bank_inputs, ok); shows an error and returns ok=False if a box
        contains something that is not a number. A blank box simply means
        'not entered' and is left out."""
        bank_inputs = {}
        for code, row in self.rows.items():
            entered = {}
            for key, _label in self.FIELDS:
                state, value = self._read_amount(row["vars"][key].get())
                if state == "bad":
                    messagebox.showerror(
                        "Invalid number",
                        f"In account {code}, the "
                        f"{key.replace('_', ' ')} figure isn't a valid "
                        f"number.\n\nUse digits only, e.g. 1500 or 1500.00.")
                    return None, False
                if state == "ok":
                    entered[key] = value
            if entered:
                bank_inputs[code] = entered
        return bank_inputs, True

    def _compare(self):
        if not self.app.gateway:
            return
        bank_inputs, ok = self._gather_inputs()
        if not ok:
            return
        start = self.start_var.get().strip() or None
        end = self.end_var.get().strip() or None
        try:
            compared = self.app.gateway.reconcile(bank_inputs, start=start,
                                                  end=end)
            header = self.app.gateway.profile_header_lines()
        except gateway.GatewayError as e:
            messagebox.showerror("Could not reconcile", str(e))
            return

        # Per-row coloured status.
        by_code = {r["code"]: r for r in compared["rows"]}
        for code, row in self.rows.items():
            r = by_code.get(code)
            if not r or not r["checked"]:
                row["status"].config(text="", foreground=MUTED)
            elif r["reconciled"]:
                row["status"].config(text="reconciled", foreground=OK)
            else:
                row["status"].config(text="check figures", foreground=ERROR)

        # Side-by-side text, with green/red on the status lines.
        report = formatting.format_reconciliation(compared, header)
        self._last_report = report
        self._render(report)

        if compared["n_checked"] == 0:
            self.summary_var.set("Enter at least one statement figure, "
                                 "then compare.")
            self.summary_label.config(foreground=MUTED)
        else:
            done, total = compared["n_reconciled"], compared["n_checked"]
            self.summary_var.set(f"{done} of {total} account(s) reconciled.")
            self.summary_label.config(foreground=OK if done == total else ERROR)
        self.app.set_status("Reconciliation compared.", kind="ok")

    def _render(self, report):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for line in report.split("\n"):
            tag = ()
            if "Status: reconciled" in line:
                tag = ("good",)
            elif "Status: NOT reconciled" in line or "<-- differs" in line:
                tag = ("bad",)
            self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")

    def _clear(self):
        for row in self.rows.values():
            for v in row["vars"].values():
                v.set("")
            row["status"].config(text="")
        self.summary_var.set("")
        self._last_report = ""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _save(self):
        if not self._last_report.strip():
            messagebox.showinfo("Nothing to save",
                                "Compare against Ledger first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save reconciliation report",
            defaultextension=".txt",
            initialfile="reconciliation.txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w") as f:
                f.write(self._last_report + "\n")
        except OSError as e:
            messagebox.showerror("Could not save", str(e))
            return
        self.app.set_status(f"Saved reconciliation to {path}", kind="ok")

    def refresh(self):
        """Rebuild the rows only when the set of asset/liability accounts
        actually changes, so figures the user is part-way through typing
        are never wiped by a routine refresh."""
        if not self.app.gateway:
            return
        try:
            all_accts = self.app.gateway.list_accounts(include_inactive=False)
        except gateway.GatewayError:
            return
        accts = [a for a in all_accts
                 if a["type"] in ("ASSET", "LIABILITY")]
        codes = tuple(a["code"] for a in accts)
        if codes != self._built_codes:
            self._build_rows(accts)
            self._built_codes = codes

        # Role enforcement: reconciling needs RECONCILE (owner/manager).
        _set_enabled(self.compare_btn, self.app._can(roles.RECONCILE))


# ----------------------------------------------------------------------
# Tab 4: Accounts (chart of accounts)
# ----------------------------------------------------------------------

class AccountsTab(ttk.Frame):
    """View the chart of accounts and add new accounts."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=16, pady=14)

        ttk.Label(wrap, text="Chart of accounts",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap, text="These are the categories your transactions "
                             "can use. It's best to settle these with "
                             "your tax expert before entering lots of data.",
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 10))

        # The list of accounts.
        columns = ("code", "name", "type", "normal", "active")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings",
                                 height=14)
        for col, label, width, anchor in (
                ("code", "Code", 80, "w"),
                ("name", "Name", 300, "w"),
                ("type", "Type", 110, "w"),
                ("normal", "Normal balance", 120, "w"),
                ("active", "Active", 70, "w")):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor=anchor)
        # Inactive accounts are shown greyed (only when "Show inactive" is on).
        self.tree.tag_configure("inactive", foreground=MUTED)
        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="top", fill="both", expand=True)

        # --- rename row: select an account above, rename it here ---
        rename_row = ttk.Frame(wrap)
        rename_row.pack(fill="x", pady=(10, 0))
        ttk.Label(rename_row, text="Rename selected account to:").pack(
            side="left")
        self.rename_var = tk.StringVar()
        self.rename_entry = ttk.Entry(rename_row, textvariable=self.rename_var,
                                      width=32)
        self.rename_entry.pack(side="left", padx=6)
        self.rename_btn = ttk.Button(rename_row, text="Rename",
                                     command=self._rename_account)
        self.rename_btn.pack(side="left")
        ttk.Label(rename_row,
                  text="(makes a name specific to you, e.g. "
                       "\"TD Business Checking\")",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))

        # --- activate / deactivate row ---
        actions = ttk.Frame(wrap)
        actions.pack(fill="x", pady=(8, 0))
        self.deact_btn = ttk.Button(actions, text="Deactivate selected account",
                                    command=self._deactivate_account)
        self.deact_btn.pack(side="left")
        self.react_btn = ttk.Button(actions, text="Reactivate selected account",
                                    command=self._reactivate_account)
        self.react_btn.pack(side="left", padx=6)
        self.show_inactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text="Show deactivated accounts",
                        variable=self.show_inactive_var,
                        command=self.refresh).pack(side="left", padx=(16, 0))
        ttk.Label(actions,
                  text="(deactivating hides an account from new entries "
                       "and Reconcile; its history is kept)",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))

        # --- add-account form ---
        form = ttk.Frame(wrap)
        form.pack(fill="x", pady=(12, 0))
        ttk.Label(form, text="Add an account:  ").grid(row=0, column=0,
                                                       sticky="w")
        ttk.Label(form, text="Code").grid(row=0, column=1)
        self.code_var = tk.StringVar()
        self.add_code_e = ttk.Entry(form, textvariable=self.code_var, width=8)
        self.add_code_e.grid(row=0, column=2, padx=4)
        ttk.Label(form, text="Name").grid(row=0, column=3)
        self.name_var = tk.StringVar()
        self.add_name_e = ttk.Entry(form, textvariable=self.name_var, width=26)
        self.add_name_e.grid(row=0, column=4, padx=4)
        ttk.Label(form, text="Type").grid(row=0, column=5)
        self.type_var = tk.StringVar(value="EXPENSE")
        self.add_type_cb = ttk.Combobox(
            form, textvariable=self.type_var, state="readonly", width=12,
            values=["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"])
        self.add_type_cb.grid(row=0, column=6, padx=4)
        self.add_btn = ttk.Button(form, text="Add", command=self._add_account)
        self.add_btn.grid(row=0, column=7, padx=6)

        # Keep the rename box in step with whatever row is selected.
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _on_select(self, _event=None):
        """When an account row is clicked, preload its name in the box."""
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        if values:
            self.rename_var.set(values[1])  # the current name

    def _selected_code(self):
        """The account code of the currently selected row, or None."""
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        return values[0] if values else None

    def _account_by_code(self, code):
        """Find an account dict by code via the gateway (includes inactive)."""
        try:
            for a in self.app.gateway.list_accounts(include_inactive=True):
                if a["code"] == code:
                    return a
        except gateway.GatewayError:
            pass
        return None

    def _rename_account(self):
        code = self._selected_code()
        if not code:
            messagebox.showinfo(
                "Select an account",
                "Click an account in the list above first, then type "
                "the new name and press Rename.")
            return
        new_name = self.rename_var.get().strip()
        if not new_name:
            messagebox.showinfo("Enter a name",
                                "Type the new name for the account.")
            return
        try:
            self.app.gateway.rename_account(code, new_name)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not rename account", str(e))
            return
        self.app.set_status(f"Renamed account {code} to '{new_name}'",
                            kind="ok")
        self.app.refresh_all()

    def _deactivate_account(self):
        code = self._selected_code()
        if not code:
            messagebox.showinfo(
                "Select an account",
                "Click an account in the list above first, then press "
                "Deactivate.")
            return
        acct = self._account_by_code(code)
        if acct and not acct["active"]:
            messagebox.showinfo("Already inactive",
                                f"Account {code} is already inactive.")
            return
        name = acct["name"] if acct else ""
        if not messagebox.askyesno(
                "Deactivate account?",
                f"Deactivate '{code}  {name}'?\n\n"
                "It will be hidden from new entries and the Reconcile "
                "list, but its history stays on your reports and you can "
                "reactivate it anytime."):
            return
        try:
            self.app.gateway.set_account_active(code, False)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not deactivate account", str(e))
            return
        self.app.set_status(f"Deactivated account {code}.", kind="ok")
        self.app.refresh_all()

    def _reactivate_account(self):
        code = self._selected_code()
        if not code:
            messagebox.showinfo(
                "Select an account",
                "Turn on 'Show deactivated accounts', click the "
                "deactivated account in the list, then press Reactivate.")
            return
        acct = self._account_by_code(code)
        if acct and acct["active"]:
            messagebox.showinfo("Already active",
                                f"Account {code} is already active.")
            return
        try:
            self.app.gateway.set_account_active(code, True)
        except gateway.GatewayError as e:
            messagebox.showerror("Could not reactivate account", str(e))
            return
        self.app.set_status(f"Reactivated account {code}.", kind="ok")
        self.app.refresh_all()

    def _add_account(self):
        try:
            self.app.gateway.add_account(self.code_var.get(),
                                         self.name_var.get(),
                                         self.type_var.get())
        except gateway.GatewayError as e:
            messagebox.showerror("Could not add account", str(e))
            return
        self.app.set_status(
            f"Added account {self.code_var.get()} {self.name_var.get()}",
            kind="ok")
        self.code_var.set("")
        self.name_var.set("")
        self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.app.gateway:
            return
        show_inactive = (self.show_inactive_var.get()
                         if hasattr(self, "show_inactive_var") else False)
        try:
            rows = self.app.gateway.list_accounts(include_inactive=show_inactive)
        except gateway.GatewayError:
            return
        for r in rows:
            active = "yes" if r["active"] else "no"
            tags = () if r["active"] else ("inactive",)
            self.tree.insert("", "end",
                             values=(r["code"], r["name"], r["type"],
                                     r["normal_balance"], active),
                             tags=tags)

        # Role enforcement: managing accounts needs MANAGE_ACCOUNTS
        # (owner/manager). Viewing the chart of accounts stays available.
        can_manage = self.app._can(roles.MANAGE_ACCOUNTS)
        for w in (self.rename_entry, self.rename_btn, self.deact_btn,
                  self.react_btn, self.add_code_e, self.add_name_e,
                  self.add_type_cb, self.add_btn):
            _set_enabled(w, can_manage)
        # The type combobox is readonly when enabled, disabled otherwise.
        if can_manage:
            _set_enabled(self.add_type_cb, True)
            try:
                self.add_type_cb.configure(state="readonly")
            except Exception:
                pass


# ----------------------------------------------------------------------
# Tab 5: Backup
# ----------------------------------------------------------------------

class SecurityTab(ttk.Frame):
    """Encryption (protection) for the open set of books -- who can open the
    data file at all. Sharing those books with other people or other computers
    has moved to its own Sharing tab."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = _centered(self)
        ttk.Label(wrap, text="Security", style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap, text="Who can open these books on this computer.",
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 14))

        # --- Encryption card (applies to any book) ---
        _enc_outer, enc = _titled_card(wrap, "Encryption")
        self.enc_status = tk.Label(enc, text="", bg=PANEL, fg="#1e2a4a",
                                   font=FONT, wraplength=780, justify="left",
                                   anchor="w")
        self.enc_status.pack(anchor="w")
        self.enc_btn = _card_button(enc, "", lambda: None)
        self._enc_btn_shown = False

    # -- encryption ----------------------------------------------------------

    def _update_encryption_section(self):
        app = self.app
        if app.mode == "client":
            self.enc_status.config(text=(
                "These books are hosted on another computer. Their encryption "
                "and backups are managed there, on the host \u2014 not from "
                "this computer."))
            if self._enc_btn_shown:
                self.enc_btn.pack_forget()
                self._enc_btn_shown = False
            return
        if app.mode == "host":
            self.enc_status.config(text=(
                "These books are encrypted and always protected. While you are "
                "hosting them on the network, changing protection is paused "
                "\u2014 stop hosting (Sharing tab) to make changes here."))
            if self._enc_btn_shown:
                self.enc_btn.pack_forget()
                self._enc_btn_shown = False
            return
        protected = bool(app.db_path) and crypto.is_protected(app.db_path)
        try:
            kind = profile.get_kind(app.conn)
        except Exception:
            kind = ""

        def show_button(text, command):
            self.enc_btn.config(text=text, command=command)
            _set_enabled(self.enc_btn, self.app._can(roles.MANAGE_PROTECTION))
            if not self._enc_btn_shown:
                self.enc_btn.pack(anchor="w", pady=(10, 0))
                self._enc_btn_shown = True

        def hide_button():
            if self._enc_btn_shown:
                self.enc_btn.pack_forget()
                self._enc_btn_shown = False

        if protected:
            text = ("This set of books is Protected. Its data file and any new "
                    "backups are encrypted, and can be opened only with your "
                    "passphrase (or recovery code).")
            if kind == "business":
                text += ("  Business books are always protected, so this can't "
                         "be turned off.")
                self.enc_status.config(text=text)
                hide_button()
            else:
                self.enc_status.config(text=text)
                show_button("Turn off protection\u2026",
                            self._on_turn_off_protection)
        elif not crypto.CRYPTO_AVAILABLE:
            self.enc_status.config(text=(
                "This set of books is Open (not encrypted). Encryption isn't "
                "available because the 'cryptography' library isn't installed "
                "on this computer."))
            hide_button()
        else:
            self.enc_status.config(text=(
                "This set of books is Open \u2014 it is NOT encrypted. Anyone "
                "who can open the file can read your records. Turning on "
                "protection encrypts the data file and all future backups."))
            show_button("Turn on protection\u2026",
                        self._on_turn_on_protection)

    def _on_turn_on_protection(self):
        if self.app._protect_existing_book():
            self.refresh()

    def _on_turn_off_protection(self):
        if self.app._unprotect_existing_book():
            self.refresh()

    def refresh(self):
        self._update_encryption_section()


class SharingTab(ttk.Frame):
    """Sharing the open books with other people and other computers: per-person
    sign-ins and roles, user management, the activity log, and hosting the
    books on the network so other computers can sign in to them."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = _centered(self)
        ttk.Label(wrap, text="Sharing", style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap, text="Let other people \u2014 and other computers on "
                            "your network \u2014 use these books.",
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 14))

        # Shown in place of the cards when sharing does not apply (personal or
        # unencrypted books, or none open).
        self.not_applicable = tk.Label(wrap, text="", bg=BG, fg=MUTED,
                                       font=FONT, wraplength=800,
                                       justify="left", anchor="w")
        self._na_shown = False

        # --- Shared access card: people on this computer ---
        self._share_outer, share = _titled_card(wrap, "Shared access")
        self.share_status = tk.Label(share, text="", bg=PANEL, fg="#1e2a4a",
                                     font=FONT, wraplength=780, justify="left",
                                     anchor="w")
        self.share_status.pack(anchor="w")
        self.share_btn = _card_button(share, "Set up shared access\u2026",
                                      self._on_manage_users)
        self._share_btn_shown = False
        self.audit_btn = _card_button(share, "View activity log\u2026",
                                      self._on_view_audit)
        self._audit_btn_shown = False
        # A manager (not the owner) gets a focused 'Reset a password' button --
        # they can give a staff member a new one-time password without the full
        # user-management screen. Hidden for owners (who use 'Manage users')
        # and staff.
        self.reset_btn = _card_button(share, "Reset a password\u2026",
                                      self._on_reset_password)
        self._reset_btn_shown = False

        # --- Hosting card: other computers over the network ---
        self._host_outer, host = _titled_card(wrap, "Hosting")
        self.host_status = tk.Label(host, text="", bg=PANEL, fg="#1e2a4a",
                                    font=FONT, wraplength=780, justify="left",
                                    anchor="w")
        self.host_status.pack(anchor="w")
        # Shown only while this computer is hosting: where to connect, the
        # security fingerprint, and a live connected count.
        self.host_detail = tk.Label(host, text="", bg=PANEL, fg="#1e2a4a",
                                    font=FONT, wraplength=780, justify="left",
                                    anchor="w")
        self.host_fp = tk.Label(host, text="", bg="#1e2a4a", fg="#ffffff",
                                font=("TkFixedFont", 11), padx=12, pady=8,
                                wraplength=760, justify="left", anchor="w")
        self.host_count = tk.Label(host, text="", bg=PANEL, fg=ACCENT,
                                   font=FONT_BOLD, anchor="w")
        self._host_detail_shown = False
        self.host_btn = _card_button(host, "Host these books on the "
                                           "network\u2026", self._on_host)
        self._host_btn_shown = False
        # Shown only in the background-host card: a one-click way back into the
        # books being hosted here (signs in over the loopback), so the owner
        # can switch back from another book without restarting the program.
        self.host_open_btn = _card_button(
            host, "Open the hosted books here\u2026", self._on_open_hosted)
        self._host_open_shown = False

    # -- showing / hiding the whole tab --------------------------------------

    def _ensure_packed(self, outer):
        if not outer.winfo_ismapped():
            outer.pack(fill="x", pady=(2, 14))

    def _ensure_unpacked(self, outer):
        if outer.winfo_ismapped():
            outer.pack_forget()

    def _show_not_applicable(self, text):
        self.not_applicable.config(text=text)
        if not self._na_shown:
            self.not_applicable.pack(anchor="w", pady=(2, 14))
            self._na_shown = True
        self._ensure_unpacked(self._share_outer)
        self._ensure_unpacked(self._host_outer)

    def _hide_not_applicable(self):
        if self._na_shown:
            self.not_applicable.pack_forget()
            self._na_shown = False
        self._ensure_packed(self._share_outer)
        self._ensure_packed(self._host_outer)

    # -- shared access (people on this computer) -----------------------------

    def _on_manage_users(self):
        app = self.app
        sess = app._session
        if not sess or not sess.can(roles.MANAGE_USERS):
            messagebox.showinfo("Not available",
                                "Only an owner can manage users.")
            return
        if app.mode in ("client", "host"):
            # Already shared (engine-backed); manage users straight through the
            # gateway, with no local enable-multiuser step.
            app._open_users_manager()
            self.refresh()
            return
        try:
            enabled = users.multiuser_enabled(app.conn)
        except Exception:
            enabled = False
        if not enabled:
            if not app._enable_multiuser_flow():
                self.refresh()
                return
        app._open_users_manager()
        self.refresh()

    def _on_view_audit(self):
        self.app._open_audit_log()

    def _on_reset_password(self):
        self.app._open_password_reset()
        self.refresh()

    def _render_reset_button(self):
        """Show the 'Reset a password' button to a manager only -- someone who
        can reset a password but is not the owner. The owner resets from the
        fuller 'Manage users' screen; staff don't see it at all."""
        sess = self.app._session
        show = (bool(sess) and sess.can(roles.RESET_PASSWORD)
                and not sess.can(roles.MANAGE_USERS))
        if show:
            if not self._reset_btn_shown:
                self.reset_btn.pack(anchor="w", pady=(6, 0))
                self._reset_btn_shown = True
        else:
            if self._reset_btn_shown:
                self.reset_btn.pack_forget()
                self._reset_btn_shown = False

    def _update_sharing_section(self):
        """The 'Shared access' card for a local, eligible business book."""
        app = self.app
        try:
            enabled = users.multiuser_enabled(app.conn)
        except Exception:
            enabled = False
        sess = app._session
        is_owner = bool(sess) and sess.can(roles.MANAGE_USERS)
        if enabled:
            self.share_status.config(text=(
                "These books are shared. Each person signs in with their own "
                "username and password, and what they can do depends on their "
                "role (Owner, Manager, or Staff)."))
            self.share_btn.config(text="Manage users\u2026")
        else:
            self.share_status.config(text=(
                "Right now only you (the owner) can open these books. You can "
                "share them with employees, giving each person their own "
                "sign-in and role. Note: on a single shared computer, roles "
                "guard against mistakes and record who did what, but cannot "
                "stop a determined user who has a password \u2014 full "
                "enforcement across computers comes with hosting (below)."))
            self.share_btn.config(text="Set up shared access\u2026")
        if is_owner:
            if not self._share_btn_shown:
                self.share_btn.pack(anchor="w", pady=(10, 0))
                self._share_btn_shown = True
        else:
            if self._share_btn_shown:
                self.share_btn.pack_forget()
                self._share_btn_shown = False
        show_audit = enabled and app._can(roles.VIEW_AUDIT)
        if show_audit:
            if not self._audit_btn_shown:
                self.audit_btn.pack(anchor="w", pady=(6, 0))
                self._audit_btn_shown = True
        else:
            if self._audit_btn_shown:
                self.audit_btn.pack_forget()
                self._audit_btn_shown = False
        self._render_reset_button()

    def _render_manage_and_audit(self, status_text):
        """Shared rendering of the 'Shared access' card for the modes where the
        book is already shared (client and host): a status line, a Manage
        users button (owner), and an activity-log button (by role)."""
        app = self.app
        sess = app._session
        can_manage = bool(sess) and sess.can(roles.MANAGE_USERS)
        self.share_status.config(text=status_text)
        self.share_btn.config(text="Manage users\u2026")
        if can_manage:
            if not self._share_btn_shown:
                self.share_btn.pack(anchor="w", pady=(10, 0))
                self._share_btn_shown = True
        else:
            if self._share_btn_shown:
                self.share_btn.pack_forget()
                self._share_btn_shown = False
        if app._can(roles.VIEW_AUDIT):
            if not self._audit_btn_shown:
                self.audit_btn.pack(anchor="w", pady=(6, 0))
                self._audit_btn_shown = True
        else:
            if self._audit_btn_shown:
                self.audit_btn.pack_forget()
                self._audit_btn_shown = False
        self._render_reset_button()

    def _update_sharing_section_client(self):
        """The 'Shared access' card when connected to a host: the book is
        already shared, so offer user management and the activity log over the
        wire (by role)."""
        self._render_manage_and_audit(
            "These books are shared and hosted on another computer. Everyone "
            "signs in with their own username and password. Depending on your "
            "role, you can manage users and view the activity log here.")

    def _update_sharing_section_host(self):
        """The 'Shared access' card while hosting on this computer: manage
        users and view the activity log, through the engine."""
        self._render_manage_and_audit(
            "These books are shared. Everyone signs in with their own username "
            "and password \u2014 you here, and anyone who connects over the "
            "network. You can manage users and view the activity log.")

    # -- hosting (other computers over the network) --------------------------

    def _hide_host_detail(self):
        if self._host_detail_shown:
            self.host_detail.pack_forget()
            self.host_fp.pack_forget()
            self.host_count.pack_forget()
            self._host_detail_shown = False

    def _update_hosting_section(self):
        """The 'Hosting' card for a local, eligible business book. The button
        appears for the owner once shared access is set up; before that the
        card explains that sharing is the prerequisite -- so the owner can see
        hosting exists and what it needs."""
        app = self.app
        self._hide_host_detail()
        self._hide_host_open()
        self.host_btn.config(text="Host these books on the network\u2026",
                             command=self._on_host)
        try:
            enabled = users.multiuser_enabled(app.conn)
        except Exception:
            enabled = False
        sess = app._session
        is_owner = bool(sess) and sess.can(roles.MANAGE_USERS)
        if not enabled:
            self.host_status.config(text=(
                "Hosting lets other computers on your network open these books "
                "\u2014 each person signing in on their own machine. Set up "
                "shared access above first, then you can start hosting."))
        elif not is_owner:
            self.host_status.config(text=(
                "These books can be hosted so other computers on the network "
                "can sign in. Only the owner can start hosting."))
        else:
            self.host_status.config(text=(
                "Host these books so other computers on your network can sign "
                "in to them. You can keep working here while hosting; the "
                "connection details and a Stop button appear here once it is "
                "running."))
        can_host = enabled and is_owner and crypto.CRYPTO_AVAILABLE
        if can_host:
            if not self._host_btn_shown:
                self.host_btn.pack(anchor="w", pady=(10, 0))
                self._host_btn_shown = True
        else:
            if self._host_btn_shown:
                self.host_btn.pack_forget()
                self._host_btn_shown = False

    def _update_hosting_section_client(self):
        self._hide_host_detail()
        self._hide_host_open()
        self.host_status.config(text=(
            "These books are hosted on another computer \u2014 you are "
            "connected to them now. Hosting is managed there, on the host."))
        if self._host_btn_shown:
            self.host_btn.pack_forget()
            self._host_btn_shown = False

    def _update_hosting_section_hosting(self):
        """The 'Hosting' card while this computer is hosting. The owner sees the
        connect address, security fingerprint, a live connected count, and a
        Stop button -- the details needed to manage hosting. An employee working
        here just sees that the books are hosted; the address and fingerprint
        are the owner's to hold, not data they need. Bookkeeping continues on
        the other tabs as usual for everyone."""
        app = self.app
        is_owner = app._can(roles.MANAGE_USERS)
        info = app._host_display() or {}
        self._hide_host_open()
        if is_owner:
            self.host_status.config(text=(
                "These books are being hosted on the network \u2014 and you "
                "can keep working here on the other tabs. Others connect from "
                "their own copy of Ledger using the details below."))
        else:
            self.host_status.config(text=(
                "These books are being hosted on the network \u2014 you can "
                "keep working here on the other tabs."))
        if is_owner:
            addrs = info.get("addrs") or []
            port = info.get("port")
            if addrs:
                lines = "\n".join("    %s   (port %s)" % (a, port)
                                  for a in addrs)
                detail = "Address for others to connect:\n" + lines
            else:
                detail = ("Listening on port %s (find this computer's address "
                          "in your network settings)." % port)
            if info.get("advertising"):
                detail += ("\n\nDiscoverable: others can pick \u201cConnect to "
                           "a host\u201d and it finds this computer \u2014 no "
                           "address needed.")
            self.host_detail.config(text=detail)
            self.host_fp.config(
                text="Security fingerprint (to read aloud on a first "
                     "connection):\n" + (info.get("fingerprint") or
                                         "(unavailable)"))
            self.refresh_host_count(app._host_connected_count())
            if not self._host_detail_shown:
                self.host_detail.pack(anchor="w", pady=(8, 0))
                self.host_fp.pack(anchor="w", fill="x", pady=(8, 0))
                self.host_count.pack(anchor="w", pady=(10, 0))
                self._host_detail_shown = True
        else:
            # Employees don't get the address, fingerprint, or connected count.
            self._hide_host_detail()
        self.host_btn.config(text="Stop hosting", command=self._on_stop_host)
        # Only the owner can stop hosting, so only the owner sees the button.
        # A manager or staff member working here just won't have the control.
        if is_owner:
            if not self._host_btn_shown:
                self.host_btn.pack(anchor="w", pady=(12, 0))
                self._host_btn_shown = True
        else:
            if self._host_btn_shown:
                self.host_btn.pack_forget()
                self._host_btn_shown = False

    def _update_hosting_section_background(self):
        """Shown when a host is running in the background but this window is
        being used for something else -- signed out on the landing page, in
        another local book, or connected to a different host. Offers a way back
        into the hosted books (over the loopback) and an owner-gated Stop. No
        live detail/count here -- we hold no connection to the host."""
        app = self.app
        is_owner = app._can(roles.MANAGE_USERS)
        self._hide_host_detail()
        book = ""
        try:
            book = os.path.basename((app._host_state or {}).get("book") or "")
        except Exception:
            book = ""
        which = (" \u2014 %s" % book) if book else ""
        # The owner gets the controls (open the hosted books here, stop). An
        # employee just sees that hosting is running -- no controls -- so there
        # is no confusion about reaching the hosted books from this machine.
        if is_owner:
            tail = (" Open them here to work in them, or stop hosting. Only "
                    "the owner can stop hosting.")
        else:
            tail = (" To work in these books, sign in from your own computer.")
        self.host_status.config(text=(
            "A set of books on this computer%s is being hosted in the "
            "background, so other computers on your network can sign in.%s"
            % (which, tail)))
        # Primary: get back into the hosted books (signs in over the loopback)
        # -- owner only, so an employee is not led to the hosted books here.
        self.host_open_btn.config(text="Open the hosted books here\u2026",
                                  command=self._on_open_hosted)
        if is_owner:
            if not self._host_open_shown:
                self.host_open_btn.pack(anchor="w", pady=(12, 0))
                self._host_open_shown = True
        else:
            self._hide_host_open()
        # Secondary: stop hosting -- owner only, so employees never see it.
        self.host_btn.config(text="Stop hosting", command=self._on_stop_host)
        if is_owner:
            if not self._host_btn_shown:
                self.host_btn.pack(anchor="w", pady=(8, 0))
                self._host_btn_shown = True
        else:
            if self._host_btn_shown:
                self.host_btn.pack_forget()
                self._host_btn_shown = False

    def refresh_host_count(self, n):
        """Update just the live connected count (called on a timer by the
        app while hosting)."""
        word = "person" if n == 1 else "people"
        try:
            self.host_count.config(text="%d %s connected" % (n, word))
        except Exception:
            pass

    def _on_host(self):
        self.app._start_hosting()

    def _on_stop_host(self):
        app = self.app
        sess = app._session
        if (app.mode == "host" and sess is not None
                and sess.can(roles.MANAGE_USERS)):
            # Already signed in to the host as owner over the loopback: the role
            # is verified on the live session, so stop directly.
            app._stop_hosting()
        else:
            # Signed out, in another book, or in an unencrypted book with no
            # session: prove the *hosted* books' owner against the running host
            # before stopping, so physical access alone can't end hosting.
            app._host_stop_requested()

    def _on_open_hosted(self):
        # Re-enter the books being hosted on this computer. The host process
        # holds that file, so we sign in over the loopback rather than opening
        # a second local copy.
        self.app._host_sign_in()

    def _hide_host_open(self):
        if self._host_open_shown:
            self.host_open_btn.pack_forget()
            self._host_open_shown = False

    def refresh(self):
        app = self.app
        # Hosting on this computer: shared, and we work through our own engine.
        if app.mode == "host":
            self._hide_not_applicable()
            self._update_sharing_section_host()
            self._update_hosting_section_hosting()
            return
        # A host is running in the background while this window is used for
        # something else (signed out, another local book, or a different host).
        # Surface Stop here -- owner-gated on click -- so hosting can always be
        # ended from the Sharing tab. The Shared-access card is hidden: it
        # concerns whatever book is open here, which may be unrelated.
        if app._host_state is not None or app._host_proc is not None:
            if self._na_shown:
                self.not_applicable.pack_forget()
                self._na_shown = False
            self._ensure_unpacked(self._share_outer)
            self._ensure_packed(self._host_outer)
            self._update_hosting_section_background()
            return
        # Connected to a host: the books are shared and hosted elsewhere.
        if app.mode == "client":
            self._hide_not_applicable()
            self._update_sharing_section_client()
            self._update_hosting_section_client()
            return
        # Local: sharing applies only to a protected business book.
        protected = bool(app.db_path) and crypto.is_protected(app.db_path)
        try:
            kind = profile.get_kind(app.conn)
        except Exception:
            kind = ""
        if app.conn is None:
            self._show_not_applicable("Open a set of books to set up sharing.")
            return
        if kind != "business":
            self._show_not_applicable(
                "Sharing is for business books \u2014 giving employees their "
                "own sign-ins, and letting other computers connect. These are "
                "personal books, opened only by you.")
            return
        if not crypto.CRYPTO_AVAILABLE:
            self._show_not_applicable(
                "Sharing needs encryption, which isn't available on this "
                "computer (the 'cryptography' library isn't installed).")
            return
        if not protected:
            self._show_not_applicable(
                "Sharing is available once these books are protected. Turn on "
                "protection from the Security tab first.")
            return
        self._hide_not_applicable()
        self._update_sharing_section()
        self._update_hosting_section()


class BackupTab(ttk.Frame):
    """Make backups and restore from them."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = _centered(self)

        ttk.Label(wrap, text="Backup and restore",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(wrap,
                  text="A backup is a dated copy of your data. \"Make a "
                       "backup now\" saves it to a folder named for your "
                       "business inside your Documents folder, so it's "
                       "easy to find. For real safety, also keep a copy "
                       "somewhere separate from this computer \u2014 a USB "
                       "drive or a cloud folder \u2014 using \"Back up "
                       "to\u2026\" below.",
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 10))

        # --- Row 1: backup buttons ---
        btns = ttk.Frame(wrap)
        btns.pack(fill="x", pady=(0, 4))
        self.make_btn = ttk.Button(btns, text="Make a backup now",
                                   style="Accent.TButton",
                                   command=self._make_backup)
        self.make_btn.pack(side="left")
        self.backup_to_btn = ttk.Button(btns, text="Back up to\u2026",
                                        command=self._backup_to)
        self.backup_to_btn.pack(side="left", padx=6)
        # The "back up to last place again" button is built but only
        # shown when there IS a remembered location -- see refresh().
        self.again_btn = ttk.Button(btns, text="",
                                    command=self._backup_to_last)
        self._again_shown = False  # tracks whether the button is packed
        # (not packed here; refresh() packs/unpacks it as appropriate)

        # A small line telling the user where "Make a backup now" puts
        # things, and where the remembered location is (if any).
        self.where_label = ttk.Label(wrap, text="", style="Muted.TLabel",
                                     wraplength=820, justify="left")
        self.where_label.pack(anchor="w", pady=(0, 8))

        # --- Row 2: restore + refresh ---
        btns2 = ttk.Frame(wrap)
        btns2.pack(fill="x", pady=(0, 10))
        self.restore_btn = ttk.Button(btns2, text="Restore from a backup\u2026",
                                      command=self._restore)
        self.restore_btn.pack(side="left")
        ttk.Button(btns2, text="Refresh list",
                   command=self.refresh).pack(side="left", padx=6)

        ttk.Label(wrap, text="Backups for this set of books (newest first):",
                  style="TLabel", font=FONT_BOLD).pack(anchor="w",
                                                       pady=(8, 2))
        self.listbox = tk.Listbox(wrap, font=FONT_MONO, height=11,
                                  bg=PANEL, relief="solid", bd=1)
        self.listbox.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # the three ways to make a backup
    # ------------------------------------------------------------------

    def _current_backup_dir(self):
        """The default backup folder for THIS set of books: a folder named
        for the business (or person) inside Documents/Ledger Backups. Shares
        the app's helper so the Backup tab and the automatic on-exit backup
        always use the same folder."""
        return self.app._book_backup_dir()

    def _make_backup(self):
        """Back up into this book's Documents/Ledger Backups/<name>/
        folder (created if needed)."""
        # Make sure the on-disk file reflects the latest committed data. For
        # an encrypted book this re-writes its encrypted file, so the copy we
        # are about to make is fully current.
        self.app._flush_book()
        try:
            dest = backup.backup(db_path=self.app.db_path,
                                 backup_dir=backup.manual_dir(
                                     self._current_backup_dir()),
                                 create=True)
        except FileNotFoundError as e:
            messagebox.showerror("Could not back up", str(e))
            return
        except OSError as e:
            messagebox.showerror("Could not back up", str(e))
            return
        messagebox.showinfo(
            "Backup made",
            f"Saved a backup to:\n\n{dest}\n\n"
            "This folder is in your Documents, named for your business, so "
            "it's easy to find. For protection against computer loss or "
            "theft, also use \"Back up to\u2026\" to put a copy on a USB "
            "drive or in a cloud folder.")
        self.app.set_status(f"Backup saved: {dest}", kind="ok")
        # Tidy away automatic copies older than the keep window. This and
        # other manual backups are kept; only old "_auto" copies are cleared.
        try:
            backup.prune_backups(self._current_backup_dir(),
                                 days=backup.AUTO_BACKUP_KEEP_DAYS)
        except Exception:
            pass
        self.refresh()

    def _backup_to(self):
        """Let the user choose any folder (USB drive, cloud folder, etc.)."""
        folder = filedialog.askdirectory(
            title="Choose where to save the backup "
                  "(e.g. your USB drive)",
            mustexist=True)
        if not folder:
            return
        self._do_backup_to_folder(folder, remember=True)

    def _backup_to_last(self):
        """One-click repeat of the last custom backup location."""
        folder = backup.get_last_location()
        if not folder:
            return
        if not backup.location_available(folder):
            messagebox.showwarning(
                "That location isn't available",
                "The last backup location:\n\n" + folder + "\n\n"
                "can't be reached right now. If it's a USB drive, "
                "check that it's plugged in. You can also use "
                "\"Back up to\u2026\" to pick a different place.")
            return
        self._do_backup_to_folder(folder, remember=True)

    def _do_backup_to_folder(self, folder, remember):
        """Shared worker: make a backup into `folder`."""
        # Capture the latest committed data first (see _make_backup).
        self.app._flush_book()
        try:
            dest = backup.backup(db_path=self.app.db_path,
                                 backup_dir=folder)
        except FileNotFoundError as e:
            messagebox.showerror("Could not back up", str(e))
            return
        except OSError as e:
            messagebox.showerror(
                "Could not save there",
                "The backup could not be saved to:\n\n" + folder +
                "\n\n" + str(e) + "\n\nIf it's a USB drive, check that "
                "it's plugged in and not full or write-protected.")
            return
        if remember:
            backup.remember_location(folder)
        messagebox.showinfo(
            "Backup made",
            f"Saved a backup to:\n\n{dest}")
        self.app.set_status(f"Backup saved to {dest}", kind="ok")
        self.refresh()

    # ------------------------------------------------------------------
    # restore
    # ------------------------------------------------------------------

    def _restore(self):
        # Start the file browser in the last custom location if there is
        # one (likely where their newest backup is), else the standard folder.
        last = backup.get_last_location()
        start_dir = (last if backup.location_available(last)
                     else self._current_backup_dir())
        path = filedialog.askopenfilename(
            title="Choose a backup file to restore",
            initialdir=start_dir,
            filetypes=[("Ledger data", "*.db"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                "Restore this backup?",
                "This will replace your current data with the contents "
                "of:\n\n" + path + "\n\nYour current data will be copied "
                "aside first, so this can be undone. Continue?"):
            return
        try:
            restored_from, safety = backup.restore(
                path, db_path=self.app.db_path,
                data_key=self.app._book_data_key)
        except FileNotFoundError as e:
            messagebox.showerror("Could not restore", str(e))
            return
        except ValueError as e:
            # The chosen backup did not open with this book's key, so nothing
            # was changed. Tell the user plainly.
            messagebox.showerror("That backup does not match this book",
                                 str(e))
            return
        # Reopen the database so the app shows the restored data. We already
        # hold this book's key, so reopen with it rather than asking again.
        reopened = self.app._open_database(
            self.app.db_path, announce=False,
            known_key=self.app._book_data_key)
        if not reopened:
            # The copy is in place but the book would not reopen. Don't claim
            # success; point the user at the safety copy made moments ago.
            recover = (f"\n\nYour data from just before this restore was saved "
                       f"to:\n{safety}\nYou can restore that file to return to "
                       f"where you were.") if safety else ""
            messagebox.showerror(
                "Restore did not complete",
                "The backup was copied into place, but this set of books "
                "could not be reopened afterwards." + recover)
            self.app.set_status("Restore did not complete", kind="error")
            return
        msg = f"Restored from:\n{restored_from}"
        if safety:
            msg += f"\n\nYour previous data was saved first to:\n{safety}"
        messagebox.showinfo("Restore complete", msg)
        self.app.set_status("Restore complete", kind="ok")

    # ------------------------------------------------------------------
    # refresh
    # ------------------------------------------------------------------

    def refresh(self):
        if self.app.mode == "client":
            self.listbox.delete(0, "end")
            self.listbox.insert("end", "  (backups are managed on the host)")
            self.where_label.config(text=(
                "These books are hosted on another computer. Backups are made "
                "on the host \u2014 by whoever runs it \u2014 not from here."))
            for b in (self.make_btn, self.backup_to_btn, self.again_btn,
                      self.restore_btn):
                _set_enabled(b, False)
            if self._again_shown:
                self.again_btn.pack_forget()
                self._again_shown = False
            return
        if self.app.mode == "host":
            self.listbox.delete(0, "end")
            self.listbox.insert("end", "  (backups are paused while hosting)")
            self.where_label.config(text=(
                "While you are hosting these books on the network, making "
                "local backups is paused, because the data file is in active "
                "use. Stop hosting (Sharing tab) to back up."))
            for b in (self.make_btn, self.backup_to_btn, self.again_btn,
                      self.restore_btn):
                _set_enabled(b, False)
            if self._again_shown:
                self.again_btn.pack_forget()
                self._again_shown = False
            return
        # This book's backup list (its own folder in Documents).
        current_dir = self._current_backup_dir()
        self.listbox.delete(0, "end")
        backups = backup.list_backups(current_dir)
        if not backups:
            self.listbox.insert("end", "  (no backups yet)")
        else:
            for path in backups:
                try:
                    size_kb = os.path.getsize(path) / 1024
                except OSError:
                    size_kb = 0
                self.listbox.insert("end",
                                    f"  {path}   ({size_kb:.0f} KB)")

        # Update the "where" line and the remembered-location button.
        standard = current_dir
        last = backup.get_last_location()
        where = f'"Make a backup now" saves to:  {standard}'
        if last:
            available = backup.location_available(last)
            state = "available now" if available else "not reachable now"
            where += f'\nLast \"Back up to\u2026\" location:  {last}  ' \
                     f'({state})'
            # Show the one-click repeat button, labelled with the place.
            short = last if len(last) <= 48 else "\u2026" + last[-47:]
            self.again_btn.config(text=f"Back up to {short} again")
            if not self._again_shown:
                self.again_btn.pack(side="left", padx=6)
                self._again_shown = True
        else:
            # No remembered location yet -- hide the repeat button.
            if self._again_shown:
                self.again_btn.pack_forget()
                self._again_shown = False
        self.where_label.config(text=where)

        # Role enforcement: Make a backup needs MAKE_BACKUP (owner/manager);
        # Restore needs RESTORE_BACKUP (owner only).
        can_backup = self.app._can(roles.MAKE_BACKUP)
        _set_enabled(self.make_btn, can_backup)
        _set_enabled(self.backup_to_btn, can_backup)
        _set_enabled(self.again_btn, can_backup)
        _set_enabled(self.restore_btn, self.app._can(roles.RESTORE_BACKUP))


# ----------------------------------------------------------------------
# Tab: Business Info (the owner's own business profile)
# ----------------------------------------------------------------------

class BusinessInfoTab(ttk.Frame):
    """
    A form for the owner's business details: name, address, contact,
    and a tagline. This is YOUR information -- it is stored in this
    data file and appears as a header on your reports. It is private
    to this set of books; if someone else uses Ledger with their
    own file, they fill in their own details.
    """

    # Wording for each mode. Only the labels change -- the fields, the
    # accounts and the reports work exactly the same either way.
    LABELS = {
        "business": {
            "title": "Business information",
            "intro": ("These details belong to this set of books and "
                      "appear as a header on your reports. They are "
                      "private to your data file \u2014 they are not part "
                      "of the program, so anyone else using Ledger "
                      "fills in their own."),
            "name": "Business name",
            "tagline": "Tagline / slogan",
            "save": "Save business info",
            "tab": "Business Info",
            "saved": ("Your business information has been saved. It will "
                      "now appear as a header on your reports."),
        },
        "personal": {
            "title": "Your information",
            "intro": ("These details belong to this set of books and "
                      "appear as a header on your reports. They are "
                      "private to your data file. Use this when you are "
                      "keeping personal books rather than a business's."),
            "name": "Your name",
            "tagline": "Subtitle (optional)",
            "save": "Save my information",
            "tab": "Profile",
            "saved": ("Your information has been saved. It will now "
                      "appear as a header on your reports."),
        },
    }

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        wrap = _centered(self)
        ttk.Style().configure("TRadiobutton", background=BG, font=FONT)

        self.title_label = ttk.Label(wrap, text="Business information",
                                     style="Title.TLabel")
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.intro_label = ttk.Label(
            wrap, text="", style="Muted.TLabel", wraplength=820,
            justify="left")
        self.intro_label.grid(row=1, column=0, columnspan=2, sticky="w",
                              pady=(2, 12))

        # --- Business / personal: shown, not chosen here ---
        # This is decided once, when the set of books is first set up (and it
        # drives encryption), so the profile screen simply shows it rather
        # than asking again.
        chooser = ttk.Frame(wrap)
        chooser.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(chooser, text="These books are for:").pack(
            side="left", padx=(0, 10))
        self.kind_var = tk.StringVar(value="business")
        self.kind_display = ttk.Label(chooser, text="Business", font=FONT_BOLD)
        self.kind_display.pack(side="left")

        # --- Name ---
        self.name_label = ttk.Label(wrap, text="Business name")
        self.name_label.grid(row=3, column=0, sticky="nw", pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(wrap, textvariable=self.name_var, width=48)
        self.name_entry.grid(row=3, column=1, sticky="w", pady=4)

        # --- Tagline / subtitle ---
        self.tagline_label = ttk.Label(wrap, text="Tagline / slogan")
        self.tagline_label.grid(row=4, column=0, sticky="nw", pady=4)
        self.tagline_var = tk.StringVar()
        self.tagline_entry = ttk.Entry(wrap, textvariable=self.tagline_var,
                                       width=48)
        self.tagline_entry.grid(row=4, column=1, sticky="w", pady=4)

        # --- Address (multi-line) ---
        ttk.Label(wrap, text="Address").grid(row=5, column=0,
                                             sticky="nw", pady=4)
        self.address_text = tk.Text(wrap, width=46, height=4, font=FONT,
                                    relief="solid", bd=1)
        self.address_text.grid(row=5, column=1, sticky="w", pady=4)

        # --- Contact (multi-line: phone, email, website) ---
        ttk.Label(wrap, text="Contact").grid(row=6, column=0,
                                             sticky="nw", pady=4)
        self.contact_text = tk.Text(wrap, width=46, height=3, font=FONT,
                                    relief="solid", bd=1)
        self.contact_text.grid(row=6, column=1, sticky="w", pady=4)
        ttk.Label(wrap, text="(phone, email, website \u2014 one per line)",
                  style="Muted.TLabel").grid(row=7, column=1, sticky="w")

        # --- Save button ---
        btns = ttk.Frame(wrap)
        btns.grid(row=8, column=1, sticky="w", pady=(14, 0))
        self.save_btn = ttk.Button(btns, text="Save business info",
                                   style="Accent.TButton",
                                   command=self._save)
        self.save_btn.pack(side="left")
        ttk.Button(btns, text="Revert",
                   command=self.refresh).pack(side="left", padx=6)

        # --- live preview of how the report header will look ---
        ttk.Label(wrap, text="Report header preview:",
                  style="TLabel", font=FONT_BOLD).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(18, 2))
        self.preview = tk.Label(wrap, text="", bg=PANEL, fg="#222222",
                                font=FONT_MONO, justify="center",
                                relief="solid", bd=1, padx=20, pady=10)
        self.preview.grid(row=10, column=0, columnspan=2, sticky="w")

        # Update the preview as the fields change.
        self.name_var.trace_add("write", lambda *_: self._update_preview())
        self.tagline_var.trace_add("write",
                                   lambda *_: self._update_preview())
        self.address_text.bind("<KeyRelease>",
                               lambda _e: self._update_preview())
        self.contact_text.bind("<KeyRelease>",
                               lambda _e: self._update_preview())

        # Start with the business wording in place.
        self._apply_kind_labels()

    def _apply_kind_labels(self):
        """Set every label to match the chosen business/personal mode."""
        kind = self.kind_var.get()
        words = self.LABELS.get(kind, self.LABELS["business"])
        try:
            self.kind_display.config(
                text="Personal" if kind == "personal" else "Business")
        except Exception:
            pass
        self.title_label.config(text=words["title"])
        self.intro_label.config(text=words["intro"])
        self.name_label.config(text=words["name"])
        self.tagline_label.config(text=words["tagline"])
        self.save_btn.config(text=words["save"])
        # Rename the tab itself so a personal user isn't looking at a tab
        # marked "Business Info".
        try:
            self.app.tabs.tab(self, text=words["tab"])
        except Exception:
            pass

    def _current_values(self):
        return {
            "name": self.name_var.get(),
            "tagline": self.tagline_var.get(),
            "address": self.address_text.get("1.0", "end").strip(),
            "contact": self.contact_text.get("1.0", "end").strip(),
        }

    def _update_preview(self):
        v = self._current_values()
        lines = []
        if v["name"]:
            lines.append(v["name"])
        if v["tagline"]:
            lines.append(v["tagline"])
        if v["address"]:
            lines.extend(v["address"].splitlines())
        if v["contact"]:
            lines.extend(v["contact"].splitlines())
        if lines:
            self.preview.config(text="\n".join(lines))
        else:
            self.preview.config(
                text="(enter your details above to see the header)")

    def _save(self):
        if not self.app.gateway:
            return
        v = self._current_values()
        try:
            # kind is chosen once during setup; saving here never changes it
            # (the gateway/host keep the stored kind).
            self.app.gateway.save_profile(name=v["name"],
                                          address=v["address"],
                                          contact=v["contact"],
                                          tagline=v["tagline"])
        except gateway.GatewayError as e:
            messagebox.showerror("Could not save", str(e))
            return
        self.app.set_status("Information saved", kind="ok")
        words = self.LABELS.get(self.kind_var.get(), self.LABELS["business"])
        messagebox.showinfo("Saved", words["saved"])

    def refresh(self):
        """Load the saved profile into the form."""
        if not self.app.gateway:
            return
        try:
            p = self.app.gateway.get_profile()
        except gateway.GatewayError:
            return
        self.kind_var.set(p["kind"])
        self._apply_kind_labels()
        self.name_var.set(p["name"])
        self.tagline_var.set(p["tagline"])
        self.address_text.delete("1.0", "end")
        self.address_text.insert("1.0", p["address"])
        self.contact_text.delete("1.0", "end")
        self.contact_text.insert("1.0", p["contact"])
        self._update_preview()

        # Role enforcement: editing the business profile needs EDIT_PROFILE
        # (owner/manager). Viewing stays available to everyone. The text
        # boxes are populated above first, then disabled, since a disabled
        # tk.Text cannot be written to.
        can_edit = self.app._can(roles.EDIT_PROFILE)
        for w in (self.name_entry, self.tagline_entry, self.save_btn):
            _set_enabled(w, can_edit)
        for t in (self.address_text, self.contact_text):
            _set_enabled(t, can_edit)


def main():
    app = LedgerApp()
    app.mainloop()


if __name__ == "__main__":
    main()


# ----------------------------------------------------------------------
# Embedded Ledger logo (PNG, base64). Used on the welcome screen when
# no logo.png/logo.gif has been placed in this folder. This is the same
# 'Ink & Brass' icon -- a ledger book on a monitor -- so the program
# always shows the real logo without needing a separate image file.
# ----------------------------------------------------------------------
_LEDGER_LOGO_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAKAAAACgCAYAAACLz2ctAAAABmJLR0QA/wD/AP+gvaeTAAAXq0lEQVR4nO2daXQU15XH/6+qunrVBlpYJJCQwMaIzRixGGxMYps4HhsM2MTxksTBiccndiYzyTjJyYdJSOycM5OZZDzJeB87OF4UIHbiJbYxYMsGgQGxiFUCISQQQhtSd1d3bW8+tJYWdEvVUnf19n7ncKSuevXqovr3rXffch/AYDAYDAaDwWAwGCZCzLhJ2dy1eTYrlusavQ4EUwnINEKQo4M6CUiGGTYwwkDpJYBcIsBFneiHCMgBnvCfHNz1xj4zbh8zAc5YsnYS/PQBEKwFITNjeS9GDKA4C0L+ynH0fw/trDwUq9tEXRTl89cs1gn5KSFYAYCLdv0M06EAdkDHr2v3VL4f7cqjJsDp160q53jhtwCWR6tORmJBgI8A4Z8PV792MIp1jo7i4mU2R17uBsJxjwHUEg2jGIkMUaBrT9Y623+B7dvVUdc2mounzVt9tYUnb4CQWaM1hJFcEEr3CpywpmbX6w2jqmekF5ZXrLldJ3iNgLhGYwAjeSGgrRRkdW11ZdVI6xhRkDCjYtUDlHCbmfjSGwqSD4KPZiy4e/VI6+AjvWBGxaoHQISXAAgjvSkjpRAAsqqgaMbx1qba2kgvjugVXF6x5nZKuM0s2GBcCVF0YOXR6jffjegqowWvrlg1jSP8F2zkghEOCuomPFla+3lljdFrDLUBi4uX2XjwlUx8jKEgIC5o9C8zl9ybY/QaQwJ05OVuYF0tDGOQybqiPGe09LBBSO8Ix4tGyjIYvVyTP+HqMxfPHR32VTysBwwMr7GggxEZhON+beRVPKQAy+evWQw2tssYARQkX5eVXw5XbkgB6oT8NHomMdIOgoemL75r8lBFwgqwfP66Io7DrdG3ipFGiJxGfjJUgbACpFAfpJQFHozRQu6fsWjtmHBnw7+CCdbGxB5GmkHsVNXvC3c2pADL5q7NAyHlsTOKkU4QwkUmQJsVy8OdYzAihmBe6axV+aFOhRSZrtHrYmsRI83g7HYSMqANKUBCyFWxtYeRbuiUVIQ6Hu41WxZDWxhpCCFcyJgijAeE4dkMDIYhKKaEOhxSgJSCTbtiRBmaFepo6FcwgT2mtjDSDxJ6Lmm4NiDrgmFEm5CaYkJjxJW4rGyjFJC8PZC8bsh+H3RdA6U0HqakLYQQCLwFos0GhzMLVpstLnaYLkDZL6GzrRWKKpt9a0YQlFIoqgzFLcPj7obdmYHsnDzwvLnzT0wVoNfTg862C6Bg3i7RkDw9UGQfcvMnQhDMmwBvWhsw4PmY+BIZVVHQduEcdF037Z6mCJBSoLOtlYkvCVBVGV0dF027nykClLw9rM2XRHg9PVBkvyn3MkeAHrcZt2FEDQqvp9uUO5kiQFnxmXEbRhTxSR5T7mNKFKxrmuGy+QW5KJlcBMHCkm9FE0VWUF/fgPaOLkPlVXXUyU8NYcpTNtLJbLPZ8LOfPIav3bMShLCE+rFAVTU8/fsX8d+//79hI12zBgYSZijuZz95DPeuW8XEF0MEgcf3H1uPR7/7YLxN6SchBJhfkIuv3bMy3makDY/+4zdgi9PQ2+UkhAAnFxUyz2ciVlHE9KtL420GgAQRIM8nhBlphdVqjbcJABJEgIz0hQmQEVeYABlxhQmQEVdSarihra0T9afOou50I5qaLsDrleD2SnB7vHD3eGG3W+Gw2+FwWuF0ODB2TDZKiieieHIhiiePh92krgnJ58PphnM409iM0w3NaO/ogsfrhdfjh1eSIEl+uDIccDkdcDnscDjsKCwsQFnJJJROKUJubuqsmk1qAXZ0XsInn36BbZ/sQc3Bo7jUPfJJD4QQjCvIxbVzpmNhxWwsnD8beXnRedAXL3Zi554DqN59APtqjqLlQtuoRhqyMl2YO3s6li2djxuWXocxOSFXPCYFSSnA9z/4DK//+V0cPHwcuh54kDabiJkzyjC1dBKmlU3GlOKJyMxwwuV0IDPTCZfTDknyw+2R4PEG/rW0tKHudBPq6s+i/nQTzja34J33P8E7738CACidMgk33TAfd/7DchRNHBeRjWebW/DWXz/Gtk/2oP5UY/9xnucwuWg8SksKUVZahLKSQowblwunww6nww6X0w673Qq3R0J3twdujxfdPR6camjGibozOFF3BnWnzmL7p3uw/dM94HkOs8qvwj2rv4IVt1wfvT+ySSSlAD/YWoWag8dQPGkCbr5pAb60rALz582AMMr1DB6PhJ17DqJqZw0+/Xw/6k41ov5UI154eTPmzyvHXXfcjOXLKiCKoaesy7KCrTuqseWtj7Bn7+F+L1c2pQhLF8/FkkVzsKhiFpyO4Zddjx2THfacqmnYs7cWW7fvxofbqrH/wFHkZGcwAZrNH/7zx7jm6pAZH0aE02nHl5ctwJeXLQAAnDt/EZve2orXN3+A3V8cwu4vDmHs2Gw88u17sPKOL/ULXtU0/OXtrfjD82+gvT0w26SosAD3rLoFq+/8EiaMz4uajQAg8DwWVczCoopZuOuO5fjK6u9FtX4zSWoBxpoJ4/Pwve+uw6MP34OqXfvxpzffx9+3fo4Nv34Gr77xDh5/9D5QSvG737+K0w1N4DiC225ZgnvXrsD1C+eA49jw4nAwARqA4whuWHwtblh8LY4eP42nfvMStlftxfd/+FR/mWVL5uGJH3wT068qiaOlyQcTYIRMv6oELz/zc+zcfRDrvvljAMDrLz2JRRVsJ7ORwDqiR0if4EjQ74zIYQJkxBUmQEZcSak2YFuXB7tqzkC08HDYRThsFjhsIhz2gZ92qyVhJ79SSiH5FXglBV6fPPDTp8AryZAVDQvnTEZutjPepkaNlBIgAGi6jktuBZfcoZeCEkJgtwq9Au0TqWXgs90CixCbBD2KqgWJq1dYvoHPkl8dcohOtKTexlUpJcDcbCfuXF5u6EF7fQqA0GtfLQIfJMqA9ywanw2nXTRkh0eScfZ81yDv5fUpUNTwy1Pj+cWIJyklwD4sAo+sDB5ZGaFntwz3qvP6Ah402Iv2eP2YX15k6P5H6i+gobnjSptctqRsGsSSlBTgcBBCer2MCCB0eyrYi/r8KvLHugzXf01pAXKznbBZhZT2XtEgLQVohOG86FA47SJKCsNuEMkIIqUE6JFkHD7ZclkUHGhH2UQLkuUNRyngk5XB7dfeKLh86jjDbdFkIKUE2HnJi8bznSHPcRyB3RoUWAS3xXo/CyYtD1U1PUhcg9uegSBJ6Z/neDkT8zOZABOVwnHZuMVpg0eS4ZFkeH0ypCAP0nc8HKKFvyw4GPCiOZkOw7NbdJ2is9s7yHsFBzuyMnSypuAvir33S+K0B/6NpEmQyKSUAAEgK8MW9iHpel/0G/A2HqlPoAOfu3okdPVIV1xbNikXc6dPNGTDgePnUNfYFvIcz3PIdNn6va/dZoEzyCvbrZa0msaVcgIcCo4j/Z4kHLKi9noqpd+L+vwKJuRnGr7PhPxMyIoKm3XAewUEZoHI0s4Ngv01LkO0CBAtArIzR75bWcHYDBSMZdvtGSGlBKhqOs62dA2MZNhE2KzJ/V/0+dX+JoKiaigal21asGQGyf10LqOppQtfHD476BjPkUDbKijidQZ/tovg49Tm0nTaH6BI/a98ZSB4kmRol0XDBEDxxNTpY0wpARaOy4aq6XB7/b3RpwLJJ6PH40ePJ3zWd5sowN4f/fYJVBy1Fw32XpJPHhBYr10+eeg0uDZRQGaQXS6HFYXjwq+WS0ZSSoACz6FsUu4Vx414Gl+3F51hEsPzHMHMaeMxdbKx1W0nz1zEoRPnr/Bel9eZ4bQmpGc2k5QSYDj6HnaGM3xOvCG9lT/yPU4sFh6Z1uh71VSD/RV6sVkF2KwCxkQhy8XUyXmGvWW6kzrhVC8eSYasmLPFgJnIijrkKE6yklIesKmlCzsPnAEQGHFwBo33JvKIg5ERGk0LbKuwaPbklApEUkqAOVkOFBZkwe0NBBzdbh+6w0zNB8KPuUZ71CLU6ErwGLXkV4a8XrTwyHDY4XKIyMlyRMWmRCGlBOi0i1g0p7j/s5FZJ5JfQXuY+oK96LTiPMOjGxfae3Ci4eIV3isUfcODiTBLJx6klAAvR+gd+M90hZuaH3reXfDMlT4v6nJYDQvwXGs3Wtp6AAx4r1AzbCKZp1j32R/RfPgDTCy/BWXX32/4b5DopLQAh4OQwGvYbrVgbJgyqqbDL6uwW43vIj77qgmYVpwHqyhExXsd2/YM9v/l5wCAc0c+RvbEa5BbPG/U9SYCaS1AIwg8ByHCCaB9r9Vo0Lj/bdS8tWHQMb8n9KTbZCR1GxcpQGv9Luzc+DgoHWhD5pUuwITpy+JnVJRhAkxQLrWcwKfPfwt60E7zmQVTccO3XwThUufFlTYC9PkSoxNXU/yQvZeGLNPV2oQdz9w/qJw9Mx/LvrsRoiN1+gCBFGkDqpqGk/WNOFl3FifqGnCivhGNjS1we739ib77ukKczkAicKfDjtyx2SgtKUJpyURMLZ2E0pIiFBUWxMzO1rqd2P7sN6DJXsgFt+KobzbqT59FW3sXPF4Jbo8Exe/GI/PqMD5jYFmAqgv4tPtG1G38GNPKijG1rAhTSyeNOid2IpDUAvxwWzX+8EIldlTtC7tFg8vlRO7YHNisIjRNR4/bg/aOblxo7cCphmbs3ls7qPz4gtxAQvHFc7Fk4ewhk4Ubob2jC1U7a1C1swY5515CSUbATrHlPXSc3ofd9eMBAIIgIMNpxYOzzmO8c0B8OgVeOTAJJ9pPAh+d7D+elenCsiXzUDrFWLaGRCWpBfibpzcCAESriAUVszCtrBilxYUoK5uMwonjkJ0VPpuB7JfR2t6JhoYmnG5oxqkzzTh5sgFHj5/Cm1s+xJtbPgQhBNfOvhrr1tyK21cshcNubEWaV/Lhb+99gtc3fYB9B471Jxy6fRqHkqCuxJtKLuDu1Ssw86tPQBQtOLzlX9G077OBAoRg1l1P4dkfrUBTcwvq6s6gvqEJJ+oasP/AMbz17o7I/2gJRtIK0Ol0YOn1c7H8hoVYsnguHAa2PghGtIoonFCAwgkFWLJ4oE+tx+3B7i8Oo3rPQXy+cz/21hzF3pqj+LennsWdt92I++65LWxm/iPHTmHjG+/irXd3wO32AgCKJo7DooVzsHD+bMybU4YTWx5He/3n/ddc3PcyzmQ4QTgOTfs2Daqv7KbHUXjtGgBAdlYZyq8p6z/n9Uqo+nw/tu7YharP90f0f08kQvbBz1iwduTb+ISg6czJIc8vXHAtXvvj/xiu79TpsyicOC7sfh3RZP+Bo9j81kf48OOd8Pn8IITg9hVL8S+P3Y8bv7IeBMC2d5/Dv//uFbzz9ypQSmGzWXHz8kW4684vY+7s6YPq0xUf9r76MNrrPgt9w14K592N8lVPGrJRlhU0NbdgSonx1/HX7n8Uu6r3DW3D5KmG6zNCbXXlFXpLSgHGA7fbg7+9vwMvvLwZFy92QhAEqGpg2lff73l5OXjowbtw+4ob4XKFTyKpKz7s3bh+kCcMJnfaMsy775mYdrckigDTphtmtLhcTqxbcxvernwa33loLYSgbFeCwOM7D63F25VPY92a24YUHwBwFhvm3fccxpYuvuJc1oRyzF33u5Tq6xsKJsAIsdtseGT9Orz95tPgeR4cz2Hza/+FR9avi2i3zX4Rlg1sr+XIKcK8+58HL6ZOCt7hSI+vmUF0XQelFJQO/A4MtEb0oPS5GZkOvPzcLwEAOTmZkHwD8w65QdNbCAgh4DgOhKD/d6BPhM+j4bMXIEtdKF70TYgZ6TWVP6UFqOs6VFWDpmvQNA1Up9A0HbquQ9cpdF3r/amDIvJmb052oE+lo6Mr4msJAkLkOILMGevAcQQ+ykHpcYNwBAIvgOM4CALfL9hUJOkFSCmFoqhQNRWqokFRVGiaClXVRiQqs6CggS+GDgBDr2EhIBAEHjwvwGIRIFh4CL2/J3ta36QTIKUUsizD71fg9/shK0NPZ08FKCgUVYWiqvBdtr5etFhgtVphtVogimLSCTJpBKgoKtxuDyTJl9CezWxkRYGsKOhxBzyl3W6Dy+WEJUmycCWFlZLPN6J2VrpBQeGVJHglCWPGZEcUlceLpGjd+qTweV0YoUmWv1lSCDArKwMO+8jz9aUbDrsdWVnJkZ8wKV7BHMchJycLGRkuSD4Jfp8MWVZYW7AXAgJRtMBqE2G32QeN0iQ6SSHAPgSBR4bLhQxXIBrui4ID3S8KVG3o5N+pgsDzsFgsECx8fxScbNFvH0klwGAIIbDZbLAFNbT7+gT7Op41VYeqqtB1HZqmQ9OTQ6A8x4Pnud6OaAG8wIHnefAcnxJ9f8EkrQBDQQjpnaIVfppWnxj7hto0XYOu6wDFoCE4Smn/Xh3Bq9ICn+kVu1oSQq4QBiG9Q24c6T/fNyQHEmha8Bzff7xPdOlESgnQCIHhr/R6yIkMexKMuMIEyIgrCSHA8+cvxNuEtKMnzCpCs0kIAZ5pbMbhI8fjbUbacLbpHI6frI+3GQASRIAA8IMf/hytreEy9TGihdfrxQ+f2ABVTYwuqYSJgk+ePIWvrnwAjzx8P6ZOLQGXON+NlOFUQyOef/E1NJ5tjrcp/ZgiQJ7noRkYpWhr68AvfvVbEyxiDAdvUtoPU9yMIIbfn4ORmPC8OS9HUwTocIRPkcFITGx2c1bmmSNAZ6Zp3yjG6CEgcDiN7488GkwRICEEOWPSa7lhMuPMyIZgiX3aE8DEbhibw4XM7HCpwBmJgmi1I2uMec/J1PdiZtYYcITDpa62K2aTMOKPzeHE2LHjQEKnDIoJpjfMXJnZsNrsuNTZBp9PAtis5rhjsViQkZULh9P8YDGcAHXE8PVsEa3ILZgITVPg9/mhqQp0Gn43oXgi+yT4/dLwBUNgtdoh2hJzLQshBIJggShaIViis6XEMIR8wCEFSAE3AWIeBvG8BQ6nOY3dkdLd1T5yAdrsrN3bCwX1hjoe0ssRSsPsHc5gjAxC0RPqeEgBUpBTsTWHkW4QSkLONAn5CiZALYAbYmqRyVBK0dPdCcXvgx5B4KOpI8894/X2wC+H3y72cgjhYLPZ4XRlG9rAMJmgBCHT5IYJQvRqgHsklgaZCaXAxQtNkP3GxRANVEWBGmHyJJ/XDZ/Pi9y8CTGyKl6QkAIMHelS7u8IE7UkIz7Jbbr4RoPP64HP54m3GVGFJ9yeUMdDCrB2T2ULoUje3P+XoWnJl8JNVRJja7EoocvUvy3UifB9fZz+SszMMRmrzYEwGwIkLBYx8TNbGYXoqDm2e0vIICSsAAWf9gooHVkHWIJhsViRlT0GySLCjMxsWK2J2YE9EghQOcS58MxYsOZZgKyPvknxQfb74PN5E3YcmiMcRKsd1iTI6xcBOiwoqa2qbAx1csixYAsRfqVQ7UEApozVxBrRaoNoTamHm/hQ+m5t1Z9Dig8YZry3ZtfrDaB4IfpWMdIFytENQ50fdsIBJ1p+SkBbo2cSI4344MiuTdVDFRhWgIeq/tRJKf1R9GxipAkygH8arpChKVe1uze9DGDTsAUZjD4ofltbXXlkuGKG5/xxFst6UIRtTDIY/VC639/h/pmRooYFeKjqT526rn4VlF4auWWMVIeCuomqfb2u7j1DafojmvV89Isth3XC3QuQ5BvbYpiBDIK7D+/bctToBRHnX2hrrj05blL5MUqxciTXM1IWnUD7Vm31pohihREJqLWp9khBUXktCF2JBEpwxIgbMoH2rcPVm/8Y6YWjGhydsWDtEgK6iYLkj6YeRvJCgW4Quu7Irj+/N5LrR7Xyrba6skogwgJC6d7R1MNIUiitodCvG6n4gCi04VqaDne1Ts1/MV+2A4RbHI06GQmPDIrf+Ds8Xz9x6O1RjZJFdX7SzEVrZ1Id/0GBm6NZLyOh+IAo6vcjiXSHIiYT5GZU3H0rCH0CwI2xugfDPAiBRnX6HuXohuHGdiOuO5qVXc7MRWtnahoeJsAdIJgUy3sxoo5OdNQQoJJw4saD1a82xeImpnmn2YvWzdWoslTXyBxCSDkIzQdFFgjJNssGxpVQ0B5C4QbQAZATADnJE26PTP3bwk2jZzAYDAaDwWAwGIyk5f8BaSNc8b9smZYAAAAASUVORK5CYII="

# Same logo as a GIF, for older Tk builds (8.5) that cannot read PNG.
# Flattened onto the welcome background so it blends with no alpha.
_LEDGER_LOGO_GIF_B64 = "R0lGODdhoACgAIcAAP////7+//39/v79+/z9/vv8/fv8/Pr7+/n6+/f4+/b4+vf3+fX3+fX29/T2+ff18/L0+PHz9/Dy9+7y9+/x9u3x9u3w9ezw9fTt4+zv9Ozt7+vv9Ovu8uru9Ort8+nt8+js8ufs8ejr8efr8ufr8efr8PDo3ubq8ebq8OXq7+To7uPo7+Pn7+Ln7+Ln7OHm7eHm6+Tk5eHl6+Dl7eDk6+Di5t/k7d7k7d7j7N7i6dzh693h6Nzh6Nvh6+fe0Nzg59vf59rg69rg6tre5tre5djf6tnd5tnd5Nfd6djc5djc49Xc6Nfb4tba4tfZ39Tb59Pb59LZ5dbY3tTY4NPY39DY5NXX3dDX487W5M3V48zU48rT4sjR4cjR4MnQ3drEo8bP38XP38TO3sPN3sLM3cbJ0sHL27/K3MLI0r3I28HFzbvG2rrF2b3DzrnE2LjE2LfD17TA1bm9yLO/1bK/1LK+1LC906+806270syzjrO3wq260ay60au50bG2wa+0wKq40KmtuaeuvLqge52ktJedrJOZqJCWprmSVa+CQYmQoIWMnoOJm3+GmXmAk3R8kahyIKZuGm93jGx0iWpyiGVvhHdrX2BpgF5mfnJdRFVgeFRedlBZc0pUbkpTZUlTbkdQa0dPYkRNY0FMaEBKZj5IYjtGYTRGbjNGbTlEYTRFbTNFbDNEbDNEazNEajNDaTJEajJDaTJCaDFCZzg/VjFBZjFBZDFAYzE+XjA/Yi89YS89YC89Xy85VS49Xi47XS47XC07XC07Wy45Wi05WS05WCw5WS04WS04Viw4WCw4VSs4Vis4VSo4VSw3Vis3Vis3VSo3VC42Syo2VSo2VCo1Uyk1Uyg0USYyUScyTyUwTiUwSSIuTiEtTCAtTCAsSyMtSCEsRx8rSyArRh8qSiAqQx4qSh4oRB0oQx0nQhwnQholPxciPBghPBYhOhYfORQdNRMcNRIbMxAZMRAYMQ8YMQ8YMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwAAAAAoACgAEAI/wBPCRxIsKDBgwgTKlzIsKHDhxAjSjwYSxi0ixgzatzIsaPHjyBDihw5EtiriQlXESPJsqXLlzBjgiymCuJKmThz6typM9dCnkCDCh2qUSHMcPaSKl3KtKnTp1CjSp1KtWrSetpgGn35NNSEr2DDih1LtqzZs2jTqp0Q6qnWhDC7or1krhSjMgYA6N3Lty+ABnIajTJnTtwmQSDGghC0SRzhUY3kNPBLea+BMoxKmbuEtq3TtwjjOvV6lq6VvRvmuBmTBcmLDQwCVJ4NwBw52pUDMNjwAkmWMW7mbNhrZXNnty+3upRb2tzpvRJOBKnSJc0cQNizY7fDRgyWIi0yCP/ga5uvgAwtimARw8aOdu1z0nSpEuSEBL7FOZ/13BT0QdFNkWaWabhRloAFKwhxRRhr0CEEebftJQQda4RxhRArWJBAgX7ld9xnycHF1WhzOcfhiRCiWNkXkbQYiQ96ebgfci4p1xJzZnmR2FpntTEJNoVRUoNtP1DiGDaTtBGWBoi46GQkg5wFghcf9hdiaCMGWNYHO0xBxZdghinmmGSWaeaZaIY5xQ4flMUfU/4ZBCBTAvJo55145hnWm0vFWRBM7lgl6KCEFmqoUvD4SdAyRDUKTTpVpeMoUc0spMqkLJ1Tz6GGqoMpST5BFIszn5ZqakzNnISSQrNYdOqrRCn/A0wsq9Zq66245qorrrc8A+uvwC5Ty6qyAGvssR3x0tAvyDbrbEa+2PiSNvFwau212DbFzjU4SUsSVO8YUoGe5JZrbgeOyAOVogPNuVSd5sYrr518KsWuQO4qBe9YBKrIYRmEleEvhzKaVW9S956Sb1L7itXvwHodEB0ODqS4lwM42HcAxMQZNyOINYq4HInNPQdAATdkuCHHepXHMgAHrnBDAR3rZzCNLXk7Eo5lPewAGO29l11889VHAQKVuewXAhRIR511Qm/HBhgVx+jxzSDnLPKNJA9oogFS+KFIJaCYgkw3hFmDCymbOFJIGzXgpjRlPkASCSKObEIKLtaA//OkJYr4IUVeBbuJM0s6i8TzvGBdsEEHIJBQwuQpVJ4CGmhYnsLkJZAAQgcbXAAWB3kMEsO8B9uT8ML2NPxVBzAQ4WWatNduO5pTEAFDB1hbGTKWIzuFBuPEFz8WFepmjfjWLqGT7fPQW/tONDEpdMuz0EzzTvRUsYM9NLo0pAoy35ePaTC2ykK++ey3tMwsu8Yv//z012///fjnP/8qudzUPvbJ2IUr9BcL//3vgBwZRit0VQtfIfCBInkG/CYSCwdC8IIkucVDWqEMDHqwJcpaSC0+SMKWLDAh6yuhCkGSjMSt8IUYcWFItEEP7tnwhlKJhzWqxzySVAuHQAwiU/8SdaX/ZIkp4BiX8ZZIvBBsT3kkkeFHFsfEKpYrdas74rvUwgNCYAIZhAmjGMdYmFRQghBGwJMRCEGJVDiGjHA0BzIwQQgeqAWLRZSTFvVVIpO9TABqqMQ3zEGKP/yBFOb4BiXUMJ6XWc1mhoPiSKToESo6zESOpMzcMlmzKsEpj3/aI8P62BeJnUAHUeBCGuLQh6jdYTWtqVrLIqQXB/gGOHeIWh/ikAYuREEHGutL4ciCx98ZMXh0ImUtufCd8ChANhDbJIoCoAD0qIcLshzmWIqpNeBxTUsl4xjTnNYFEFhMLyAo2gmOxjFtioWby/MmSywZlocVoAcLWkMdogb/iDpU6EIq84s0Y6YgBu0zav60UA9o9khP9gmUBGGd68DyMAA4AGmZlCbEECBLALhzT4eLYg931rWeYZJD1LTmeoIGCCycEwBYkJp3wJOBZ87mC4j4Qic/5rtuHvObyQwnJ/ui0ROZwG4tSsQDdtq7TxpTj8jcYnMIow1NNIIQaMABWURABT0YQhKdQFthOBGIyexlbg0IBCfemAknDUIEFBiEk76AAzQQohGa0EYYIUnMkE5ypIorqRXDkoJFAMkc2FhECs7CJCclQgPxgqdI5fktwZqlAiBQAQ2AoITZ3e6ztpuCEoBAAxWAQIlpkexfKUtScIplB6CNrWxju4O+/0pSJJTsCD0vC4IUuCAHQDhCE2Y72yYcAQg5cEEKTnsn1eIWsCHZ7WCnm1q/Ppe1gX1KOQKnh+5697vgDa94x0ve8pr3vOI9hDSikkWXUCN5QoyvDemRjfbGRBvu2JR891soeIQjJwpxlQchRRVJffAYCxnGs8rB36WUA3urYEgrLAjDFQIjIsyqMAl3UatZUFjD7LNF/FCxiw+DGFbP2EVN9DcQV9ziF8QoBqlODBNmJKMYv9BFLSLM4h77+MdADrKQh0zkIhtZyKyoxS6CYQxkMIPGMHFGMobhi1yoKsiyCAaUSyWMYeFvFSXe8q9SjIr51aIZYm4WMmShq+ulGf97z/DyqmDx5DeXrxmwQMku7Py/X0hEwHxmHzJW3BAtB/qAz+DxQnJx6AcyQ9EIYUWjIUiMhex50g8UcUKMgekHCkMhJu50+ZyRW1Ejq9QfmUY42CGPeTT41VCZRzzWkRUAQ1ck4aghrHddFXjUl4fYDck0fsjrYlNlHcD+KUvaYexmU8VTEG3XS1wNFXCEwhPYzra2t83tbnv72+AOt7i5LQoGx9q+83yKIajLbh45Yl3Rxpco7SGKdttbLaWwbkhQrRHp3vvezt33rado2X8bnC36Bgm/M+LvsQxBDoZwxCQuoYlPbAITlXjEIgRRhsXKKwVlEMQiHlEJTGziE5r/uMQkHGEIOQyhuQn/yMIx4m9BcGKQiO2EJAohhzJYoQYaiIETvKCGQCziEqUQqzlGwQgqpIUKjBgMYbpRikssIhBq8IITYqCBGlihDHIoBFgP2w1OCMKh9oq3wuY90a9UFGIuMEQqCIMLQvBuAh0gBC4IYwpDuMCRHwVLwBU+8EoWvJ4n5aQUMCFGTEhhqA3lqVN9ClWgStVrfoR8UQF/tUj2NJ7KrqxrTZr5oW7+ZYH/yuBlXnjdHp6iJ92Ae4S2y17+MpizOb0pUalKVkbNDsOJfFMf+tRQRpWPQsWNbnhzSzfkMjtbeOkWtPNK1rgGNtDETeoRfluBBxsk/n67/+lpCXmPdt62n59s6FsbVMzvhQVC40MczsAFKOBgBBFgKG1Or5cCRGAEOAAFXHAGccAHQsMCTOV5kwd6lZduo0cW4tcXAuAAHjADS6AFZPAGeCA0LnVW5BdT74EHb0AGWrAEM+ABDtBIs7F9q+cRM3cR4Zd4mkd+kMeCMeeCrccRMWgyNqAdewAHZrAFT2ADIAABBHAi/LcXBAABIGADT7AFZgAHe6AdNpCA6LeA6teAotd+pDcbS9iETxiFUyg0e/AgHsgXQjCG7/GDQTiERXiElWGD3Ud430dwD8gvMjh+5WeF23SDHfGC0LCD74cdIkiCJoiCKsghSWgeFGiBGP+ogdiBgMKngMRHecZnecjnfn7hfwAogARogEJTiOZ0hnsBAhm4gfE3f/V3f/lHGXKYfqu1ftnFhRCYhwNTACn4UhOofyfCIi0CI+bHV304h6xXh4Z3h5dUepy0iLNRNy6CCAMwiVdYiQx4iQ5Ii3iojHuxABzDfwewVH5hAongIomAAfhxfsMIi9cli9H1em5nDocwCWA0RtOAC6WQCsjADWSUCo/wBxqgSTSoFxrwB4/QVi2SCYTBDb1gkC0iDWKEDJNwCOj4Tn7IEYAYftZQCYKgAnjyAgQ5d+ZADY7wHC5jBY5ADXzXjzXQJC6SB3ngJHkwFiogCJVgDcJIkcT/iIPG6HrIWEUuUAh7p4/moI+4UAguQBaN9SSIkAHm0oJ/mIMb0XBMlATd4A1ToBZJmQinE1kVuREX6Y5ocQG95QIykAM/MARK0ASeRVxgMgVNoARD8AM5IAMugAIgIDp64pQWCZX95o4VUAI0cARsOZifdQQ0UAKoNY1pV3wRxXZkkQKEGZmE6XE4qY7ex47gV3AXAFuS2ZmgtQN4WZlYGItayH6Xd1koIAM/wASe6ZlM8AMygAKJSYmLaYmNeXyjJC8X8AEkgAIqAAMyQAM5sANnOQRHcJxHoARMsJxMoATIeQRDEJc7kAM0IAMwoAIoQAIfEJpN2ZVFwZcMB5YH/0ddeumV4ElzTiEN47meE0AL3pkRX+kUtJAE7HlvKpA6qqN2MAFfztafTSEP6EYS4+CfBMoUBsaY0vYS4FCgBYpsAdoS50BtDMpr7FANMgGIG3EN4XAO6tChHvqhIBqiIjqiHfpEU/EOJJqiKjqi6BAOv2ZrCJEMJERgU3GgGNRCCcEL30MN6NAO7vCjQBqk7gAPvSakRsoO4zAN3+NnCSFpz7KgsLYN2CNnCOFmzZIN+tVgtdYsw9AQOvos2oAOKzqmY3oOW+oskKYQX2pqz0IrD2GlbGoszzBAEaEKMhqnv0IMhCYRHoanpiJBuFILjOKnjfIMmqYrraBghAoUxCuQZ/XjCsCwqDIRDFemP66wC3cqqR4xDLnACkf2qaAaqqI6qqRaqqYKEQEBADs="
