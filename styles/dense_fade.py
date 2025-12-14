"""Dense Fade - Solid blocks with pure brightness fade"""

import curses

STYLE_NAME = "Dense Fade"
STYLE_DESCRIPTION = "Solid blocks with smooth brightness gradient"


def render_waveform(amp, age, colors):
    """
    Render waveform with dense fade effect.

    Uses only solid block characters with varying brightness
    levels to create a pure, smooth phosphor-like fade.
    """
    if age >= 100:
        return None

    # Always solid blocks - the density comes from brightness variation
    intensity = abs(amp)

    # Block density based on amplitude
    if intensity > 0.7:
        char = "█"
    elif intensity > 0.5:
        char = "▓"
    elif intensity > 0.3:
        char = "▒"
    else:
        char = "░"

    # Very smooth brightness gradient over time
    if age < 2:
        attr = colors[1] | curses.A_BOLD | curses.A_STANDOUT
    elif age < 4:
        attr = colors[1] | curses.A_BOLD
    elif age < 7:
        attr = colors[1]
    elif age < 11:
        # Transition zone
        char = "▓" if char == "█" else char
        attr = colors[1]
    elif age < 15:
        char = "▒" if char in ["█", "▓"] else char
        attr = colors[2]
    elif age < 19:
        char = "░" if char in ["█", "▓", "▒"] else char
        attr = colors[2]
    else:
        char = "░"
        attr = colors[2] | curses.A_DIM

    return (char, attr)
