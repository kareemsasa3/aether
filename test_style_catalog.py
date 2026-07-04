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
    slugs, and case-insensitive display names resolve; anything else -> None
  - load_default_style(): returns a usable fallback style
  - aether.load_style() at the interactive prompt: blank input selects the
    default style (neon_wave); invalid nonblank input still exits with 1

All headless: styles import fine without a curses session, a tmp styles_dir
exercises the failure paths without touching the real catalog, and the
prompt tests stub input()/time.sleep and capture stdout.

Run directly (`python3 test_style_catalog.py`) or via pytest.
"""
import builtins
import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout
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


def test_resolve_by_exact_slug():
    available = style_catalog.list_style_names()
    assert style_catalog.resolve_style_name("matrix_rain", available) == "matrix_rain"
    assert style_catalog.resolve_style_name("neon_wave", available) == "neon_wave"


def test_resolve_by_case_insensitive_name():
    available = style_catalog.list_style_names()
    assert style_catalog.resolve_style_name("Matrix Rain", available) == "matrix_rain"
    assert style_catalog.resolve_style_name("matrix rain", available) == "matrix_rain"
    assert style_catalog.resolve_style_name("MATRIX_RAIN", available) == "matrix_rain"
    assert style_catalog.resolve_style_name(" Neon Wave ", available) == "neon_wave"
    assert style_catalog.resolve_style_name("fire", available) == "fire"
    assert style_catalog.resolve_style_name("FIRE", available) == "fire"


def test_resolve_every_display_name():
    # Every display name in the catalog must resolve to its own slug, so the
    # names shown in the CLI menu are always valid selections.
    for entry in style_catalog.load_catalog():
        for variant in (
            entry["display"],
            entry["display"].lower(),
            entry["display"].upper(),
        ):
            resolved = style_catalog.resolve_style_name(
                variant, style_catalog.list_style_names()
            )
            assert resolved == entry["name"], (
                f"{variant!r} resolved to {resolved!r}, expected {entry['name']!r}"
            )


def test_resolve_unknown_name_is_none():
    # The CLI reports "not found" and exits gracefully on None, as before.
    available = style_catalog.list_style_names()
    assert style_catalog.resolve_style_name("no_such", available) is None
    assert style_catalog.resolve_style_name("", available) is None


def test_load_default_style():
    module = style_catalog.load_default_style()
    assert module is not None
    assert module.STYLE_NAME in ("Neon Wave", "Classic Wave")


def _load_style_at_prompt(user_input):
    """Drive aether.load_style(None) with a canned prompt answer, muting the
    menu output and the cosmetic post-selection sleep."""
    import aether

    orig_input = builtins.input
    orig_sleep = time.sleep
    builtins.input = lambda prompt="": user_input
    time.sleep = lambda seconds: None
    try:
        with redirect_stdout(io.StringIO()) as out:
            module = aether.load_style(None)
        return module, out.getvalue()
    finally:
        builtins.input = orig_input
        time.sleep = orig_sleep


def test_blank_prompt_input_selects_default_style():
    # Just pressing Enter (or entering whitespace) must not exit; it selects
    # the default style, neon_wave — first of style_catalog.DEFAULT_STYLES.
    for blank in ("", "   "):
        module, output = _load_style_at_prompt(blank)
        assert module.STYLE_NAME == "Neon Wave", f"input {blank!r}"
        assert "Loading style: Neon Wave" in output


def test_invalid_prompt_input_still_exits():
    # Nonblank-but-unknown input keeps the documented failure path:
    # report the style and the available list, then exit 1.
    try:
        _load_style_at_prompt("no_such_style")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit for unknown style")


_TESTS = [
    test_list_style_names_sorted_slugs,
    test_load_style_module_valid,
    test_load_style_module_missing_raises,
    test_load_catalog_expected_styles,
    test_load_catalog_skips_broken_styles,
    test_resolve_by_number,
    test_resolve_number_out_of_range_is_none,
    test_resolve_by_exact_slug,
    test_resolve_by_case_insensitive_name,
    test_resolve_every_display_name,
    test_resolve_unknown_name_is_none,
    test_load_default_style,
    test_blank_prompt_input_selects_default_style,
    test_invalid_prompt_input_still_exits,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} style catalog tests passed.")
