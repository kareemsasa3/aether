"""Aurora - full-height northern-lights curtains that dance to the music"""

import curses
import math
import random

STYLE_NAME = "Aurora"
STYLE_DESCRIPTION = "Flowing full-height light curtains with drifting colors"


def _curtain_height(x, frame, energy, h):
    """Layered sines give each column a slowly drifting curtain length."""
    n = (
        0.5
        + 0.25 * math.sin(x * 0.09 + frame * 0.03)
        + 0.25 * math.sin(x * 0.023 - frame * 0.011)
    )
    return int(n * energy * (h - 1))


def render_frame(ctx, canvas):
    """Curtains hang from the sky; bass makes them billow, treble sparkles.

    Stateless by design: everything is a function of (x, frame) plus the
    band levels, so the drift stays smooth and deterministic.
    """
    h, w = ctx.height, ctx.width
    colors = ctx.colors

    # Energy floor keeps a gentle aurora drifting during silence.
    energy = min(1.0, 0.35 + 0.45 * ctx.mid + 0.35 * ctx.bass + 0.3 * ctx.beat)
    surge = ctx.beat > 0.7
    rng = random.Random(ctx.frame // 3 * 51349 + w)

    for x in range(w):
        hgt = _curtain_height(x, ctx.frame, energy, h)
        if hgt <= 0:
            continue

        # Color bands drift sideways over time.
        hue = math.sin(x * 0.05 + ctx.frame * 0.02)
        if hue > 0.3:
            base = colors[1]  # Green
        elif hue > -0.4:
            base = colors[3]  # Cyan
        else:
            base = colors[4]  # Magenta

        for y in range(hgt + 1):
            depth = y / max(1, hgt)
            if depth < 0.55:
                char, attr = "░", base
            elif depth < 0.85:
                char, attr = "▒", base
            else:
                # The luminous lower edge of the curtain.
                char = "▓"
                attr = base | curses.A_BOLD
            if surge:
                attr |= curses.A_BOLD
            canvas.set(y, x, char, attr)

        # Treble scatters sparkles just below the curtain's glowing hem.
        if ctx.treble > 0.35 and rng.random() < 0.04 + 0.08 * ctx.treble:
            canvas.set(hgt + 1 + rng.randrange(2), x, "✧", colors[6] | curses.A_BOLD)

    # Faint ground reflection along the bottom row.
    for x in range(0, w, 2):
        if _curtain_height(x, ctx.frame, energy, h) > h // 2:
            canvas.set(h - 1, x, "·", colors[2])


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 80:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    # Aurora characters - flowing, wave-like
    curtains = ["░", "▒", "▓", "█", "│", "║"]
    wisps = ["~", "≈", "∿", "∽", "⌇", "⌁"]
    particles = ["·", "∙", "°", "˚", "*", "✧"]

    intensity = abs(amp)

    # Layer selection based on intensity and age
    if age < 9:
        if intensity > 0.5:
            char = rng.choice(curtains[3:5])
        else:
            char = rng.choice(curtains[1:4])
    elif age < 30:
        char = rng.choice(curtains[:3] + wisps[:2])
    elif age < 50:
        char = rng.choice(wisps + particles[:3])
    else:
        char = rng.choice(particles)

    # Aurora color dancing - cycle through colors based on position
    wave = math.sin(i * 0.15 + age * 0.1)

    if age < 12:
        # Fresh aurora - bright greens and cyans
        if wave > 0.3:
            attr = colors[3] | curses.A_BOLD  # Cyan
        else:
            attr = colors[1] | curses.A_BOLD  # Green
    elif age < 24:
        # Middle layer - mix colors
        if wave > 0.5:
            attr = colors[3]
        elif wave > 0:
            attr = colors[1]
        else:
            attr = colors[4]  # Magenta accents
    elif age < 45:
        # Outer layer
        if wave > 0.3:
            attr = colors[1]
        else:
            attr = colors[5]  # Blue
    elif age < 65:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    # Occasional bright sparkle - now stable per sample
    if rng.random() < 0.02:
        char = "✧"
        attr = colors[rng.choice([1, 3, 4])] | curses.A_BOLD

    return (char, attr)
