"""Cyberpunk - neon signal over a living city skyline with glitch bursts"""

import curses
import random

STYLE_NAME = "Cyberpunk"
STYLE_DESCRIPTION = "Neon signal over a city skyline with glitches and data rain"

_GLITCH_GLYPHS = "▚▞░#$%&<>/\\|=+*"
_PARTICLE_GLYPHS = "$@#¥€₿"

# Persistent scene: skyline heights (fixed per size), rising data particles
# [x, y_float, char], and active glitch scanlines [row, ttl]. last_frame
# guards double-advance.
_state = {
    "size": None,
    "skyline": [],
    "particles": [],
    "glitches": [],
    "last_frame": None,
}


def _reset(w, h):
    rng = random.Random(w * 131 + h * 17)
    heights, x = [], 0
    while x < w:
        bw = rng.randint(3, 9)
        bh = rng.randint(max(1, h // 6), max(2, (2 * h) // 5))
        heights.extend([bh] * bw)
        x += bw
    _state["size"] = (w, h)
    _state["skyline"] = heights[:w]
    _state["particles"] = []
    _state["glitches"] = []
    _state["last_frame"] = None


def _advance(ctx, w, h):
    rng = random.Random(ctx.frame * 4241 + w)
    st = _state

    # Data particles rise from the streets when the music runs hot.
    energy = min(1.0, ctx.amp + ctx.mid * 0.5)
    if rng.random() < 0.10 + 0.45 * energy:
        x = rng.randrange(w)
        st["particles"].append([x, float(h - 1), rng.choice(_PARTICLE_GLYPHS)])
    for p in st["particles"]:
        p[1] -= 0.4 + 0.4 * ctx.treble
    st["particles"] = [p for p in st["particles"] if p[1] > 0]

    # Beats and treble spikes tear glitch scanlines across the frame.
    if ctx.beat > 0.6 or (ctx.treble > 0.7 and rng.random() < 0.3):
        for _ in range(rng.randint(1, 2)):
            st["glitches"].append([rng.randrange(max(1, h)), 3])
    for g in st["glitches"]:
        g[1] -= 1
    st["glitches"] = [g for g in st["glitches"] if g[1] > 0]


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    if _state["size"] != (w, h):
        _reset(w, h)
    if _state["last_frame"] != ctx.frame:
        _advance(ctx, w, h)
        _state["last_frame"] = ctx.frame

    colors = ctx.colors

    # Skyline: dim building mass with windows that light up with the mids.
    for x, bh in enumerate(_state["skyline"]):
        top = h - bh
        canvas.set(top, x, "▄", colors[10])
        for y in range(top + 1, h):
            lit = (x * 13 + y * 7) % 11 < 1 + int(ctx.mid * 5)
            if lit:
                canvas.set(y, x, "▪", colors[6])
            else:
                canvas.set(y, x, "░", colors[8] | curses.A_DIM)

    # Rising data particles.
    for x, y, char in _state["particles"]:
        canvas.set(int(y), x, char, colors[3])

    # The signal: a hot-pink neon trace riding above the city.
    base = (2 * h) // 5
    scale = max(1, h // 3)
    for x in range(w):
        amp, age = ctx.columns[x]
        y = base - int(amp * scale)
        if abs(amp) > 0.55:
            canvas.set(y, x, "▓", colors[3] | curses.A_BOLD)
        elif age > 50:
            canvas.set(y, x, "═", colors[10])
        else:
            canvas.set(y, x, "═", colors[4] | curses.A_BOLD)

    # Glitch scanlines rip across everything on hits.
    for row, ttl in _state["glitches"]:
        rng = random.Random(row * 977 + ctx.frame // 2)
        for x in range(0, w, 1):
            if rng.random() < 0.35:
                attr = (colors[4] if ttl % 2 else colors[3]) | curses.A_BOLD
                canvas.set(row, x, rng.choice(_GLITCH_GLYPHS), attr)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 65:  # Extended from 22 for longer persistence
        return None

    # Use a seeded random for stable character selection (prevents flicker).
    # The sample_id is constant for a specific audio sample as it radiates.
    rng = random.Random(sample_id)

    # Cyberpunk symbol groups
    tech_symbols = ["¥", "€", "₿", "£", "$"]
    code_symbols = ["@", "#", "%", "&", "*", "^"]
    glyphs = ["◊", "◈", "⌘", "⌥", "⎔", "⏣"]
    lines = ["═", "║", "╔", "╗", "╚", "╝"]

    intensity = abs(amp)

    # Symbol selection creates the cyberpunk texture
    if age < 9 and intensity > 0.5:
        char = rng.choice(tech_symbols + glyphs)
    elif age < 24:
        char = rng.choice(code_symbols + glyphs)
    elif age < 45:
        char = rng.choice(code_symbols + lines)
    else:
        char = rng.choice(lines + ["·", ":", "."])

    if age < 9:
        # Hot pink for fresh signals
        attr = colors[4] | curses.A_BOLD
    elif age < 18:
        # Cyan glow
        attr = colors[3] | curses.A_BOLD
    elif age < 30:
        # Green matrix
        attr = colors[1] | curses.A_BOLD
    elif age < 45:
        attr = colors[1]
    else:
        attr = colors[2] | curses.A_DIM

    # Random neon flicker (seeded: some samples glow, stably, as they radiate)
    if rng.random() < 0.08:
        attr = colors[rng.choice([3, 4, 5])] | curses.A_BOLD

    return (char, attr)
