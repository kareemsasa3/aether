"""Heartbeat - ECG/Medical monitor style"""

import curses
import random

STYLE_NAME = "Heartbeat"
STYLE_DESCRIPTION = "ECG medical monitor with cardiac rhythm"


def render_waveform(amp, age, colors):
    """
    Render waveform with ECG/heartbeat effect.

    Creates the distinctive peaks and valleys of an
    electrocardiogram display.
    """
    if age >= 100:
        return None

    intensity = abs(amp)

    # ECG-style characters
    # Sharp peaks and valleys for that cardiac look
    if amp > 0.6:
        char = "╱"  # Sharp rise (QRS complex)
    elif amp > 0.3:
        char = "/"
    elif amp > 0.05:
        char = "─"  # Baseline
    elif amp > -0.05:
        char = "─"
    elif amp > -0.3:
        char = "\\"
    elif amp > -0.6:
        char = "╲"  # Sharp fall
    else:
        char = "│"  # Deep valley (S wave)

    # Add ECG-specific peaks randomly for realism
    if intensity > 0.7:
        char = random.choice(["▲", "△", "∧", "╱"])
    elif intensity > 0.5 and amp < 0:
        char = random.choice(["▼", "▽", "∨", "╲"])

    # Medical monitor green with red for critical peaks
    if age < 3 and intensity > 0.6:
        # Critical peak - could flash red
        attr = colors[4] | curses.A_BOLD  # Magenta for alert
    elif age < 4:
        attr = colors[1] | curses.A_BOLD
    elif age < 8:
        attr = colors[1]
    elif age < 14:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
