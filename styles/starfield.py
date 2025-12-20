"""Starfield - Twinkling stars and cosmic dots"""

import curses
import random

STYLE_NAME = "Starfield"
STYLE_DESCRIPTION = "Twinkling stars and cosmic sparkles"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with starfield effect.

    Uses star characters of varying brightness to create
    a twinkling, cosmic aesthetic.
    """
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
