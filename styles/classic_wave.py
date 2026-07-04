"""Classic Wave - a real oscilloscope: connected trace, phosphor, graticule"""

import curses

STYLE_NAME = "Classic Wave"
STYLE_DESCRIPTION = "CRT oscilloscope: continuous trace with phosphor decay"

# Phosphor persistence grid of per-cell intensities (1.0 = just traced),
# keyed by canvas size. Fades every frame, leaving the classic green ghost.
_state = {"size": None, "phosphor": [], "last_frame": None}


def _reset(w, h):
    _state["size"] = (w, h)
    _state["phosphor"] = [[0.0] * w for _ in range(max(1, h))]
    _state["last_frame"] = None


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    if _state["size"] != (w, h):
        _reset(w, h)
    phosphor = _state["phosphor"]
    advance = _state["last_frame"] != ctx.frame
    _state["last_frame"] = ctx.frame

    colors = ctx.colors
    center = h // 2
    scale = max(1, center - 1)

    # Graticule: the measurement grid under everything.
    for y in range(0, h, 4):
        for x in range(0, w, 10):
            canvas.set(y, x, "·", colors[8] | curses.A_DIM)
    for x in range(0, w, 2):
        canvas.set(center, x, "╌", colors[8] | curses.A_DIM)

    if advance:
        for row in phosphor:
            for x in range(w):
                row[x] *= 0.78

    # Trace: connect consecutive samples with vertical segments so the
    # beam draws a continuous line, like a real scope.
    idle = ctx.silence_frames > 45
    prev_y = None
    for x in range(w):
        amp, _ = ctx.columns[x]
        y = center - int(max(-1.0, min(1.0, amp)) * scale)
        y = max(0, min(h - 1, y))
        if 0 <= y < len(phosphor):
            phosphor[y][x] = 1.0
        if prev_y is not None and abs(y - prev_y) > 1:
            lo, hi = sorted((y, prev_y))
            for yy in range(lo + 1, hi):
                if 0 <= yy < len(phosphor):
                    phosphor[yy][x] = 0.9
        prev_y = y

    # Idle sweep: with no signal, a bright spot patrols the flat trace so
    # the scope still feels powered on.
    if idle:
        sweep_x = (ctx.frame * 2) % max(1, w)
        phosphor[center][sweep_x] = 1.0

    # Render phosphor: brightness maps to the CRT decay ramp.
    for y in range(min(h, len(phosphor))):
        row = phosphor[y]
        for x in range(w):
            v = row[x]
            if v > 0.95:
                canvas.set(y, x, "●", colors[1] | curses.A_BOLD)
            elif v > 0.7:
                canvas.set(y, x, "█", colors[1] | curses.A_BOLD)
            elif v > 0.45:
                canvas.set(y, x, "▓", colors[1])
            elif v > 0.25:
                canvas.set(y, x, "▒", colors[2])
            elif v > 0.12:
                canvas.set(y, x, "░", colors[2] | curses.A_DIM)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 60:  # Extended from 20 for longer persistence
        return None

    # Classic oscilloscope uses underscore and overline for waves
    # Plus some curve characters for smoother look

    if amp > 0.4:
        char = "‾"  # Overline for peaks
    elif amp > 0.1:
        char = "˜"  # Tilde for medium high
    elif amp < -0.4:
        char = "_"  # Underscore for troughs
    elif amp < -0.1:
        char = "˜"  # Tilde for medium low
    else:
        char = "─"  # Dash for center crossing

    # Classic CRT phosphor glow effect (extended age ranges)
    if age < 6:
        attr = colors[1] | curses.A_BOLD | curses.A_STANDOUT
    elif age < 15:
        attr = colors[1] | curses.A_BOLD
    elif age < 30:
        attr = colors[1]
    elif age < 45:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
