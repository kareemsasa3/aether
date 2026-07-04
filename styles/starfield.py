"""Starfield - parallax starfield that warps outward on the bass"""

import curses
import math
import random

STYLE_NAME = "Starfield"
STYLE_DESCRIPTION = "Parallax stars: treble twinkles, bass jumps to warp speed"

# Per-layer drift speed (cells/frame at rest) and resting glyph, near to far.
_LAYERS = [
    (0.05, "·"),
    (0.12, "∙"),
    (0.28, "✦"),
]

# Persistent stars [x_float, y, layer, twinkle_phase], keyed by canvas size.
_state = {"size": None, "stars": [], "last_frame": None}


def _reset(w, h):
    rng = random.Random(w * 31 + h * 7)
    count = max(8, (w * h) // 22)
    _state["size"] = (w, h)
    _state["stars"] = [
        [
            rng.uniform(0, w),
            rng.randrange(max(1, h)),
            rng.randrange(len(_LAYERS)),
            rng.uniform(0, math.tau),
        ]
        for _ in range(count)
    ]
    _state["last_frame"] = None


def _advance(ctx, w, h):
    """Drift stars outward from the center; respawn the ones that escape."""
    rng = random.Random(ctx.frame * 6151 + w)
    warp = 0.4 + 2.0 * ctx.bass + 3.0 * ctx.beat
    cx = w / 2
    for star in _state["stars"]:
        speed = _LAYERS[star[2]][0] * warp
        direction = 1.0 if star[0] >= cx else -1.0
        star[0] += direction * max(speed, 0.02)
        if star[0] < 0 or star[0] >= w:
            # Respawn near the center on a fresh row, like flying forward.
            star[0] = cx + rng.uniform(-w / 8, w / 8)
            star[1] = rng.randrange(max(1, h))
            star[3] = rng.uniform(0, math.tau)


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    if _state["size"] != (w, h):
        _reset(w, h)
    if _state["last_frame"] != ctx.frame:
        _advance(ctx, w, h)
        _state["last_frame"] = ctx.frame

    colors = ctx.colors
    warp = 0.4 + 2.0 * ctx.bass + 3.0 * ctx.beat
    twinkle_rate = 0.06 + 0.35 * ctx.treble

    # Beat shockwave: a dim magenta glow expanding from the center row.
    if ctx.beat > 0.25:
        cx, cy = w // 2, h // 2
        half = int(ctx.beat * w / 6)
        for x in range(max(0, cx - half), min(w, cx + half + 1)):
            canvas.set(cy, x, "░", colors[10])

    for x, y, layer, phase in _state["stars"]:
        xi = int(x)
        tw = math.sin(phase + ctx.frame * twinkle_rate)
        speed = _LAYERS[layer][0] * warp
        if speed > 0.75:
            # Warp: near stars stretch into streaks pointing outward.
            streak = min(4, int(speed * 3))
            direction = 1 if x >= w / 2 else -1
            for k in range(streak):
                canvas.set(y, xi - direction * k, "─", colors[3])
            canvas.set(y, xi, "━", colors[3] | curses.A_BOLD)
        elif layer == 2:
            attr = colors[6] | curses.A_BOLD if tw > 0.55 else colors[3]
            canvas.set(y, xi, "✦" if tw > 0.55 else "✧", attr)
        elif layer == 1:
            attr = colors[3] if tw > 0.6 else colors[8]
            canvas.set(y, xi, "∙", attr)
        else:
            canvas.set(y, xi, "·", colors[8] | (0 if tw < 0.7 else curses.A_BOLD))


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 80:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    intensity = abs(amp)

    # Star characters from bright to dim
    bright_stars = ["★", "✦", "✧", "⋆", "*"]
    medium_stars = ["✧", "⋆", "*", "·", "∙"]
    dim_stars = ["·", "∙", "⋅", ".", "˙"]

    # Select stars based on intensity and age
    if intensity > 0.5 and age < 15:
        char = rng.choice(bright_stars)
    elif intensity > 0.3 or age < 30:
        char = rng.choice(medium_stars)
    else:
        char = rng.choice(dim_stars)

    # Twinkling effect - random brightness variations (now stable per sample)
    twinkle = rng.random()

    if age < 9 and twinkle > 0.7:
        # Bright twinkle
        attr = colors[1] | curses.A_BOLD | curses.A_STANDOUT
    elif age < 18:
        attr = colors[1] | curses.A_BOLD
    elif age < 36:
        # Occasional cyan twinkle
        if twinkle > 0.9:
            attr = colors[3] | curses.A_BOLD
        else:
            attr = colors[1]
    elif age < 54:
        attr = colors[2]
    elif age < 72:
        attr = colors[2] | curses.A_DIM
    else:
        char = "."
        attr = colors[2] | curses.A_DIM

    return (char, attr)
