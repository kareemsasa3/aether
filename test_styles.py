#!/usr/bin/env python3
"""Characterization tests for the styles/ plugin contract.

The style plugins are the one stable seam of the TUI (see REFACTOR.md): each
file in styles/ exposes STYLE_NAME, STYLE_DESCRIPTION, and
render_waveform(i, amp, age, max_width, colors, sample_id) returning either
None or a (char, attr) tuple. These tests pin that contract before the style
catalog/loop overhaul:

  - the 16 expected styles are discoverable and loadable
  - every style declares STYLE_NAME / STYLE_DESCRIPTION and render_waveform
  - render_waveform returns None or (str, int) across a sweep of inputs,
    including tiny max_width values and extreme amp/age
  - render_waveform is deterministic for fixed inputs (styles with randomness
    seed a local random.Random(sample_id) so a sample keeps its glyph as it
    radiates instead of flickering every frame)

All headless: no curses session is needed because styles only combine the
integer attrs passed in via `colors` with curses.A_* constants.

Run directly (`python3 test_styles.py`) or via pytest.
"""
import importlib.util
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

STYLES_DIR = Path(_HERE) / "styles"

# The full expected catalog, by display name (STYLE_NAME).
EXPECTED_STYLE_NAMES = {
    "Aurora",
    "Classic Wave",
    "Cyberpunk",
    "Data Stream",
    "Dense Fade",
    "Fire",
    "Geometric",
    "Glitch Art",
    "Heartbeat",
    "Matrix Rain",
    "Minimalist",
    "Neon Pulse",
    "Neon Wave",
    "Pixel Art",
    "Rain Drops",
    "Starfield",
}

# Distinct sentinel attrs so a style mixing up color indices would show up.
COLORS = {n: n * 1000 for n in range(1, 11)}


def _load_all_styles():
    """Load every style module the same way the app discovers them."""
    modules = {}
    for path in sorted(STYLES_DIR.glob("*.py")):
        if path.stem == "__init__":
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[path.stem] = module
    return modules


def _sweep_inputs():
    """A grid of representative render inputs, including edge values."""
    for max_width in (1, 5, 40):
        for amp in (-1.0, -0.6, -0.05, 0.0, 0.05, 0.3, 0.72, 1.0):
            for age in (0, 1, 5, 20, 45, 79, 99, 150):
                for i in (0, 2, max_width - 1):
                    yield i, amp, age, max_width


def test_all_expected_styles_discoverable():
    modules = _load_all_styles()
    names = {getattr(m, "STYLE_NAME", stem) for stem, m in modules.items()}
    assert names == EXPECTED_STYLE_NAMES, (
        f"missing: {EXPECTED_STYLE_NAMES - names}, "
        f"unexpected: {names - EXPECTED_STYLE_NAMES}"
    )


def test_style_metadata_contract():
    for stem, module in _load_all_styles().items():
        assert isinstance(getattr(module, "STYLE_NAME", None), str), stem
        assert getattr(module, "STYLE_NAME").strip(), stem
        assert isinstance(getattr(module, "STYLE_DESCRIPTION", None), str), stem
        assert callable(getattr(module, "render_waveform", None)), stem


def test_render_waveform_output_shape():
    for stem, module in _load_all_styles().items():
        for i, amp, age, max_width in _sweep_inputs():
            result = module.render_waveform(i, amp, age, max_width, COLORS, i)
            if result is None:
                continue
            assert isinstance(result, tuple) and len(result) == 2, (
                f"{stem}: render_waveform returned {result!r}"
            )
            char, attr = result
            assert isinstance(char, str) and len(char) == 1, (
                f"{stem}: bad char {char!r} for amp={amp} age={age}"
            )
            assert isinstance(attr, int), (
                f"{stem}: bad attr {attr!r} for amp={amp} age={age}"
            )


def test_render_waveform_deterministic_for_fixed_inputs():
    for stem, module in _load_all_styles().items():
        for i, amp, age, max_width in _sweep_inputs():
            for sample_id in (0, 7, -3):
                first = module.render_waveform(
                    i, amp, age, max_width, COLORS, sample_id
                )
                for _ in range(3):
                    again = module.render_waveform(
                        i, amp, age, max_width, COLORS, sample_id
                    )
                    assert again == first, (
                        f"{stem}: nondeterministic for i={i} amp={amp} "
                        f"age={age} sample_id={sample_id}: "
                        f"{first!r} vs {again!r}"
                    )


def test_render_waveform_handles_degenerate_width():
    # max_width can get tiny on very small terminals; no style may crash.
    for stem, module in _load_all_styles().items():
        for max_width in (0, 1):
            for i in (0, 1):
                module.render_waveform(i, 0.5, 3, max_width, COLORS, 0)


_TESTS = [
    test_all_expected_styles_discoverable,
    test_style_metadata_contract,
    test_render_waveform_output_shape,
    test_render_waveform_deterministic_for_fixed_inputs,
    test_render_waveform_handles_degenerate_width,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} style contract tests passed.")
