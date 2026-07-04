"""Minimalist - high-resolution braille curve, nothing else"""

import curses
import math

STYLE_NAME = "Minimalist"
STYLE_DESCRIPTION = "Ultra-clean high-resolution braille curve with peak marks"

# Braille cell = 2x4 sub-pixels; standard Unicode dot bit layout.
_BIT = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}

# Falling peak-hold markers, in sub-pixel units per cell column.
_state = {"width": None, "peaks": [], "last_frame": None}


def _plot(cells, sx, sy):
    cells[(sy // 4, sx // 2)] = cells.get((sy // 4, sx // 2), 0) | _BIT[
        (sx % 2, sy % 4)
    ]


def render_frame(ctx, canvas):
    """One continuous sub-pixel curve; quiet passages breathe gently."""
    h, w = ctx.height, ctx.width
    sub_h, sub_w = h * 4, w * 2
    center = sub_h // 2
    scale = max(1, center - 2)

    st = _state
    if st["width"] != w:
        st["width"] = w
        st["peaks"] = [0.0] * max(1, w)
    advance = st["last_frame"] != ctx.frame
    st["last_frame"] = ctx.frame

    quiet = ctx.silence_frames > 45
    breath = 1.0 + 0.5 * math.sin(ctx.frame * 0.015)

    wave_cells = {}
    peak_cells = {}
    prev_sy = None
    for sx in range(sub_w):
        x = min(w - 1, sx // 2)
        if quiet:
            sy = center + round(2 * math.sin(sx * 0.05 + ctx.frame * 0.05) * breath)
        else:
            amp = ctx.columns[x][0]
            if sx % 2 and x + 1 < w:
                amp = (amp + ctx.columns[x + 1][0]) / 2
            sy = center - int(max(-1.0, min(1.0, amp)) * scale)
        sy = max(0, min(sub_h - 1, sy))
        _plot(wave_cells, sx, sy)
        # Fill the vertical gap to the previous sample: a continuous curve,
        # not a scatter of dots.
        if prev_sy is not None and abs(sy - prev_sy) > 1:
            lo, hi = sorted((sy, prev_sy))
            for yy in range(lo + 1, hi):
                _plot(wave_cells, sx, yy)
        prev_sy = sy

        # Peak hold per cell column (even sub-columns only).
        if sx % 2 == 0 and not quiet:
            dev = abs(sy - center)
            if dev > st["peaks"][x]:
                st["peaks"][x] = float(dev)

    if advance:
        st["peaks"] = [max(0.0, p - 1.2) for p in st["peaks"]]

    if not quiet:
        for x, peak in enumerate(st["peaks"]):
            p = int(peak)
            if p > 3:
                _plot(peak_cells, x * 2, max(0, center - p - 2))
                _plot(peak_cells, x * 2, min(sub_h - 1, center + p + 2))

    wave_attr = ctx.colors[3] | (curses.A_BOLD if ctx.beat > 0.6 else 0)
    for (cy, cx), bits in peak_cells.items():
        if (cy, cx) not in wave_cells:
            canvas.set(cy, cx, chr(0x2800 + bits), ctx.colors[8])
    for (cy, cx), bits in wave_cells.items():
        bits |= peak_cells.get((cy, cx), 0)
        canvas.set(cy, cx, chr(0x2800 + bits), wave_attr)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 60:  # Extended from 20 for longer persistence
        return None

    intensity = abs(amp)

    # Simple, clean character selection
    if intensity > 0.6:
        char = "●"  # Solid dot for peaks
    elif intensity > 0.4:
        char = "○"  # Open circle
    elif intensity > 0.2:
        char = "·"  # Small dot
    else:
        char = "─"  # Dash for low values

    # Clean fade with no fancy effects (extended age ranges)
    if age < 15:
        attr = colors[1] | curses.A_BOLD
    elif age < 30:
        attr = colors[1]
    elif age < 45:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
