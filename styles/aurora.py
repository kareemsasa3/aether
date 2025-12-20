"""Aurora - Northern lights inspired flowing curtains"""

import curses
import random
import math

STYLE_NAME = "Aurora"
STYLE_DESCRIPTION = "Northern lights with flowing color curtains"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with aurora borealis effect.

    Creates flowing, curtain-like patterns with color
    shifts reminiscent of the northern lights.
    """
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
