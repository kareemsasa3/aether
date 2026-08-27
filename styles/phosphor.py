"""Phosphor - X-Y oscilloscope Lissajous trace with green phosphor decay"""

import curses
import math

STYLE_NAME = "Phosphor"
STYLE_DESCRIPTION = "X-Y scope Lissajous figure traced in decaying green phosphor"

# Brightness ramp for the persistence grid, hottest first. With the 0.70
# decay only the freshest trace is HOT; the afterglow cools in ~5 frames.
_HOT = 0.9
_MID = 0.5
_LOW = 0.25
_EMBER = 0.1

# Persistence grid, smoothed signal trackers, and the beam state (phase
# accumulators thx/thy plus last sweep's amplitudes), keyed by canvas size.
# The beam is continuous: every sweep starts exactly where the last ended,
# so the trace can never show a loose end. last_frame guards double-advance
# when a frame repaints.
_state = {
    "size": None,
    "grid": [],
    "bass": 0.0,
    "treble": 0.0,
    "amp": 0.0,
    "fx": 2.0,
    "fy": 3.0,
    "fxi": 2,
    "fyi": 3,
    "thx": 0.0,
    "thy": 0.0,
    "ax": None,
    "ay": None,
    "spec": None,
    "flux": 0.0,
    "excite": 0.0,
    "tint": bytearray(),
    "last_frame": None,
}


def _draw_graticule(ctx, canvas):
    """Faint scope graticule: center axes with ticks, corners marked."""
    h, w = ctx.height, ctx.width
    cy, cx = h // 2, w // 2
    attr = ctx.colors[8] | curses.A_DIM
    for x in range(0, w, 4):
        canvas.set(cy, x, "·", attr)
    for y in range(0, h, 2):
        canvas.set(y, cx, "·", attr)
    canvas.set(cy, cx, "┼", attr)


def render_frame(ctx, canvas):
    """Bass and treble bend the figure, beats spin it, silence idles it.

    An X-Y oscilloscope: the trace is a Lissajous curve whose x/y
    frequencies track the smoothed bass and treble bands, redrawn every
    frame into a persistence grid that decays like CRT phosphor, so the
    figure leaves a fading green afterglow as the music reshapes it.
    """
    h, w = ctx.height, ctx.width
    if h < 1 or w < 1:
        return

    st = _state
    if st["size"] != (h, w):
        st["size"] = (h, w)
        st["grid"] = [0.0] * (h * w)
        st["bass"] = st["treble"] = st["amp"] = 0.0
        st["fx"], st["fy"] = 2.0, 3.0
        st["fxi"], st["fyi"] = 2, 3
        st["thx"] = st["thy"] = 0.0
        st["ax"] = st["ay"] = None
        st["spec"], st["flux"] = None, 0.0
        st["excite"] = 0.0
        st["tint"] = bytearray(h * w)
        st["last_frame"] = None
    advance = st["last_frame"] != ctx.frame
    st["last_frame"] = ctx.frame

    grid = st["grid"]
    if advance:
        # Heavy smoothing keeps the figure morphing instead of jittering.
        st["bass"] += (ctx.bass - st["bass"]) * 0.08
        st["treble"] += (ctx.treble - st["treble"]) * 0.08
        st["amp"] += (max(abs(ctx.amp), ctx.bass, ctx.mid) - st["amp"]) * 0.06
        # Integer frequency targets (with hysteresis) so the figure closes
        # when the bands hold steady; easing between targets sweeps through
        # detuned ratios, so a morph reads as a brief spin — exactly how a
        # real scope behaves while its inputs drift.
        if st["bass"] > 0.6:
            st["fxi"] = 3
        elif st["bass"] < 0.35:
            st["fxi"] = 2
        if st["treble"] > 0.55:
            st["fyi"] = 5
        elif 0.25 < st["treble"] < 0.45:
            st["fyi"] = 4
        elif st["treble"] < 0.15:
            st["fyi"] = 3
        # Ease fast: a detuned (non-integer) ratio precesses hard every
        # sweep, so lingering between integers piles rotated afterglow
        # copies into fog. A quick snap reads as one beat-sized spin.
        st["fx"] += (st["fxi"] - st["fx"]) * 0.25
        st["fy"] += (st["fyi"] - st["fy"]) * 0.25
        # Spectral flux: how much the spectrum moved since last frame,
        # relative to its level. Steady tones ~0, percussive/noisy ~1.
        spec = list(ctx.spectrum)
        prev = st["spec"]
        if prev is not None and len(prev) == len(spec) and spec:
            delta = sum(abs(a - b) for a, b in zip(spec, prev)) / len(spec)
            level = sum(spec) / len(spec)
            st["flux"] += (min(1.0, delta / (level + 0.05)) - st["flux"]) * 0.15
        st["spec"] = spec
        # Excitation glides toward the flux target: 0 = resting green,
        # 1 = active (cyan arcs), 2 = overdriven (magenta arcs). The climb
        # above 1 is deliberately slow so magenta only appears during
        # genuinely sustained activity; cooling back down is quicker.
        target = 2.0 if st["flux"] > 0.30 else 1.0 if st["flux"] > 0.12 else 0.0
        e = st["excite"]
        if target > e:
            rate = 0.06 if e < 1.0 else 0.015
        else:
            rate = 0.10
        e += (target - e) * rate
        if abs(target - e) < 0.02:
            e = target
        st["excite"] = e
        grid[:] = [v * 0.70 if v > 0.04 else 0.0 for v in grid]

    idle = ctx.silence_frames > 30

    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    breathe = 1.0 + 0.08 * math.sin(ctx.frame * 0.05)
    size = (0.30 + 0.62 * min(1.0, st["amp"])) * breathe
    ax = max(0.0, cx - 0.5) * size
    ay = max(0.0, cy - 0.5) * size

    if advance:
        # Standby trace burns dimmer, live trace at full brightness.
        heat = 0.55 if idle else 1.0
        steps = max(160, 6 * (w + h))
        two_pi = 2.0 * math.pi
        # One full figure per sweep, plus a slight detune that beats
        # accelerate — the classic rotating-Lissajous effect.
        sweep_x = st["fx"] * two_pi + 0.012 + 0.05 * ctx.beat
        sweep_y = st["fy"] * two_pi
        ax0 = st["ax"] if st["ax"] is not None else ax
        ay0 = st["ay"] if st["ay"] is not None else ay
        thx, thy = st["thx"], st["thy"]
        px = int(cx + ax0 * math.sin(thx) + 0.5)
        py = int(cy + ay0 * math.sin(thy) + 0.5)
        tint = st["tint"]
        tint[:] = bytes(h * w)
        # Tint follows the beam's normalized local speed, so excited colors
        # form coherent arcs along the trace instead of scattered cells.
        # Excitation lowers the speed threshold: at rest nothing qualifies
        # (pure green), rising activity lets cyan spread in from the
        # fastest arcs, and only the sustained regime (excite > 1) starts
        # tipping those arcs to magenta.
        e = st["excite"]
        smax = math.hypot(ax * st["fx"], ay * st["fy"])
        cyan_thr = 1.02 - 0.14 * min(e, 1.0)
        mag_thr = 1.02 - 0.12 * max(0.0, e - 1.0)
        glint = ctx.beat > 0.8
        for t in range(1, steps + 1):
            u = t / steps
            argx = thx + sweep_x * u
            argy = thy + sweep_y * u
            # Amplitude eases along the sweep so swells stay seamless too.
            axu = ax0 + (ax - ax0) * u
            ayu = ay0 + (ay - ay0) * u
            x = int(cx + axu * math.sin(argx) + 0.5)
            y = int(cy + ayu * math.sin(argy) + 0.5)
            # Comet ramp: the oldest quarter of the sweep grades up from
            # last frame's decayed head, so the seam carries no visible end.
            hstamp = heat * (0.70 + 0.30 * min(1.0, u * 4.0))
            if glint and u > 0.97:
                # Beats put a brief gold glint on the beam head only.
                tc = 3
            elif smax > 1e-9:
                sn = math.hypot(
                    axu * st["fx"] * math.cos(argx),
                    ayu * st["fy"] * math.cos(argy),
                ) / smax
                tc = 2 if (e > 1.0 and sn > mag_thr) else 1 if sn > cyan_thr else 0
            else:
                tc = 0
            # Fast sections can jump cells between samples; fill the
            # segment so the trace stays connected at any speed.
            gap = max(abs(x - px), abs(y - py))
            for k in range(1, gap):
                iy = py + (y - py) * k // gap
                ix = px + (x - px) * k // gap
                if 0 <= iy < h and 0 <= ix < w:
                    idx = iy * w + ix
                    if grid[idx] < hstamp:
                        grid[idx] = hstamp
                    tint[idx] = tc
            px, py = x, y
            if 0 <= y < h and 0 <= x < w:
                idx = y * w + x
                if grid[idx] < hstamp:
                    grid[idx] = hstamp
                tint[idx] = tc
        st["thx"] = math.fmod(thx + sweep_x, two_pi)
        st["thy"] = math.fmod(thy + sweep_y, two_pi)
        st["ax"], st["ay"] = ax, ay

    _draw_graticule(ctx, canvas)

    colors = ctx.colors
    # Home color is green everywhere — the afterglow always, and the beam
    # at rest. The tint grid carries the excitation arcs (see the sweep).
    tint = st["tint"]
    hot_attrs = (
        colors[1] | curses.A_BOLD,
        colors[3] | curses.A_BOLD,
        colors[4] | curses.A_BOLD,
        colors[6] | curses.A_BOLD,
    )
    for y in range(h):
        row = y * w
        for x in range(w):
            v = grid[row + x]
            if v >= _HOT:
                canvas.set(y, x, "▓", hot_attrs[tint[row + x]])
            elif v >= _MID:
                canvas.set(y, x, "▒", colors[1])
            elif v >= _LOW:
                canvas.set(y, x, "░", colors[2])
            elif v >= _EMBER:
                canvas.set(y, x, "·", colors[2] | curses.A_DIM)


def render_waveform(i, amp, age, max_width, colors, sample_id=0):
    """Legacy single-cell fallback (kept for the stable style contract)."""
    if age >= 70:
        return None

    intensity = abs(amp)
    if intensity > 0.6:
        char = "●"
    elif intensity > 0.35:
        char = "•"
    elif intensity > 0.12:
        char = "∙"
    else:
        char = "·"

    # Phosphor afterglow: bright green trace cooling into the dim band.
    if age < 8:
        attr = colors[1] | curses.A_BOLD
    elif age < 25:
        attr = colors[1]
    elif age < 45:
        attr = colors[2]
    else:
        attr = colors[2] | curses.A_DIM

    return (char, attr)
