"""Pixel Art - Retro half-block pixel aesthetic"""

import curses
import random

STYLE_NAME = "Pixel Art"
STYLE_DESCRIPTION = "Retro pixel art with half-block characters"


def render_waveform(i, amp, age, colors):
    """
    Render waveform with retro pixel art effect.

    Uses half-block characters to create a chunky, retro
    8-bit aesthetic reminiscent of classic arcade games.
    """
    if age >= 100:
        return None

    # Half-block characters for that pixel art look
    if amp > 0.3:
        chars = ["▀", "▘", "▝", "▖", "▗"]
    elif amp < -0.3:
        chars = ["▄", "▖", "▗", "▘", "▝"]
    else:
        chars = ["▌", "▐", "▕", "▏"]

    # Add some variation based on position
    if i % 2 == 0:
        char = random.choice(chars[:3])
    else:
        char = random.choice(chars)

    # Retro color transition: bright to dim
    if age < 4:
        attr = colors[1] | curses.A_BOLD
    elif age < 10:
        attr = colors[1]
    elif age < 16:
        # Add some "scanline" dimming effect
        if i % 3 == 0:
            attr = colors[2] | curses.A_DIM
        else:
            attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
