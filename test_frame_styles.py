#!/usr/bin/env python3
"""Contract tests for styles implementing the full-frame render path.

Any style exposing render_frame(ctx, canvas) gets the whole waveform region
as a 2D canvas each frame (see render.FrameContext). These tests pin the
frame-style contract for every such style, alongside the legacy
render_waveform contract in test_styles.py:

  - render_frame paints a non-blank scene when a signal is present
  - it also paints a non-blank ambient scene during long silence (the
    screen must stay alive when nothing is playing)
  - identical context sequences produce identical canvases on a fresh
    module load (determinism: styles animate off ctx.frame and seeded
    randomness, never wall-clock or unseeded random)
  - degenerate canvas sizes never raise

All headless: canvases are plain buffers and colors are sentinel ints.

Run directly (`python3 test_frame_styles.py`) or via pytest.
"""
import importlib.util
import math
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import render  # noqa: E402

STYLES_DIR = Path(_HERE) / "styles"

COLORS = {n: n << 8 for n in range(1, 11)}


def _load_frame_styles():
    """Fresh-load every style module that implements render_frame."""
    modules = {}
    for path in sorted(STYLES_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "render_frame"):
            modules[path.stem] = module
    return modules


def _make_ctx(frame, width, height, *, amp=0.0, bass=0.0, mid=0.0, treble=0.0,
              beat=0.0, silence_frames=0, columns=None):
    if columns is None:
        # A decaying sine wave radiating from center, ages growing outward,
        # roughly what the engine feeds the real renderer.
        center = width // 2
        columns = []
        for x in range(width):
            dist = abs(x - center)
            a = amp * math.sin(dist * 0.35) * (0.98 ** dist)
            columns.append((a, dist // 2))
    spectrum = [
        min(1.0, max(0.0, amp * (0.4 + 0.6 * math.sin(frame * 0.1 + i))))
        for i in range(12)
    ]
    return render.FrameContext(
        frame=frame,
        width=width,
        height=height,
        amp=amp,
        bass=bass,
        mid=mid,
        treble=treble,
        spectrum=spectrum,
        beat=beat,
        silence_frames=silence_frames,
        columns=columns,
        colors=COLORS,
    )


def _painted_cells(canvas):
    return [
        (y, x, ch, attr)
        for y, row in enumerate(canvas.cells)
        for x, (ch, attr) in enumerate(row)
        if ch != " "
    ]


def _run_sequence(module, frames, width=72, height=18, **ctx_kw):
    """Render `frames` consecutive frames, returning the last canvas."""
    canvas = None
    for f in range(frames):
        canvas = render.Canvas(height, width)
        module.render_frame(_make_ctx(f, width, height, **ctx_kw), canvas)
    return canvas


def test_frame_styles_exist():
    assert _load_frame_styles(), "no styles implement render_frame"


def test_active_signal_paints_scene():
    for stem, module in _load_frame_styles().items():
        canvas = _run_sequence(
            module, 12, amp=0.8, bass=0.7, mid=0.5, treble=0.6, beat=1.0
        )
        painted = _painted_cells(canvas)
        assert len(painted) > 10, f"{stem}: nearly blank canvas with hot signal"


def test_long_silence_still_paints_ambient_scene():
    for stem, module in _load_frame_styles().items():
        canvas = _run_sequence(module, 12, amp=0.0, silence_frames=600)
        assert _painted_cells(canvas), f"{stem}: dead screen during silence"


def test_deterministic_across_fresh_loads():
    def final_cells(stem_filter):
        cells = {}
        for stem, module in _load_frame_styles().items():
            if stem != stem_filter:
                continue
            canvas = _run_sequence(
                module, 10, amp=0.6, bass=0.5, mid=0.4, treble=0.3, beat=0.4
            )
            cells[stem] = canvas.cells
        return cells

    for stem in _load_frame_styles():
        assert final_cells(stem) == final_cells(stem), (
            f"{stem}: nondeterministic frame sequence"
        )


def test_degenerate_sizes_do_not_raise():
    for stem, module in _load_frame_styles().items():
        for width, height in [(1, 1), (2, 2), (5, 3), (10, 1), (1, 10)]:
            _run_sequence(
                module, 4, width=width, height=height,
                amp=0.9, bass=0.9, mid=0.9, treble=0.9, beat=1.0,
            )
            _run_sequence(module, 4, width=width, height=height,
                          silence_frames=999)


_TESTS = [
    test_frame_styles_exist,
    test_active_signal_paints_scene,
    test_long_silence_still_paints_ambient_scene,
    test_deterministic_across_fresh_loads,
    test_degenerate_sizes_do_not_raise,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} frame-style contract tests passed.")
