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


def test_canvas_defaults_to_spaces():
    c = render.Canvas(2, 3)
    assert c.get(0, 0) == (" ", 0)
    assert c.get(1, 2) == (" ", 0)


def test_canvas_set_get_and_clipping():
    c = render.Canvas(4, 6)
    c.set(1, 2, "X", 99)
    assert c.get(1, 2) == ("X", 99)
    # Multi-char input keeps only the first char (one cell per set).
    c.set(0, 0, "AB", 7)
    assert c.get(0, 0) == ("A", 7)
    # Out-of-bounds writes are silently clipped; reads come back blank.
    for y, x in [(-1, 0), (4, 0), (0, -1), (0, 6)]:
        c.set(y, x, "!", 1)
        assert c.get(y, x) == (" ", 0)
    # Empty char is ignored.
    c.set(2, 2, "", 5)
    assert c.get(2, 2) == (" ", 0)


def test_canvas_iter_runs_merges_same_attr_cells():
    c = render.Canvas(2, 5)
    c.set(0, 0, "a", 1)
    c.set(0, 1, "b", 1)
    c.set(0, 2, "c", 2)
    runs = list(c.iter_runs())
    # Row 0: "ab" with attr 1, "c" with attr 2, then trailing spaces attr 0.
    assert runs[0] == (0, 0, "ab", 1)
    assert runs[1] == (0, 2, "c", 2)
    assert runs[2] == (0, 3, "  ", 0)
    # Row 1 is one blank run covering the full width.
    assert runs[3] == (1, 0, "     ", 0)


def test_canvas_degenerate_sizes():
    for h, w in [(0, 0), (0, 5), (5, 0), (-2, -2)]:
        c = render.Canvas(h, w)
        c.set(0, 0, "x", 1)  # Must not raise.
        assert list(c.iter_runs()) == [] or all(r[2] for r in c.iter_runs())


def test_blit_canvas_offsets_and_clips():
    c = render.Canvas(2, 4)
    c.set(0, 0, "h", 3)
    c.set(0, 1, "i", 3)
    s = _FakeScreen()
    render.blit_canvas(s, 24, 80, c, top=5, left=10)
    # First run lands at the offset position.
    assert s.calls[0] == (5, 10, "hi", 3)
    # All writes stay within the screen bounds.
    for y, x, text, attr in s.calls:
        assert 0 <= y < 24 and 0 <= x < 80
        assert x + len(text) < 80


def test_blit_canvas_clips_offscreen_rows():
    c = render.Canvas(3, 10)
    c.set(2, 0, "x", 1)
    s = _FakeScreen()
    # Screen only 2 rows tall: canvas rows at y >= 2 must be dropped.
    render.blit_canvas(s, 2, 80, c, top=1, left=0)
    assert all(y < 2 for y, *_ in s.calls)


def test_frame_context_exposes_fields():
    ctx = render.FrameContext(
        frame=7,
        width=40,
        height=12,
        amp=0.5,
        bass=0.9,
        mid=0.4,
        treble=0.2,
        spectrum=[0.0] * 12,
        beat=1.0,
        silence_frames=0,
        columns=[(0.0, 999)] * 40,
        colors={n: n for n in range(1, 11)},
    )
    assert (ctx.frame, ctx.width, ctx.height) == (7, 40, 12)
    assert ctx.bass == 0.9 and ctx.beat == 1.0
    assert len(ctx.columns) == ctx.width
    assert set(ctx.colors) == set(range(1, 11))


_TESTS = [
    test_safe_addstr_writes_in_bounds,
    test_safe_addstr_clips_to_right_edge,
    test_safe_addstr_defaults_attr_zero_and_coerces_text,
    test_safe_addstr_skips_out_of_bounds,
    test_safe_addstr_swallows_curses_error,
    test_get_bg_char_center_line,
    test_get_bg_char_non_center_is_blank,
    test_canvas_defaults_to_spaces,
    test_canvas_set_get_and_clipping,
    test_canvas_iter_runs_merges_same_attr_cells,
    test_canvas_degenerate_sizes,
    test_blit_canvas_offsets_and_clips,
    test_blit_canvas_clips_offscreen_rows,
    test_frame_context_exposes_fields,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} render tests passed.")
