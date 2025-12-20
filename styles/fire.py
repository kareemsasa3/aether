"""Fire - Flame-like rising effect with warmth"""

import curses
import random

STYLE_NAME = "Fire"
STYLE_DESCRIPTION = "Rising flames with warm color transitions"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with fire/flame effect.

    Creates rising flame-like patterns with characters
    that suggest heat and movement upward.
    """
    if age >= 60:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    # Flame characters - from dense to sparse
    hot_flames = ["█", "▓", "░", "▒"]
    med_flames = ["ᚈ", "₪", "※", "⁂", "⁕"]
    dim_flames = ["∵", "·", "°", "˚", "'", "`"]

    # Fire rises - so positive amplitude gets hot chars
    if amp > 0.3:
        if age < 12:
            char = rng.choice(hot_flames[:2])
        elif age < 30:
            char = rng.choice(hot_flames)
        else:
            char = rng.choice(med_flames)
    elif amp > -0.1:
        # Middle flames
        char = rng.choice(med_flames)
    else:
        # Base embers
        char = rng.choice(dim_flames)

    # Fire color: magenta/red -> yellow-ish -> dim
    if age < 6:
        attr = colors[4] | curses.A_BOLD  # Hot magenta
    elif age < 15:
        attr = colors[4]  # Magenta
    elif age < 24:
        attr = colors[1] | curses.A_BOLD  # Bright
    elif age < 36:
        attr = colors[1]  # Green
    elif age < 48:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    # Random spark/ember effect - now stable per sample
    if rng.random() < 0.05:
        char = rng.choice(["*", "✦", "⁕"])
        attr = colors[4] | curses.A_BOLD

    return (char, attr)
