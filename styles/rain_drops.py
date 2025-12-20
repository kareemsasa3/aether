"""Rain Drops - Gentle falling droplets effect"""

import curses
import random

STYLE_NAME = "Rain Drops"
STYLE_DESCRIPTION = "Gentle falling water droplets and splashes"


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """
    Render waveform with rain drops effect.

    Creates falling droplets with splash effects,
    giving a gentle, ambient water aesthetic.
    """
    if age >= 100:
        return None

    intensity = abs(amp)

    # Droplet characters
    drops = ["●", "○", "◦", "·", "∘"]
    falling = ["│", "|", "¦", ":", "!"]
    splash = ["○", "◦", "·", "∙", "˙", ",", "`", "'"]

    # Fresh = big drops, older = smaller/splash
    if age < 3:
        if intensity > 0.4:
            char = drops[0]  # Big drop
        else:
            char = drops[1]
    elif age < 8:
        if amp > 0:
            char = random.choice(falling[:3])  # Falling
        else:
            char = random.choice(drops[1:4])
    elif age < 15:
        char = random.choice(splash[:4])  # Splash spreading
    else:
        char = random.choice(splash[4:])  # Dissipating

    # Blue/cyan for water feel
    if age < 2:
        attr = colors[3] | curses.A_BOLD  # Cyan bright
    elif age < 6:
        attr = colors[5] | curses.A_BOLD  # Blue
    elif age < 10:
        attr = colors[3]  # Cyan
    elif age < 16:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    # Occasional ripple effect
    if random.random() < 0.03:
        char = random.choice(["~", "≈", "∿"])
        attr = colors[5]

    return (char, attr)
