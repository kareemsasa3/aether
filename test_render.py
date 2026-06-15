#!/usr/bin/env python3
"""Unit tests for render.py terminal primitives.

Phase 3 of the TUI refactor moved generic terminal helpers out of
`UltimateOscilloscope` into `render.py`. These tests pin the behavior that was
previously embedded in `safe_addstr` and `get_bg_char`:

  - safe_addstr writes only when (y, x) is on-screen
  - safe_addstr clips text to the right edge (width - x - 1)
  - safe_addstr coerces non-str text and defaults attr to 0
  - safe_addstr swallows curses.error
  - get_bg_char returns the center-line glyph on the center row, else blank

No real curses session is required: safe_addstr runs against a fake screen, and
get_bg_char's center branch is exercised with curses.color_pair stubbed (the
real one needs initscr()).

Run directly (`python3 test_render.py`) or via pytest.
"""
import curses
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import render  # noqa: E402


class _FakeScreen:
    """Records addstr calls; optionally raises curses.error like a real screen
    does when a write lands out of bounds."""

    def __init__(self, raise_error=False):
        self.calls = []
        self.raise_error = raise_error

    def addstr(self, y, x, text, attr):
        if self.raise_error:
            raise curses.error("simulated out-of-bounds")
        self.calls.append((y, x, text, attr))


def test_safe_addstr_writes_in_bounds():
    s = _FakeScreen()
    render.safe_addstr(s, 24, 80, 5, 10, "hello", 7)
    assert s.calls == [(5, 10, "hello", 7)]


def test_safe_addstr_clips_to_right_edge():
    s = _FakeScreen()
    # max width = 10 - 2 - 1 = 7
    render.safe_addstr(s, 24, 10, 0, 2, "abcdefghijk")
    assert s.calls == [(0, 2, "abcdefg", 0)]


def test_safe_addstr_defaults_attr_zero_and_coerces_text():
    s = _FakeScreen()
    render.safe_addstr(s, 24, 80, 1, 1, 42)
    assert s.calls == [(1, 1, "42", 0)]


def test_safe_addstr_skips_out_of_bounds():
    s = _FakeScreen()
    render.safe_addstr(s, 24, 80, -1, 0, "x")    # y < 0
    render.safe_addstr(s, 24, 80, 24, 0, "x")    # y == height
    render.safe_addstr(s, 24, 80, 0, -1, "x")    # x < 0
    render.safe_addstr(s, 24, 80, 0, 80, "x")    # x == width
    assert s.calls == []


def test_safe_addstr_swallows_curses_error():
    s = _FakeScreen(raise_error=True)
    # Must not propagate.
    render.safe_addstr(s, 24, 80, 5, 5, "boom")
    assert s.calls == []


def test_get_bg_char_center_line():
    orig = curses.color_pair
    curses.color_pair = lambda n: ("PAIR", n)
    try:
        center_y = 4 + 10 // 2  # waveform_start=4, waveform_height=10 -> 9
        ch, attr = render.get_bg_char(4, 10, center_y, 0)
        assert ch == "─"
        assert attr == ("PAIR", 2)
        # x is ignored for the center line.
        ch2, attr2 = render.get_bg_char(4, 10, center_y, 999)
        assert (ch2, attr2) == (ch, attr)
    finally:
        curses.color_pair = orig


def test_get_bg_char_non_center_is_blank():
    # Non-center rows never touch curses.color_pair.
    assert render.get_bg_char(4, 10, 0, 0) == (" ", 0)
    assert render.get_bg_char(4, 10, 8, 0) == (" ", 0)
    assert render.get_bg_char(4, 10, 10, 0) == (" ", 0)


_TESTS = [
    test_safe_addstr_writes_in_bounds,
    test_safe_addstr_clips_to_right_edge,
    test_safe_addstr_defaults_attr_zero_and_coerces_text,
    test_safe_addstr_skips_out_of_bounds,
    test_safe_addstr_swallows_curses_error,
    test_get_bg_char_center_line,
    test_get_bg_char_non_center_is_blank,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} render tests passed.")
