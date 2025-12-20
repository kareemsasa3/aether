"""Neon Wave - Vibrant glowing waveform with color transitions"""

import curses
import math

STYLE_NAME = "Neon Wave"
STYLE_DESCRIPTION = "Vibrant neon glow with smooth color transitions"


def render_waveform(i, amp, age, max_width, colors):
    """
    Render waveform with neon glow effect.
    
    Creates a vibrant, glowing waveform that transitions through
    colors based on amplitude and fades gracefully with age.
    """
    if age >= 80:
        return None

    abs_amp = abs(amp)
    
    # Character selection based on amplitude for smooth curves
    if abs_amp > 0.7:
        char = "█"  # Solid for peaks
    elif abs_amp > 0.5:
        char = "▓"
    elif abs_amp > 0.3:
        char = "▒"
    elif abs_amp > 0.15:
        char = "░"
    elif abs_amp > 0.05:
        char = "·"
    else:
        char = "∙"

    # Color based on amplitude - creates rainbow effect on peaks
    # Fresh signals get vibrant colors, older ones fade to green
    if age < 4:
        # Brand new - hot colors based on amplitude
        if abs_amp > 0.7:
            attr = colors[4] | curses.A_BOLD  # Magenta/pink for peaks
        elif abs_amp > 0.4:
            attr = colors[3] | curses.A_BOLD  # Cyan for high
        else:
            attr = colors[1] | curses.A_BOLD  # Green for normal
    elif age < 12:
        # Still fresh - bright colors
        if abs_amp > 0.5:
            attr = colors[3] | curses.A_BOLD  # Cyan
        else:
            attr = colors[1] | curses.A_BOLD  # Bright green
    elif age < 30:
        # Medium age - standard green
        attr = colors[1]
    elif age < 50:
        # Aging - dim green  
        attr = colors[2]
    else:
        # Old - very dim
        attr = colors[2] | curses.A_DIM

    return (char, attr)

