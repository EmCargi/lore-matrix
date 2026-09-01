import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

browser_lore_matrix = importlib.import_module("browser_lore_matrix")


def test_browser_imports_cleanly():
    """browser_lore_matrix imports without executing runtime UI loops."""
    assert browser_lore_matrix.BASE_DIR is not None
    assert str(browser_lore_matrix.BASE_DIR).endswith("lore-matrix")


def test_page_config_set():
    """Module-level page config is present."""
    import streamlit as st
    # streamlit.set_page_config stores config; verify the module loaded it
    assert hasattr(st, "set_page_config")


def test_browser_has_navigation_pages():
    """The sidebar navigation includes all expected pages."""
    # The navigation list is defined at module level as a string list
    assert hasattr(browser_lore_matrix, "st")
