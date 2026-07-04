"""Matrix Rain - real cascading digital rain driven by the music"""

import curses
import random

STYLE_NAME = "Matrix Rain"
STYLE_DESCRIPTION = "Cascading digital rain: energy spawns drops, bass speeds them"

# Mostly binary with occasional halfwidth katakana/symbols for texture.
_GLYPHS = "010101010101ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜ<>*+=:"

# Persistent scene state, keyed by canvas size. The glyph grid is fixed per
# size (real matrix rain reveals a stable character field); drops are
# [x, head_y, speed, length]. last_frame guards double-advance when a frame
# is drawn twice (e.g. right after an overlay closes).
_state = {"size": None, "grid": [], "drops": [], "last_frame": None}


def _reset(w, h):
    rng = random.Random(w * 7919 + h)
    _state["size"] = (w, h)
    _state["grid"] = [
        [rng.choice(_GLYPHS) for _ in range(w)] for _ in range(max(1, h))
    ]
    _state["drops"] = []
    _state["last_frame"] = None


def _advance(ctx, w, h):
    """Spawn and move drops for this frame (called once per ctx.frame)."""
    rng = random.Random(ctx.frame * 9973 + w)
    energy = min(1.0, ctx.amp + ctx.mid * 0.5 + ctx.treble * 0.5)

    # Spawn probability per column: quiet drizzle floor, scaling with the
    # music, with a burst on every beat. Tails live for tens of frames, so
    # these stay small or the field saturates into a solid wall of glyphs.
    p = 0.008 + 0.03 * energy + 0.10 * (ctx.beat if ctx.beat > 0.6 else 0.0)
    speed = 0.35 + 0.45 * ctx.bass + 0.4 * ctx.beat
    for x in range(w):
        if rng.random() < p:
            length = rng.randint(max(2, h // 4), max(3, (2 * h) // 3))
            _state["drops"].append([x, 0.0, speed * rng.uniform(0.7, 1.3), length])

    for drop in _state["drops"]:
        drop[1] += drop[2]
    _state["drops"] = [d for d in _state["drops"] if d[1] - d[3] < h]

    # Shimmer: a few grid cells mutate each frame so long tails stay alive.
    for _ in range(1 + w // 20):
        gx, gy = rng.randrange(w), rng.randrange(max(1, h))
        _state["grid"][gy][gx] = rng.choice(_GLYPHS)


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    if _state["size"] != (w, h):
        _reset(w, h)
    if _state["last_frame"] != ctx.frame:
        _advance(ctx, w, h)
        _state["last_frame"] = ctx.frame

    colors = ctx.colors
    grid = _state["grid"]

    # Faint waveform ghost behind the rain ties the scene to the music.
    center = h // 2
    scale = max(1, center - 1)
    for x in range(w):
        amp, age = ctx.columns[x]
        if abs(amp) > 0.05 and age < 40:
            y = center - int(amp * scale)
            canvas.set(y, x, "·", colors[2])

    hot = ctx.beat > 0.6
    for x, head_y, _, length in _state["drops"]:
        head = int(head_y)
        for k in range(length):
            y = head - k
            if not (0 <= y < h):
                continue
            if k == 0:
                # Bright head; beats flash the whole leading edge.
                attr = colors[1] | curses.A_BOLD
                if hot:
                    attr |= curses.A_STANDOUT
            elif k < length // 3:
                attr = colors[1] | curses.A_BOLD
            elif k < (2 * length) // 3:
                attr = colors[1]
            elif k < length - 2:
                attr = colors[2]
            else:
                attr = colors[2] | curses.A_DIM
            canvas.set(y, x, grid[y % len(grid)][x], attr)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    # Skip very old samples
    if age >= 60:
        return None

    # Use a seeded random for stable character selection (prevents flicker)
    # The sample_id is constant for a specific audio sample as it radiates.
    rng = random.Random(sample_id)

    # Character selection: mix of blocks and binary for that Matrix feel
    if age < 9:
        char = rng.choices(["█", "▓", "0", "1"], weights=[50, 20, 15, 15], k=1)[0]
    elif age < 24:
        char = rng.choices(["▓", "▒", "0", "1"], weights=[30, 20, 25, 25], k=1)[0]
    else:
        char = rng.choices(["0", "1", "░", " "], weights=[35, 35, 20, 10], k=1)[0]

    # Age-based intensity for that phosphor decay look
    if age < 9:
        attr = colors[1] | curses.A_BOLD
    elif age < 21:
        attr = colors[1]
    elif age < 36:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
