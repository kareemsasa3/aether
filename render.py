"""Terminal rendering primitives for the Aether visualizer.

Phase 3 of the TUI refactor (see REFACTOR.md): generic, domain-free
terminal/curses helpers move here. They are pure functions of their explicit
arguments and own no visualizer state, so the bounds-clipping and
background-character logic is unit-testable with a fake stdscr.

`recalculate_layout` intentionally stays on `UltimateOscilloscope`. The coupling
audit (see REFACTOR.md) found it writes ~25 instance fields — geometry, the
waveform deques, and the performance counters — so it is layout *state*, not a
render primitive, and belongs to the later state extraction (Phase 4) rather
than here.
"""

import curses


def init_colors():
    """Initialize the curses color palette.

    Uses 256-color mode when available for richer colors, falling back to the
    basic 8 colors otherwise. Must run after the screen is initialized.
    """
    curses.use_default_colors()

    # Enhanced color palette
    # Using 256-color mode if available for richer colors. This must NOT be
    # gated on can_change_color(): most 256-color terminals report False for
    # it, but init_pair with palette indices >= 16 works regardless — the old
    # gate silently dropped every terminal to the dull 8-color fallback.
    if curses.COLORS >= 256:
        # Custom colors for a more vibrant look
        curses.init_pair(1, 46, -1)  # Bright green (neon)
        curses.init_pair(2, 22, -1)  # Dim green (forest)
        curses.init_pair(3, 51, -1)  # Cyan (electric)
        curses.init_pair(4, 201, -1)  # Magenta (hot pink)
        curses.init_pair(5, 33, -1)  # Blue (deep)
        curses.init_pair(6, 226, -1)  # Yellow (gold)
        curses.init_pair(7, 208, -1)  # Orange (amber)
        curses.init_pair(8, 245, -1)  # Gray (subtle)
        curses.init_pair(9, 196, -1)  # Red (hot)
        curses.init_pair(10, 129, -1)  # Purple (violet)
    else:
        # Fallback to basic 8 colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_BLUE, -1)
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.init_pair(7, curses.COLOR_YELLOW, -1)  # Orange fallback
        curses.init_pair(8, curses.COLOR_WHITE, -1)  # Gray fallback
        curses.init_pair(9, curses.COLOR_RED, -1)
        curses.init_pair(10, curses.COLOR_MAGENTA, -1)


def safe_addstr(stdscr, height, width, y, x, text, attr=0):
    """Bounds-checked addstr: clip text to the screen and swallow curses errors.

    Mirrors the former UltimateOscilloscope.safe_addstr exactly; `height` and
    `width` are the cached screen dimensions the caller already tracks.
    """
    try:
        if 0 <= y < height and 0 <= x < width:
            text = str(text)[: width - x - 1]
            stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


class Canvas:
    """A 2D cell buffer a frame style paints into before it is blitted.

    Cells are (char, attr) tuples and default to a plain space, so a canvas
    both draws this frame and erases the last one when blitted over the
    waveform region. set() silently clips out-of-bounds writes, mirroring
    safe_addstr, so styles never need their own bounds checks.
    """

    def __init__(self, height, width):
        self.height = max(0, height)
        self.width = max(0, width)
        self.cells = [[(" ", 0)] * self.width for _ in range(self.height)]

    def set(self, y, x, char, attr=0):
        if 0 <= y < self.height and 0 <= x < self.width and char:
            self.cells[y][x] = (char[0], attr)

    def get(self, y, x):
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.cells[y][x]
        return (" ", 0)

    def iter_runs(self):
        """Yield (y, x, text, attr) for runs of consecutive same-attr cells.

        One addstr per run instead of per cell keeps the full-region repaint
        cheap at target FPS.
        """
        for y, row in enumerate(self.cells):
            x = 0
            while x < self.width:
                attr = row[x][1]
                start = x
                chars = []
                while x < self.width and row[x][1] == attr:
                    chars.append(row[x][0])
                    x += 1
                yield y, start, "".join(chars), attr


class FrameContext:
    """Read-only inputs for a style's render_frame(ctx, canvas) call.

    Everything a full-frame style needs to compose a scene: canvas geometry,
    a frame counter (styles animate off this — never wall-clock time — so a
    frame is reproducible for a fixed state), band energies, the beat pulse,
    per-column wave samples as (amplitude, age) with index 0 at the left
    edge and fresh samples near the center, and the full 10-color table.
    """

    def __init__(
        self,
        *,
        frame,
        width,
        height,
        amp,
        bass,
        mid,
        treble,
        spectrum,
        beat,
        silence_frames,
        columns,
        colors,
    ):
        self.frame = frame
        self.width = width
        self.height = height
        self.amp = amp
        self.bass = bass
        self.mid = mid
        self.treble = treble
        self.spectrum = spectrum
        self.beat = beat
        self.silence_frames = silence_frames
        self.columns = columns
        self.colors = colors


def blit_canvas(stdscr, height, width, canvas, top, left):
    """Draw a Canvas at (top, left) using bounds-clipped writes."""
    for y, x, text, attr in canvas.iter_runs():
        safe_addstr(stdscr, height, width, top + y, left + x, text, attr)


def get_bg_char(waveform_start, waveform_height, y, x):
    """Background character/attr for coordinate (y, x).

    Draws the dim center line of the waveform area; every other cell is blank.
    `x` is accepted for call-site compatibility but is not used (the center line
    spans the full width).
    """
    center_y = waveform_start + (waveform_height // 2)

    # Center Line Only
    if y == center_y:
        return "─", curses.color_pair(2)  # Dim green

    return " ", 0
