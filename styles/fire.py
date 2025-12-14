"""Fire - Flame-like rising effect with warmth"""

import curses
import random

STYLE_NAME = "Fire"
STYLE_DESCRIPTION = "Rising flames with warm color transitions"


def render_waveform(amp, age, colors):
    """
    Render waveform with fire/flame effect.

    Creates rising flame-like patterns with characters
    that suggest heat and movement upward.
    """
    if age >= 60:  # Extended from 20 for longer persistence
        return None

    # Flame characters - from dense to sparse
    hot_flames = ["█", "▓", "░", "▒"]
    med_flames = ["ᚈ", "₪", "※", "⁂", "⁕"]
    dim_flames = ["∵", "·", "°", "˚", "'", "`"]

    # Fire rises - so positive amplitude gets hot chars (extended age ranges)
    if amp > 0.3:
        if age < 12:
            char = random.choice(hot_flames[:2])
        elif age < 30:
            char = random.choice(hot_flames)
        else:
            char = random.choice(med_flames)
    elif amp > -0.1:
        # Middle flames
        char = random.choice(med_flames)
    else:
        # Base embers
        char = random.choice(dim_flames)

    # Fire color: magenta/red -> yellow-ish -> dim (extended age ranges)
    # Using available colors creatively
    if age < 6:
        attr = colors[4] | curses.A_BOLD  # Hot magenta
    elif age < 15:
        attr = colors[4]  # Magenta
    elif age < 24:
        attr = colors[1] | curses.A_BOLD  # Bright (like yellow-ish)
    elif age < 36:
        attr = colors[1]  # Green (ember-ish)
    elif age < 48:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    # Random spark/ember effect
    if random.random() < 0.05:
        char = random.choice(["*", "✦", "⁕"])
        attr = colors[4] | curses.A_BOLD

    return (char, attr)
