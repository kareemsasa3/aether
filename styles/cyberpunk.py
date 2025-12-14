"""Cyberpunk - Neon symbols and tech aesthetic"""

import curses
import random

STYLE_NAME = "Cyberpunk"
STYLE_DESCRIPTION = "Neon tech symbols with street aesthetic"


def render_waveform(amp, age, colors):
    """
    Render waveform with cyberpunk effect.

    Uses a mix of tech symbols, currency signs, and
    punctuation for a gritty cyber aesthetic.
    """
    if age >= 65:  # Extended from 22 for longer persistence
        return None

    # Cyberpunk symbol groups
    tech_symbols = ["¥", "€", "₿", "£", "$"]
    code_symbols = ["@", "#", "%", "&", "*", "^"]
    glyphs = ["◊", "◈", "⌘", "⌥", "⎔", "⏣"]
    lines = ["═", "║", "╔", "╗", "╚", "╝"]

    intensity = abs(amp)

    # Symbol selection creates the cyberpunk texture
    if age < 9 and intensity > 0.5:
        char = random.choice(tech_symbols + glyphs)
    elif age < 24:
        char = random.choice(code_symbols + glyphs)
    elif age < 45:
        char = random.choice(code_symbols + lines)
    else:
        char = random.choice(lines + ["·", ":", "."])

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

    # Random neon flicker
    if random.random() < 0.08:
        attr = colors[random.choice([3, 4, 5])] | curses.A_BOLD

    return (char, attr)
