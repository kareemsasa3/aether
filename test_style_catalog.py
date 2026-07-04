#!/usr/bin/env python3
"""Unit tests for style_catalog.py.

Phase 5 of the TUI refactor moved style discovery/loading out of `aether.py`
and `ui/overlays.py` into `style_catalog.py`. These tests pin the shared
behavior both call sites rely on:

  - list_style_names(): sorted slugs of every style file
  - load_style_module(): loads a real plugin; FileNotFoundError when missing
  - load_catalog(): one entry per style with name/display/desc/module, and
    the 16 expected display names
  - resolve_style_name(): the CLI's selection semantics — 1-based numbers,
    out-of-range numbers -> None, anything else passed through as a slug
  - load_default_style(): returns a usable fallback style

All headless: styles import fine without a curses session, and a tmp
styles_dir exercises the failure paths without touching the real catalog.

Run directly (`python3 test_style_catalog.py`) or via pytest.
"""
import os
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import style_catalog  # noqa: E402
from test_styles import EXPECTED_STYLE_NAMES  # noqa: E402


def test_list_style_names_sorted_slugs():
    names = style_catalog.list_style_names()
    assert names == sorted(names)
    assert len(names) == 16
    assert "aurora" in names
    assert "neon_wave" in names
    assert "__init__" not in names


def test_load_style_module_valid():
    module = style_catalog.load_style_module("matrix_rain")
    assert module.STYLE_NAME == "Matrix Rain"
    assert callable(module.render_waveform)


def test_load_style_module_missing_raises():
    try:
        style_catalog.load_style_module("no_such_style")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_load_catalog_expected_styles():
    catalog = style_catalog.load_catalog()
    displays = {entry["display"] for entry in catalog}
    assert displays == EXPECTED_STYLE_NAMES
    for entry in catalog:
        assert entry["name"] in style_catalog.list_style_names()
        assert isinstance(entry["desc"], str)
        assert callable(entry["module"].render_waveform)
    # Sorted by slug, matching the CLI menu and picker ordering.
    assert [e["name"] for e in catalog] == style_catalog.list_style_names()


def test_load_catalog_skips_broken_styles():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "good.py").write_text(
            'STYLE_NAME = "Good"\nSTYLE_DESCRIPTION = "ok"\n'
            "def render_waveform(*a):\n    return None\n"
        )
        (tmp / "broken.py").write_text("raise RuntimeError('boom')\n")
        catalog = style_catalog.load_catalog(styles_dir=tmp)
        assert [e["name"] for e in catalog] == ["good"]
        assert catalog[0]["display"] == "Good"


def test_resolve_by_number():
    available = style_catalog.list_style_names()
    # 1-based indexing over the sorted slugs.
    assert style_catalog.resolve_style_name("1", available) == available[0]
    assert style_catalog.resolve_style_name("16", available) == available[15]
    idx = available.index("matrix_rain")
    assert style_catalog.resolve_style_name(str(idx + 1), available) == "matrix_rain"
    # Whitespace around the number is tolerated (input() strip behavior).
    assert style_catalog.resolve_style_name(" 2 ", available) == available[1]


def test_resolve_number_out_of_range_is_none():
    available = style_catalog.list_style_names()
    assert style_catalog.resolve_style_name("0", available) is None
    assert style_catalog.resolve_style_name("17", available) is None
    assert style_catalog.resolve_style_name("-1", available) is None
    assert style_catalog.resolve_style_name("99", available) is None


def test_resolve_non_numeric_passes_through():
    # Non-numeric input is treated as a slug; existence is the caller's
    # problem (the CLI reports "not found" and exits, as before).
    available = style_catalog.list_style_names()
    assert style_catalog.resolve_style_name("matrix_rain", available) == "matrix_rain"
    assert style_catalog.resolve_style_name("no_such", available) == "no_such"


def test_load_default_style():
    module = style_catalog.load_default_style()
    assert module is not None
    assert module.STYLE_NAME in ("Neon Wave", "Classic Wave")


_TESTS = [
    test_list_style_names_sorted_slugs,
    test_load_style_module_valid,
    test_load_style_module_missing_raises,
    test_load_catalog_expected_styles,
    test_load_catalog_skips_broken_styles,
    test_resolve_by_number,
    test_resolve_number_out_of_range_is_none,
    test_resolve_non_numeric_passes_through,
    test_load_default_style,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} style catalog tests passed.")
