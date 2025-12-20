"""Glitch Art - Intentionally corrupted visual aesthetic"""

import curses
import random

STYLE_NAME = "Glitch Art"
STYLE_DESCRIPTION = "Corrupted, glitchy characters with visual artifacts"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with glitch art effect.

    Uses intentionally "broken" looking characters and random
    visual artifacts for a corrupted digital aesthetic.
    """
    if age >= 100:
        return None

    # Use seeded random for stability
    rng = random.Random(sample_id)

    # Glitch characters - mix of broken/corrupted symbols
    glitch_chars = [
        "█",
        "▓",
        "▒",
        "░",
        "¥",
        "₿",
        "§",
        "¶",
        "†",
        "‡",
        "╳",
        "╱",
        "╲",
        "╬",
        "╋",
        "⌐",
        "¬",
        "¦",
        "|",
        "/",
        "@",
        "#",
        "%",
        "&",
        "*",
        "░",
        "▒",
        "▓",
        "█",
    ]

    # More chaotic at newer ages, settling down as it ages
    if age < 3:
        # Full glitch chaos
        char = rng.choice(glitch_chars)
        # Random color flicker
        color_pick = rng.choice([1, 2, 3, 4, 5])
        attr = colors[color_pick] | curses.A_BOLD
    elif age < 6:
        # Moderate glitch
        char = rng.choice(glitch_chars[:15])
        attr = colors[rng.choice([1, 3])] | curses.A_BOLD
    elif age < 12:
        # Settling glitch
        char = rng.choice(["▓", "▒", "░", "█", "|", "¦"])
        attr = colors[1]
    elif age < 18:
        # Fading glitch
        char = rng.choice(["░", ".", "·", " ", "´"])
        attr = colors[2]
    else:
        char = rng.choice([" ", ".", "·"])
        attr = colors[2] | curses.A_DIM

    # Random "corruption burst" - stable per sample
    if rng.random() < 0.05:
        char = rng.choice(["█", "▓", "▒"])
        attr = colors[rng.choice([4, 5])] | curses.A_BOLD | curses.A_REVERSE

    return (char, attr)
