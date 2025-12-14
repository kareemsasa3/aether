"""Classic Wave - Traditional oscilloscope sine curves"""

import curses

STYLE_NAME = "Classic Wave"
STYLE_DESCRIPTION = "Traditional oscilloscope with clean sine waves"


def render_waveform(i, amp, age, max_width, colors):
    """
    Render waveform with classic oscilloscope effect.

    Uses curve characters to draw smooth, continuous
    waveforms like a real analog oscilloscope.
    """
    if age >= 60:  # Extended from 20 for longer persistence
        return None

    # Classic oscilloscope uses underscore and overline for waves
    # Plus some curve characters for smoother look

    if amp > 0.4:
        char = "‾"  # Overline for peaks
    elif amp > 0.1:
        char = "˜"  # Tilde for medium high
    elif amp < -0.4:
        char = "_"  # Underscore for troughs
    elif amp < -0.1:
        char = "˜"  # Tilde for medium low
    else:
        char = "─"  # Dash for center crossing

    # Classic CRT phosphor glow effect (extended age ranges)
    if age < 6:
        attr = colors[1] | curses.A_BOLD | curses.A_STANDOUT
    elif age < 15:
        attr = colors[1] | curses.A_BOLD
    elif age < 30:
        attr = colors[1]
    elif age < 45:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
