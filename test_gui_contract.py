# Ledger -- GUI contract tests (rebuilt)
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kelly's Computers LLC
"""
AST-based contract tests for ledger/gui.py.

These never start tkinter or open a window: they parse gui.py as source and
assert that the methods, helpers, wiring, and styling the GUI depends on are
present and shaped correctly. That makes them safe to run headless (no X
display) and fast.

The original suite's source was lost, so this file was rebuilt from the
current gui.py. It re-establishes a regression net over the existing surface
AND pins the new "Pull data from QuickBooks" import flow (Slice 1: UI shell).

Run:  python3 -m unittest test_gui_contract -v
  or: python3 test_gui_contract.py
"""

import ast
import os
import unittest


def _find_gui():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "gui.py"),
        os.path.join(here, "ledger", "gui.py"),
        os.path.join(os.getcwd(), "gui.py"),
        os.path.join(os.getcwd(), "ledger", "gui.py"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        "could not locate gui.py next to the test or under ./ledger/")


GUI_PATH = _find_gui()
with open(GUI_PATH, "r", encoding="utf-8") as _fh:
    SRC = _fh.read()
TREE = ast.parse(SRC)


def func(name):
    """First FunctionDef named `name` anywhere in the module (incl. methods)."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def func_src(name):
    node = func(name)
    if node is None:
        return ""
    return ast.get_source_segment(SRC, node) or ""


def arg_names(name):
    node = func(name)
    if node is None:
        return []
    return [a.arg for a in node.args.args]


def class_names():
    return {n.name for n in ast.walk(TREE) if isinstance(n, ast.ClassDef)}


def module_assigned_names():
    names = set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


class ExistingSurface(unittest.TestCase):
    """Regression net: the structure the rest of the GUI relies on."""

    def test_core_methods_present(self):
        for name in (
            "_build_header", "_build_tabs", "_show_workspace",
            "_refresh_signout_button", "_make_dialog_static", "_signin_card",
            "_login_over_wire", "_back_to_entry", "_entry_books",
            "_landing_sign_in", "_manage_books", "_center_dialog",
            "_dialog_border",
        ):
            self.assertIsNotNone(func(name), "missing method: " + name)

    def test_nine_tab_classes_present(self):
        tabs = {
            "EntryTab", "JournalTab", "ReportsTab", "ReconciliationTab",
            "AccountsTab", "BackupTab", "SecurityTab", "SharingTab",
            "BusinessInfoTab",
        }
        self.assertTrue(tabs.issubset(class_names()),
                        "missing tab classes: " + str(tabs - class_names()))

    def test_dialog_helpers_present(self):
        for name in ("_dlg_label", "_dlg_entry", "_dlg_button", "_dlg_radio",
                     "_dlg_check", "_show_hide_button"):
            self.assertIsNotNone(func(name), "missing helper: " + name)

    def test_palette_constants_present(self):
        names = module_assigned_names()
        for c in ("BG", "PANEL", "ACCENT", "HEADER_BG", "HEADER_BTN", "DLG_BG",
                  "DLG_CARD", "DLG_CARD_TX", "OK", "ERROR", "MUTED"):
            self.assertIn(c, names, "missing constant: " + c)

    def test_signin_error_type_present(self):
        self.assertIn("_SigninError", class_names())

    def test_card_border_colour_retained(self):
        # The signed-card / locked-card edge colour the sign-in work settled on.
        self.assertIn("#6f82a8", SRC)


class QuickBooksImportSlice1(unittest.TestCase):
    """Contract for the new 'Pull data from QuickBooks' UI shell."""

    def test_methods_present(self):
        for name in ("_quickbooks_import", "_quickbooks_scope",
                     "_refresh_import_button", "_qb_detect_format"):
            self.assertIsNotNone(func(name), "missing method: " + name)

    def test_import_is_zero_arg_method(self):
        self.assertEqual(arg_names("_quickbooks_import"), ["self"])

    def test_scope_takes_a_path(self):
        self.assertEqual(arg_names("_quickbooks_scope"), ["self", "path"])

    def test_header_builds_button_wired_to_import(self):
        hdr = func_src("_build_header")
        self.assertIn("qb_import_btn", hdr)
        self.assertIn("command=self._quickbooks_import", hdr)

    def test_button_visibility_wired_through_signout_refresh(self):
        self.assertIn("_refresh_import_button",
                      func_src("_refresh_signout_button"))

    def test_button_only_shown_for_open_local_book(self):
        ref = func_src("_refresh_import_button")
        self.assertIn('self.mode == "local"', ref)
        self.assertIn("self.conn", ref)

    def test_import_card_opens_file_dialog_and_advances(self):
        src = func_src("_quickbooks_import")
        self.assertIn("filedialog.askopenfilename", src)
        self.assertIn("self._quickbooks_scope", src)

    def test_import_card_offers_the_three_formats(self):
        src = func_src("_quickbooks_import").lower()
        for ext in (".iif", ".qbo", ".csv"):
            self.assertIn(ext, src, "file dialog missing format: " + ext)

    def test_scope_card_has_three_data_checkboxes(self):
        src = func_src("_quickbooks_scope")
        self.assertIn("_dlg_check", src)
        for label in ("Chart of accounts", "Customers & vendors",
                      "Transactions"):
            self.assertIn(label, src, "scope missing checkbox: " + label)

    def test_scope_card_has_date_range(self):
        self.assertIn("Date range", func_src("_quickbooks_scope"))

    def test_detect_format_maps_known_extensions(self):
        src = func_src("_qb_detect_format")
        for ext in (".iif", ".qbo", ".csv"):
            self.assertIn(ext, src)

    def test_dialogs_use_centered_titled_modal_convention(self):
        # In-app dialogs: titled, bordered, centred, grabbed -- NOT the
        # borderless pinned card (_make_dialog_static) used beside locked-page
        # branding.
        for name in ("_quickbooks_import", "_quickbooks_scope"):
            src = func_src(name)
            self.assertIn("win.title(", src, name)
            self.assertIn("self._center_dialog(win)", src, name)
            self.assertIn("grab_set", src, name)
            self.assertNotIn("_make_dialog_static", src, name)

    def test_slice1_imports_nothing_into_the_book(self):
        # Safety contract: the shell must not yet mutate the open book. No
        # commits, no SQL execution, no engine writes from the scope card.
        src = func_src("_quickbooks_scope").lower()
        for forbidden in ("commit(", ".execute(", "insert into",
                          "transactions.add", "accounts.add"):
            self.assertNotIn(forbidden, src,
                             "Slice 1 must not write to the book: " + forbidden)
        # And it should visibly say so (the stub notice).
        self.assertIn("not wired up yet", func_src("_quickbooks_scope").lower())


class AboutWindow(unittest.TestCase):
    """The About window must never clip its bottom buttons."""

    def test_no_fixed_clipping_geometry(self):
        # The fixed 460x440 was too short on some systems and cut off the
        # button text; the window should size to its contents instead, so it
        # must make no hard-coded .geometry(...) call.
        self.assertNotIn(".geometry(", func_src("_show_about"))

    def test_buttons_anchored_to_bottom(self):
        # Bottom-anchored so they always keep their full height regardless of
        # how tall the body text renders.
        self.assertIn('side="bottom"', func_src("_show_about"))

    def test_window_is_positioned(self):
        self.assertIn("_center_dialog", func_src("_show_about"))


class BrandingConsistency(unittest.TestCase):
    """Branding must be sourced consistently, with no leftover placeholders."""

    def test_no_company_placeholder(self):
        # "comPany" was a leftover placeholder in the welcome window title.
        self.assertNotIn("comPany", SRC)

    def test_welcome_title_uses_builder_name(self):
        self.assertIn("about.builder_name()", func_src("_show_welcome"))


class ImportHygiene(unittest.TestCase):
    """Dead imports were removed before packaging; keep them out."""

    def _module_imported_names(self):
        names = set()
        for node in TREE.body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    names.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    names.add(a.asname or a.name)
        return names

    def test_removed_dead_imports_stay_removed(self):
        imported = self._module_imported_names()
        for dead in ("subprocess", "sys", "time", "accounts",
                     "transactions", "reports", "host"):
            self.assertNotIn(dead, imported,
                             "dead import crept back: " + dead)

    def test_still_imports_what_it_uses(self):
        # Sanity: the modules the GUI actually drives must remain imported.
        imported = self._module_imported_names()
        for needed in ("database", "crypto", "about", "gateway", "host_main",
                       "hoststate", "tk"):
            self.assertIn(needed, imported, "lost a live import: " + needed)


if __name__ == "__main__":
    unittest.main(verbosity=2)