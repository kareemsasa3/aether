"""Spectra - full-width mirrored spectrum bars with falling peak caps"""

import curses

STYLE_NAME = "Spectra"
STYLE_DESCRIPTION = "Full-width mirrored spectrum bars with falling peak caps"

# Rainbow ramp across the frequency axis, low to high.
_RAMP = [10, 4, 5, 3, 1, 6, 7]

# Bottom-up partial blocks for smooth bar tops above the center line.
_TIP_BLOCKS = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

# Per-bar display state: smoothed heights and falling peak caps, keyed by
# bar count. last_frame guards double-advance when a frame repaints.
_state = {"bars": None, "display": [], "peaks": [], "last_frame": None}


def _bar_targets(spectrum, num_bars):
    """Linearly interpolate the 12 spectrum bins across num_bars bars."""
    targets = []
    top = len(spectrum) - 1
    for b in range(num_bars):
        pos = (b / max(1, num_bars - 1)) * top
        lo = int(pos)
        hi = min(top, lo + 1)
        frac = pos - lo
        targets.append(spectrum[lo] * (1 - frac) + spectrum[hi] * frac)
    return targets


def render_frame(ctx, canvas):
    h, w = ctx.height, ctx.width
    center = h // 2
    max_half = max(1, center - 1)

    bar_w, gap = 3, 1
    num_bars = max(1, w // (bar_w + gap))

    st = _state
    if st["bars"] != num_bars:
        st["bars"] = num_bars
        st["display"] = [0.0] * num_bars
        st["peaks"] = [0.0] * num_bars
        st["last_frame"] = None
    advance = st["last_frame"] != ctx.frame
    st["last_frame"] = ctx.frame

    targets = _bar_targets(ctx.spectrum, num_bars)
    if advance:
        for b in range(num_bars):
            st["display"][b] += (targets[b] - st["display"][b]) * 0.4
            st["peaks"][b] = max(st["peaks"][b] - 0.15, st["display"][b] * max_half)

    colors = ctx.colors
    hot = ctx.beat > 0.6

    # Center baseline, flashing bold on beats so hits land visibly.
    baseline_attr = colors[8] | (curses.A_BOLD if hot else curses.A_DIM)
    for x in range(w):
        canvas.set(center, x, "━" if hot else "─", baseline_attr)

    for b in range(num_bars):
        x0 = b * (bar_w + gap)
        color = colors[_RAMP[(b * len(_RAMP)) // num_bars]]
        d = st["display"][b] * max_half
        cells = int(d)
        frac = d - cells
        attr = color | (curses.A_BOLD if (hot or st["display"][b] > 0.6) else 0)

        for x in range(x0, min(x0 + bar_w, w)):
            for k in range(1, cells + 1):
                canvas.set(center - k, x, "█", attr)
                canvas.set(center + k, x, "█", attr)
            if frac > 0.12:
                canvas.set(center - cells - 1, x, _TIP_BLOCKS[int(frac * 8)], attr)
                canvas.set(
                    center + cells + 1, x, "▀" if frac >= 0.5 else "░", attr
                )
            # Peak caps hover above the bars and sink back down.
            pk = int(st["peaks"][b])
            if pk > cells + 1:
                canvas.set(center - pk, x, "▬", colors[8])
                canvas.set(center + pk, x, "▬", colors[8])

    # Quiet passages: a glint patrols the baseline so the frame stays alive.
    if ctx.silence_frames > 45:
        glint = (ctx.frame * 2) % max(1, w)
        canvas.set(center, glint, "◆", colors[3] | curses.A_BOLD)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 70:
        return None

    intensity = abs(amp)
    # Rainbow by position across the half-width, matching the bar ramp.
    color = colors[_RAMP[min(len(_RAMP) - 1, (i * len(_RAMP)) // max(1, max_width))]]

    if intensity > 0.7:
        char = "█"
    elif intensity > 0.45:
        char = "▓"
    elif intensity > 0.2:
        char = "▒"
    else:
        char = "░"

    if age < 10:
        attr = color | curses.A_BOLD
    elif age < 35:
        attr = color
    else:
        attr = colors[8] | curses.A_DIM

    return (char, attr)
