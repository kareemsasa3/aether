"""Minimalist - Clean dots and dashes aesthetic"""

import curses

STYLE_NAME = "Minimalist"
STYLE_DESCRIPTION = "Clean, elegant dots and dashes only"


def render_waveform(amp, age, colors):
    """
    Render waveform with minimalist effect.

    Uses only dots and dashes for a clean, elegant look
    that focuses on the waveform shape itself.
    """
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
