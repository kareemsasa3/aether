"""Rain Drops - rainfall onto a living water surface shaped by the music"""

import curses
import random

STYLE_NAME = "Rain Drops"
STYLE_DESCRIPTION = "Rain falling onto a rippling water surface with splashes"

# Persistent scene state, keyed by canvas size: falling drops [x, y, speed]
# and surface ripples [x, age]. last_frame guards double-advance.
_state = {"size": None, "drops": [], "ripples": [], "last_frame": None}


def _surface_y(ctx, x, base, swell):
    """Water line for a column: the waveform sculpts the surface."""
    amp, _ = ctx.columns[x]
    return base - int(amp * swell)


def _advance(ctx, w, h, base, swell):
    rng = random.Random(ctx.frame * 7717 + w)
    st = _state

    # Rainfall density follows the mids/highs; beats dump a burst of drops.
    # Drops take ~20 frames to fall, so keep spawn rates low or the sky
    # saturates.
    p = 0.005 + 0.045 * min(1.0, ctx.mid + ctx.treble)
    if ctx.beat > 0.6:
        p += 0.08
    for x in range(w):
        if rng.random() < p:
            st["drops"].append([x, 0.0, 0.5 + 0.5 * rng.random()])

    survivors = []
    for drop in st["drops"]:
        drop[1] += drop[2] + 0.3 * ctx.bass
        if drop[1] >= _surface_y(ctx, drop[0], base, swell):
            st["ripples"].append([drop[0], 0])
        else:
            survivors.append(drop)
    st["drops"] = survivors

    for r in st["ripples"]:
        r[1] += 1
    st["ripples"] = [r for r in st["ripples"] if r[1] < 6]


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    base = max(1, (h * 2) // 3)
    swell = (h // 5) * (1.0 + 0.5 * ctx.beat)

    if _state["size"] != (w, h):
        _state["size"] = (w, h)
        _state["drops"] = []
        _state["ripples"] = []
        _state["last_frame"] = None
    if _state["last_frame"] != ctx.frame:
        _advance(ctx, w, h, base, swell)
        _state["last_frame"] = ctx.frame

    colors = ctx.colors

    # Water: an undulating surface line with a shaded body below it.
    for x in range(w):
        sy = _surface_y(ctx, x, base, swell)
        amp, _ = ctx.columns[x]
        surf_attr = (
            colors[3] | curses.A_BOLD if abs(amp) > 0.4 else colors[3]
        )
        canvas.set(sy, x, "≈" if abs(amp) > 0.25 else "~", surf_attr)
        for depth in range(1, h - sy):
            y = sy + depth
            if depth <= 2:
                canvas.set(y, x, "░", colors[5])
            elif (x + y) % 3 == 0:
                canvas.set(y, x, "·", colors[5] | curses.A_DIM)

    # Falling drops: a streak with a bright head.
    for x, y, _ in _state["drops"]:
        yi = int(y)
        canvas.set(yi - 1, x, "│", colors[5])
        canvas.set(yi, x, "●" if ctx.beat > 0.6 else "•", colors[3] | curses.A_BOLD)

    # Splashes: ripples widen and fade where drops hit the surface.
    for x, age in _state["ripples"]:
        sy = _surface_y(ctx, x, base, swell)
        if age == 0:
            canvas.set(sy - 1, x, "○", colors[3] | curses.A_BOLD)
        else:
            fade = colors[3] if age < 3 else colors[5]
            canvas.set(sy - 1, x - age, "(", fade)
            canvas.set(sy - 1, x + age, ")", fade)
            if age < 3:
                canvas.set(sy - 2, x, "◦", fade)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 100:
        return None

    # Use a seeded random for stable character selection (prevents flicker).
    # The sample_id is constant for a specific audio sample as it radiates.
    rng = random.Random(sample_id)

    intensity = abs(amp)

    # Droplet characters
    drops = ["●", "○", "◦", "·", "∘"]
    falling = ["│", "|", "¦", ":", "!"]
    splash = ["○", "◦", "·", "∙", "˙", ",", "`", "'"]

    # Fresh = big drops, older = smaller/splash
    if age < 3:
        if intensity > 0.4:
            char = drops[0]  # Big drop
        else:
            char = drops[1]
    elif age < 8:
        if amp > 0:
            char = rng.choice(falling[:3])  # Falling
        else:
            char = rng.choice(drops[1:4])
    elif age < 15:
        char = rng.choice(splash[:4])  # Splash spreading
    else:
        char = rng.choice(splash[4:])  # Dissipating

    # Blue/cyan for water feel
    if age < 2:
        attr = colors[3] | curses.A_BOLD  # Cyan bright
    elif age < 6:
        attr = colors[5] | curses.A_BOLD  # Blue
    elif age < 10:
        attr = colors[3]  # Cyan
    elif age < 16:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    # Occasional ripple effect (seeded: some samples ripple, stably)
    if rng.random() < 0.03:
        char = rng.choice(["~", "≈", "∿"])
        attr = colors[5]

    return (char, attr)
