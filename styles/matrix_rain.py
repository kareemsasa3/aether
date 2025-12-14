"""Matrix Rain - Binary cascading effect with digital rain aesthetic"""

import curses
import random

STYLE_NAME = "Matrix Rain"
STYLE_DESCRIPTION = "Binary cascading 0s and 1s with digital rain effect"


def render_waveform(age, colors):
    """
    Render waveform with Matrix-style binary rain effect.

    Characters cascade down with a mix of solid blocks and binary digits,
    fading from bright green to dim as they age.
    """
    # Skip very old samples
    if age >= 60:  # Extended from 20 for longer persistence
        return None

    # Character selection: mix of blocks and binary for that Matrix feel
    # Newer samples have more blocks, older ones transition to binary
    if age < 9:
        char = random.choices(["█", "▓", "0", "1"], weights=[50, 20, 15, 15], k=1)[0]
    elif age < 24:
        char = random.choices(["▓", "▒", "0", "1"], weights=[30, 20, 25, 25], k=1)[0]
    else:
        char = random.choices(["0", "1", "░", " "], weights=[35, 35, 20, 10], k=1)[0]

    # Age-based intensity for that phosphor decay look (extended age ranges)
    if age < 9:
        attr = colors[1] | curses.A_BOLD
    elif age < 21:
        attr = colors[1]
    elif age < 36:
        attr = colors[2]
    elif age < 51:
        attr = colors[2] | curses.A_DIM
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
