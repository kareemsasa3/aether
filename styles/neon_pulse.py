"""Neon Pulse - Bright pulsating blocks with electric glow effect"""

import curses

STYLE_NAME = "Neon Pulse"
STYLE_DESCRIPTION = "Electric pulsating blocks with intense glow"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with neon glow effect.

    Uses amplitude to modulate intensity, creating a pulsing,
    electric feel with bright center and glowing edges.
    """
    if age >= 55:  # Extended from 18 for longer persistence
        return None

    # Character based on amplitude intensity
    intensity = abs(amp)

    if intensity > 0.7:
        char = "█"
    elif intensity > 0.5:
        char = "▓"
    elif intensity > 0.3:
        char = "▒"
    else:
        char = "░"

    # Age and amplitude combine for brightness (extended age ranges)
    if age < 6 and intensity > 0.5:
        attr = colors[1] | curses.A_BOLD | curses.A_REVERSE
    elif age < 12:
        attr = colors[1] | curses.A_BOLD
    elif age < 24:
        attr = colors[1]
    elif age < 36:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
