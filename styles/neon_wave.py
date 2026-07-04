"""Neon Wave - flagship mirrored neon wave with beat flash and peak trails"""

import curses
import math

STYLE_NAME = "Neon Wave"
STYLE_DESCRIPTION = "Mirrored neon glow wave with beat flashes and peak trails"

# Bottom-up partial blocks for smooth column tips above the center line.
_TIP_BLOCKS = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

# Per-size peak-hold state: peaks fall a little every frame, leaving a
# visible trail above the live wave. Keyed off the canvas width so a resize
# starts fresh; last_frame guards against double-advancing when a frame is
# drawn more than once (e.g. after an overlay closes).
_state = {"width": None, "peaks": [], "last_frame": None}


def _column_attr(q, a, age, beat, colors):
    """Color for a body cell: deep blue core, cyan body, hot tips.

    q is the cell's position within its own column (0 center .. 1 tip), a the
    column's amplitude, age its sample age. Old samples fade to dim green so
    the wave trails off at the edges like phosphor.
    """
    if age > 60:
        return colors[2]
    if q < 0.4:
        attr = colors[5]
    elif q < 0.75:
        attr = colors[3]
    elif a > 0.6:
        attr = colors[4] | curses.A_BOLD
    else:
        attr = colors[3] | curses.A_BOLD
    if beat > 0.6:
        attr |= curses.A_BOLD
    return attr


def _render_ambient(ctx, canvas, center):
    """Quiet-state visuals: a slowly breathing dotted wave with sparkles."""
    breath = 1.0 + 0.6 * math.sin(ctx.frame * 0.02)
    for x in range(ctx.width):
        y = center + round(math.sin(x * 0.12 + ctx.frame * 0.06) * breath)
        if (x * 7 + ctx.frame // 8) % 97 == 0:
            canvas.set(y, x, "✧", ctx.colors[3])
        else:
            canvas.set(y, x, "·", ctx.colors[2])


def render_frame(ctx, canvas):
    """Compose the full scene: baseline, mirrored gradient wave, peak trails."""
    h, w = ctx.height, ctx.width
    center = h // 2
    max_half = max(1, center - 1)

    st = _state
    if st["width"] != w:
        st["width"] = w
        st["peaks"] = [0.0] * w
    advance = st["last_frame"] != ctx.frame
    st["last_frame"] = ctx.frame

    if ctx.silence_frames > 45:
        if advance:
            st["peaks"] = [0.0] * w
        _render_ambient(ctx, canvas, center)
        return

    # Beat pulse physically enlarges the wave so hits visibly jump.
    scale = max_half * (1.0 + 0.3 * ctx.beat)
    colors = ctx.colors

    for x in range(w):
        amp, age = ctx.columns[x]
        a = min(1.0, abs(amp))
        d = a * scale
        cells = int(d)
        frac = d - cells

        # Peak hold: rise instantly, fall slowly.
        if d > st["peaks"][x]:
            st["peaks"][x] = d
        elif advance:
            st["peaks"][x] = max(0.0, st["peaks"][x] - 0.35)

        if d < 0.1:
            canvas.set(center, x, "·", colors[2])
        else:
            # Solid body, mirrored above and below the center line.
            for k in range(cells + 1):
                q = k / max_half
                attr = _column_attr(q, a, age, ctx.beat, colors)
                canvas.set(center - k, x, "█", attr)
                canvas.set(center + k, x, "█", attr)
            # Smooth partial tip; sparkles when the highs are hot.
            tip = cells + 1
            if a > 0.75 and ctx.treble > 0.5:
                tip_attr = colors[6] | curses.A_BOLD
                canvas.set(center - tip, x, "✦", tip_attr)
                canvas.set(center + tip, x, "✦", tip_attr)
            elif frac > 0.1:
                tip_attr = _column_attr(1.0, a, age, ctx.beat, colors)
                canvas.set(center - tip, x, _TIP_BLOCKS[int(frac * 8)], tip_attr)
                canvas.set(
                    center + tip, x, "▀" if frac >= 0.5 else "░", tip_attr
                )

        # Peak trail markers hover above the live wave and sink back down.
        pk = int(st["peaks"][x])
        if pk > cells + 1:
            canvas.set(center - pk, x, "·", colors[8])
            canvas.set(center + pk, x, "·", colors[8])


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
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
