"""Geometric - Triangles and shapes creating patterns"""

import curses
import random

STYLE_NAME = "Geometric"
STYLE_DESCRIPTION = "Triangles and geometric shapes in patterns"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with geometric shapes.

    Uses triangles, diamonds, and circles to create
    visually striking geometric patterns.
    """
    if age >= 100:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    # Shape selection based on amplitude direction and position
    if amp > 0.2:
        # Point up for positive amplitude
        shapes = ["△", "▲", "▴", "◇", "◆", "○"]
    elif amp < -0.2:
        # Point down for negative amplitude
        shapes = ["▽", "▼", "▿", "◇", "◆", "○"]
    else:
        # Neutral shapes
        shapes = ["○", "●", "◇", "◆", "□", "■"]

    # Create pattern based on position
    pattern_pos = i % 4
    if pattern_pos == 0:
        char = shapes[0]  # Triangles
    elif pattern_pos == 1:
        char = shapes[3]  # Diamonds
    elif pattern_pos == 2:
        char = shapes[4 if age < 8 else 5]
    else:
        char = rng.choice(shapes[1:3])

    # Age-based color with geometric precision
    if age < 3:
        attr = colors[3] | curses.A_BOLD  # Cyan for freshness
    elif age < 7:
        attr = colors[1] | curses.A_BOLD
    elif age < 12:
        attr = colors[1]
    elif age < 17:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
