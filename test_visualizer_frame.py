#!/usr/bin/env python3
"""Headless frame tests for the UltimateOscilloscope TUI.

Phase 5 of the TUI refactor made the oscilloscope constructible without a
real terminal: global curses setup moved from the constructor to main(), the
SHM reader became injectable, and the frame loop split into tick() (one frame
of dynamic content) and handle_key() (input dispatch). These tests drive the
draw pipeline against a strict fake screen:

  - construction and full draw pass at a range of terminal sizes, down to
    degenerate 1x1, in both design modes, with no exceptions and no
    out-of-bounds writes
  - tick() output is deterministic: identical state -> identical writes
  - handle_key(): quit keys, design-mode toggle, resize reflow, unknown keys

No real curses session, keyboard, daemon, or shared memory is required:
curses.color_pair is stubbed (it needs initscr), the SHM reader is a stub
that reports unavailable, and the legacy event file read is patched out.

Run directly (`python3 test_visualizer_frame.py`) or via pytest.
"""
import curses
import os
import sys
from contextlib import contextmanager

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether  # noqa: E402
import style_catalog  # noqa: E402


class _FakeScreen:
    """Strict stand-in for a curses window.

    Records every addstr and raises curses.error on any write that a real
    terminal would reject (out of bounds, or spilling past the right edge),
    so the bounds-clipping in the draw pipeline is actually exercised.
    """

    def __init__(self, height, width, keys=()):
        self.height = height
        self.width = width
        self.calls = []
        self.keys = list(keys)

    def getmaxyx(self):
        return self.height, self.width

    def addstr(self, y, x, text, attr=0):
        if not (0 <= y < self.height and 0 <= x < self.width):
            raise curses.error(f"addstr({y}, {x}) out of bounds")
        if x + len(text) > self.width:
            raise curses.error(f"addstr({y}, {x}, {len(text)} chars) overflows")
        self.calls.append((y, x, text, attr))

    def nodelay(self, flag):
        pass

    def clear(self):
        self.calls.append(("CLEAR",))

    def refresh(self):
        pass

    def getch(self):
        return self.keys.pop(0) if self.keys else -1


class _NoShm:
    """SHM reader stand-in: never available, like running without the daemon."""

    def is_available(self):
        return False

    def read_event(self):
        return None

    def close(self):
        pass


@contextmanager
def _headless_curses():
    """Stub the curses bits that need initscr(), and mute the legacy file read
    so frames depend only on in-process state."""
    orig_pair = curses.color_pair
    orig_legacy = aether.read_event_legacy
    curses.color_pair = lambda n: n << 8
    aether.read_event_legacy = lambda: (None, 0.0)
    try:
        yield
    finally:
        curses.color_pair = orig_pair
        aether.read_event_legacy = orig_legacy


def _make_viz(height, width, style_name="neon_wave"):
    screen = _FakeScreen(height, width)
    style = style_catalog.load_style_module(style_name)
    viz = aether.UltimateOscilloscope(screen, style, shm=_NoShm())
    return viz, screen


def _seed_signal(viz):
    """Push a deterministic audio event through the real ingest path."""
    viz.state.ingest(
        {"type": "audio", "frequency": 440.0, "amplitude": 0.9},
        viz.config_model,
    )
    for _ in range(8):
        viz.state.add_scroll_sample(viz.config_model)


def test_construct_and_draw_at_small_sizes():
    for height, width in [(24, 80), (10, 30), (5, 12), (3, 8), (2, 2), (1, 1)]:
        with _headless_curses():
            viz, screen = _make_viz(height, width)
            _seed_signal(viz)
            for mode in ("OSCILLOSCOPE", "SPECTRUM"):
                viz.design_mode = mode
                viz.recalculate_layout()
                viz.draw_static_elements()
                viz.draw_frame()
                viz.draw_status()
                viz.clear_waveform_area()
                viz.clear_spectrum_area()


def test_tick_runs_headless_at_small_sizes():
    for height, width in [(24, 80), (5, 12), (1, 1)]:
        with _headless_curses():
            viz, _ = _make_viz(height, width)
            _seed_signal(viz)
            viz.tick()
            viz.decay_all()
            viz.tick()


def test_tick_is_deterministic_for_fixed_state():
    def frame_writes(style_name):
        viz, screen = _make_viz(24, 80, style_name)
        _seed_signal(viz)
        screen.calls.clear()
        viz.tick()
        return screen.calls

    for style_name in ("neon_wave", "classic_wave", "matrix_rain", "glitch_art"):
        with _headless_curses():
            first = frame_writes(style_name)
            second = frame_writes(style_name)
        assert first, f"{style_name}: tick produced no writes"
        assert first == second, f"{style_name}: nondeterministic frame"


def test_different_styles_render_differently():
    # Sanity check that the determinism test isn't comparing empty output:
    # two styles with different glyph sets should not paint identical frames.
    def frame_writes(style_name):
        viz, screen = _make_viz(24, 80, style_name)
        _seed_signal(viz)
        screen.calls.clear()
        viz.draw_waveform()
        return screen.calls

    with _headless_curses():
        assert frame_writes("classic_wave") != frame_writes("matrix_rain")


def test_handle_key_quit():
    with _headless_curses():
        viz, _ = _make_viz(24, 80)
        assert viz.handle_key(ord("q")) is False
        assert viz.handle_key(ord("Q")) is False


def test_handle_key_toggles_design_mode():
    with _headless_curses():
        viz, _ = _make_viz(24, 80)
        assert viz.design_mode == "OSCILLOSCOPE"
        assert viz.handle_key(ord("d")) is True
        assert viz.design_mode == "SPECTRUM"
        assert viz.handle_key(ord("D")) is True
        assert viz.design_mode == "OSCILLOSCOPE"


def test_handle_key_ignores_unknown_keys():
    with _headless_curses():
        viz, _ = _make_viz(24, 80)
        for key in (-1, ord("x"), ord("1"), 27):
            assert viz.handle_key(key) is True
            assert viz.design_mode == "OSCILLOSCOPE"


def test_handle_key_resize_reflows_layout():
    with _headless_curses():
        viz, screen = _make_viz(24, 80)
        screen.height, screen.width = 12, 40
        assert viz.handle_key(curses.KEY_RESIZE) is True
        assert (viz.height, viz.width) == (12, 40)
        # Same-size resize events are a no-op (anti-flicker optimization).
        screen.calls.clear()
        assert viz.handle_key(curses.KEY_RESIZE) is True
        assert screen.calls == []


_TESTS = [
    test_construct_and_draw_at_small_sizes,
    test_tick_runs_headless_at_small_sizes,
    test_tick_is_deterministic_for_fixed_state,
    test_different_styles_render_differently,
    test_handle_key_quit,
    test_handle_key_toggles_design_mode,
    test_handle_key_ignores_unknown_keys,
    test_handle_key_resize_reflows_layout,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} visualizer frame tests passed.")
