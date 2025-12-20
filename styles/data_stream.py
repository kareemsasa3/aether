"""Data Stream - Flowing directional arrows like data packets"""

import curses
import random

STYLE_NAME = "Data Stream"
STYLE_DESCRIPTION = "Flowing arrows and data symbols streaming across"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with flowing data stream effect.

    Uses directional arrows based on amplitude direction,
    creating a sense of data flowing through the display.
    """
    if age >= 65:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    # Direction arrows based on amplitude sign
    if amp > 0.1:
        # Upward flowing data
        chars = ["↑", "↟", "⇡", "△", "▲", "⬆"]
    elif amp < -0.1:
        # Downward flowing data
        chars = ["↓", "↡", "⇣", "▽", "▼", "⬇"]
    else:
        # Horizontal flow at center
        chars = ["→", "←", "⟶", "⟵", "─", "═"]

    # Newer samples get bolder arrows
    if age < 9:
        char = rng.choice(chars[:2])  # Bold arrows
    elif age < 24:
        char = rng.choice(chars[2:4])  # Medium arrows
    else:
        char = rng.choice(chars[4:])  # Light arrows

    # Speed effect: flicker between arrow states (now stable per sample)
    if age < 15 and rng.random() < 0.3:
        char = rng.choice(["»", "«", "›", "‹"])

    # Age-based coloring with cyan for data feel
    if age < 12:
        attr = colors[3] | curses.A_BOLD  # Cyan bold
    elif age < 30:
        attr = colors[1]  # Green
    elif age < 48:
        attr = colors[2]  # Dim green
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
