#!/usr/bin/env python3
# aether.py - THE FINAL FORM
import curses
import time
import sys
import importlib.util
from pathlib import Path
from aether_shm import AetherSharedMemory, read_event_legacy
import aether_config as config
from ui import overlays
from config_model import VizConfig
from engine import VisualizerState
import render


class UltimateOscilloscope:
    # Static defaults
    TARGET_FPS = config.VIZ_FPS
    DEBUG_MODE = False
    BURST_WIDTH_RATIO = 0.6

    # Config schema and presets now live in config_model. Kept here as
    # class-level references so the (still viz-driven) config overlay can read
    # them via the instance unchanged; VizConfig owns the actual values.
    CONFIG_SCHEMA = VizConfig.CONFIG_SCHEMA
    PRESETS = VizConfig.PRESETS

    def __init__(self, stdscr, style_module):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.stdscr.nodelay(True)

        # Configurable settings now live in the config model.
        self.config_model = VizConfig()

        # Config menu state
        self.config_keys = self.config_model.keys

        # Initialize the curses color palette (256-color with 8-color fallback).
        render.init_colors()

        # State Initialization
        self.design_mode = "OSCILLOSCOPE"  # Options: "OSCILLOSCOPE", "SPECTRUM"

        # Signal/ingestion state: waveform buffers, spectrum, RGB levels, and
        # the smoothing scalars. Lives in engine.VisualizerState; draw methods
        # reach it through the read-only compatibility properties below.
        self.state = VisualizerState()

        # Event tracking
        self.last_event_time = 0

        # Initialize Shared Memory Reader
        self.shm = AetherSharedMemory(is_writer=False)

        # Style module for waveform rendering
        self.style = style_module

        # Calculate Layout (depends on state above)
        self.recalculate_layout()

        # Draw static elements (depends on layout)
        self.draw_static_elements()

    # The config helpers below delegate to self.config_model. They remain on
    # the oscilloscope so the (still viz-driven) config overlay can call them
    # unchanged; migrating the overlay to use VizConfig directly is deferred.
    def _get_config_value(self, key):
        """Get current value of a config setting"""
        return self.config_model.get(key)

    def _set_config_value(self, key, value):
        """Set a config value, clamping to valid range"""
        self.config_model.set(key, value)

    def _load_preset(self, preset_name):
        """Load a configuration preset"""
        return self.config_model.apply_preset(preset_name)

    # Read-only views onto the signal engine's state, so the draw/status methods
    # keep reading self.<field> unchanged this phase. Writes happen inside the
    # engine (ingest/decay/add_scroll_sample), never directly on the oscilloscope.
    @property
    def spectrum_values(self):
        return self.state.spectrum_values

    @property
    def waveform_left(self):
        return self.state.waveform_left

    @property
    def waveform_right(self):
        return self.state.waveform_right

    @property
    def waveform_age_left(self):
        return self.state.waveform_age_left

    @property
    def waveform_age_right(self):
        return self.state.waveform_age_right

    @property
    def bass_level(self):
        return self.state.bass_level

    @property
    def mid_level(self):
        return self.state.mid_level

    @property
    def treble_level(self):
        return self.state.treble_level

    @property
    def current_freq(self):
        return self.state.current_freq

    def recalculate_layout(self):
        """Update dimensions and buffers on resize"""
        h, w = self.stdscr.getmaxyx()
        self.height = h
        self.width = w

        # LAYOUT DISPATCH
        if self.design_mode == "SPECTRUM":
            # --- SPECTRUM MODE LAYOUT ---
            # Maximize spectrum area, hide waveform or make it tiny
            HEADER_LINES = 3
            STATUS_LINE = 1

            # Use most space for spectrum
            self.spectrum_start = HEADER_LINES
            self.spectrum_height = max(10, h - HEADER_LINES - STATUS_LINE - 1)
            self.spectrum_end = self.spectrum_start + self.spectrum_height
            self.spectrum_width = w

            # Tiny/hidden waveform area (required for buffer logic)
            self.waveform_start = h  # Off screen
            self.waveform_height = 0
            self.waveform_end = h

            # RGB hidden/integrated
            self.rgb_x_start = w  # Off screen
            self.rgb_y_start = h
            self.bottom_panel_start = h

        else:
            # --- OSCILLOSCOPE MODE LAYOUT (Default) ---
            # - Waveform: main area (full width, most of screen height)
            # - Bottom panel: Spectrum (left) + RGB (right)

            # Fixed sizes
            BOTTOM_PANEL_LINES = 4  # Spectrum + RGB area
            STATUS_LINE = 1
            HEADER_LINES = 4  # Border + title + border + waveform label

            # Waveform gets all remaining vertical space (FULL WIDTH)
            self.waveform_start = HEADER_LINES
            self.waveform_height = max(
                10, h - HEADER_LINES - BOTTOM_PANEL_LINES - STATUS_LINE - 1
            )
            self.waveform_end = self.waveform_start + self.waveform_height

            # Bottom panel (spectrum left, RGB right)
            self.bottom_panel_start = self.waveform_end + 1

            # Add separator line
            self.separator_y = self.bottom_panel_start - 1  # For the "─" line

            # Spectrum section
            self.spectrum_start = self.bottom_panel_start + 1  # +1 to skip separator
            self.spectrum_height = BOTTOM_PANEL_LINES - 1  # -1 for separator
            self.spectrum_end = self.spectrum_start + self.spectrum_height
            self.spectrum_width = int(w * 0.6)

            # RGB section (aligned with spectrum)
            self.rgb_x_start = self.spectrum_width + 5
            self.rgb_y_start = self.spectrum_start  # Changed from bottom_panel_start

        # Graph dimensions (FULL WIDTH - no sidebar)
        self.graph_x_start = 3
        self.graph_x_end = w - 3
        self.graph_width = max(10, self.graph_x_end - self.graph_x_start)

        # CENTER-OUT RADIATION: Two deques radiating from center. The signal
        # state owns the waveform buffers; it only needs the half width.
        half_width = max(5, self.graph_width // 2)
        self.state.resize(half_width)

        self.last_ys = [None] * self.graph_width

        # Performance Monitoring
        self.shm_hits = 0
        self.total_reads = 0
        self.total_events = 0
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()

    # Thin delegators to render.py. Kept as methods so the many self./viz.
    # call sites (draw methods and the overlays) stay unchanged this phase.
    def get_bg_char(self, y, x):
        """Get the background character for a given coordinate"""
        return render.get_bg_char(self.waveform_start, self.waveform_height, y, x)

    def safe_addstr(self, y, x, text, attr=0):
        render.safe_addstr(self.stdscr, self.height, self.width, y, x, text, attr)

    def draw_static_elements(self):
        """Draw static UI elements with modern aesthetic"""
        # Top border with gradient effect
        border_chars = "━" * self.width
        self.safe_addstr(0, 0, border_chars, curses.color_pair(8))

        # Title bar - clean modern look
        title = " ◉ AETHER "
        subtitle = "audio visualizer"

        # Draw title on left
        self.safe_addstr(1, 2, title, curses.color_pair(3) | curses.A_BOLD)
        self.safe_addstr(1, 2 + len(title), subtitle, curses.color_pair(8))

        # Draw mode indicator on right
        mode_str = f"[ {self.design_mode} ]"
        self.safe_addstr(
            1, self.width - len(mode_str) - 2, mode_str, curses.color_pair(6)
        )

        # Second border
        self.safe_addstr(2, 0, border_chars, curses.color_pair(8))

        if self.design_mode == "OSCILLOSCOPE":
            # Waveform section label with icon
            label = "◈ WAVEFORM"
            self.safe_addstr(
                self.waveform_start - 1,
                3,
                label,
                curses.color_pair(1) | curses.A_BOLD,
            )

            # Subtle frequency indicator
            if self.current_freq > 0:
                freq_str = f"{self.current_freq:.0f} Hz"
                self.safe_addstr(
                    self.waveform_start - 1,
                    self.width - len(freq_str) - 3,
                    freq_str,
                    curses.color_pair(8),
                )

            # Bottom panel separator - subtle dotted line
            separator = "─" * self.width
            self.safe_addstr(
                self.bottom_panel_start - 1,
                0,
                separator,
                curses.color_pair(8),
            )

            # Spectrum label with icon
            self.safe_addstr(
                self.spectrum_start,
                3,
                "◈ SPECTRUM",
                curses.color_pair(3) | curses.A_BOLD,
            )

            # RGB label with icon
            self.safe_addstr(
                self.rgb_y_start,
                self.rgb_x_start,
                "◈ RGB",
                curses.color_pair(4) | curses.A_BOLD,
            )

        elif self.design_mode == "SPECTRUM":
            self.safe_addstr(
                self.spectrum_start - 1,
                3,
                "◈ FULL SPECTRUM ANALYZER",
                curses.color_pair(3) | curses.A_BOLD,
            )

    def draw_waveform_grid(self):
        """Draw subtle center line with gradient fade at edges"""
        center_y = self.waveform_start + (self.waveform_height // 2)

        # Create a subtle center line with fading edges
        line_width = self.graph_width
        fade_width = min(8, line_width // 6)

        # Draw main center line (dim)
        self.safe_addstr(
            center_y,
            self.graph_x_start + fade_width,
            "─" * (line_width - fade_width * 2),
            curses.color_pair(8),
        )

        # Fading edges using lighter dash characters
        fade_chars = ["╌", "┄", "┈", "·"]
        for i in range(min(fade_width, len(fade_chars))):
            # Left fade
            self.safe_addstr(
                center_y,
                self.graph_x_start + i,
                fade_chars[min(i, len(fade_chars) - 1)],
                curses.color_pair(8),
            )
            # Right fade
            self.safe_addstr(
                center_y,
                self.graph_x_end - i - 1,
                fade_chars[min(i, len(fade_chars) - 1)],
                curses.color_pair(8),
            )

    def draw_waveform(self):
        """Draw waveform radiating from center outward"""
        center_y = self.waveform_start + (self.waveform_height // 2)
        center_x = self.graph_x_start + (self.graph_width // 2)
        scale = int(self.waveform_height * 0.4)

        # Prepare color dict for style
        colors = {
            1: curses.color_pair(1),
            2: curses.color_pair(2),
            3: curses.color_pair(3),
            4: curses.color_pair(4),
            5: curses.color_pair(5),
        }

        # Draw LEFT half (from center going left)
        # Index 0 is at center, higher indices are further left
        for i, (amp, age) in enumerate(zip(self.waveform_left, self.waveform_age_left)):
            amp = max(-1.0, min(1.0, amp))
            if abs(amp) < 0.005:
                continue

            x = center_x - i - 1  # -1 so index 0 is just left of center
            if x < self.graph_x_start:
                continue

            y = int(center_y - (amp * scale))

            if self.waveform_start <= y < self.waveform_end:
                idx = x - self.graph_x_start
                if 0 <= idx < len(self.last_ys):
                    self.last_ys[idx] = y

                # Calculate a stable sample_id that stays with the sample as it radiates.
                # This prevents flickering in styles that use randomness.
                sample_id = i - int(age * self.config_model.samples_per_frame)

                result = self.style.render_waveform(
                    i, amp, age, self.graph_width // 2, colors, sample_id
                )
                if result:
                    char, attr = result
                    self.safe_addstr(y, x, char, attr)

        # Draw RIGHT half (from center going right)
        # Index 0 is at center, higher indices are further right
        for i, (amp, age) in enumerate(
            zip(self.waveform_right, self.waveform_age_right)
        ):
            amp = max(-1.0, min(1.0, amp))
            if abs(amp) < 0.005:
                continue

            x = center_x + i  # index 0 is at center
            if x >= self.graph_x_end:
                continue

            y = int(center_y - (amp * scale))

            if self.waveform_start <= y < self.waveform_end:
                idx = x - self.graph_x_start
                if 0 <= idx < len(self.last_ys):
                    self.last_ys[idx] = y

                # Calculate stable sample_id
                sample_id = i - int(age * self.config_model.samples_per_frame)

                result = self.style.render_waveform(
                    i, amp, age, self.graph_width // 2, colors, sample_id
                )
                if result:
                    char, attr = result
                    self.safe_addstr(y, x, char, attr)

    def draw_frame(self):
        """Dispatch drawing based on current design mode"""
        if self.design_mode == "SPECTRUM":
            self.draw_spectrum_fullscreen()
        else:
            self.draw_waveform()
            self.draw_spectrum()
            self.draw_rgb_preview()

    def draw_spectrum_fullscreen(self):
        """Draw immersive full-screen spectrum analyzer with gradient bars"""
        # Clear spectrum area
        for y in range(self.spectrum_start, self.spectrum_end):
            self.safe_addstr(y, 0, " " * self.width, 0)

        # Band configuration with colors that create a rainbow gradient
        bands_config = [
            ("SUB", 10),  # Purple
            ("BASS", 4),  # Magenta
            ("LOW", 5),  # Blue
            ("MID", 3),  # Cyan
            ("HIGH", 1),  # Green
            ("TREBLE", 6),  # Yellow
            ("AIR", 7),  # Orange
        ]

        band_values = [
            self.spectrum_values[0],
            max(self.spectrum_values[1:3]),
            max(self.spectrum_values[3:5]),
            max(self.spectrum_values[5:8]),
            max(self.spectrum_values[8:10]),
            self.spectrum_values[10],
            self.spectrum_values[11],
        ]

        num_bands = len(bands_config)
        margin_x = 3
        total_width = self.width - (2 * margin_x)
        bar_width = max(3, (total_width // num_bands) - 2)
        bar_max_height = self.spectrum_height - 3

        start_y = self.spectrum_end - 2

        # Block characters for smooth vertical gradient
        blocks = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

        for i, ((name, color_idx), value) in enumerate(zip(bands_config, band_values)):
            x_pos = margin_x + (i * (bar_width + 2))
            color = curses.color_pair(color_idx)

            # Draw label at bottom
            label = name[:bar_width].center(bar_width)
            self.safe_addstr(start_y + 1, x_pos, label, curses.color_pair(8))

            # Calculate bar height (float for smooth top)
            exact_height = value * bar_max_height
            full_blocks = int(exact_height)
            partial = exact_height - full_blocks

            # Draw the bar from bottom up
            for h in range(bar_max_height):
                y = start_y - h

                if h < full_blocks:
                    # Full block with intensity gradient (brighter at top)
                    intensity_factor = 0.5 + (h / bar_max_height) * 0.5
                    attr = color | curses.A_BOLD if intensity_factor > 0.7 else color
                    self.safe_addstr(y, x_pos, "█" * bar_width, attr)

                elif h == full_blocks and partial > 0:
                    # Partial block at top for smooth animation
                    partial_idx = int(partial * 8)
                    partial_char = blocks[min(8, partial_idx)]
                    self.safe_addstr(y, x_pos, partial_char * bar_width, color)

                else:
                    # Empty space - draw very subtle grid
                    if h % 4 == 0:
                        self.safe_addstr(
                            y,
                            x_pos,
                            "·" * bar_width,
                            curses.color_pair(8) | curses.A_DIM,
                        )

    def draw_spectrum(self):
        """Draw compact spectrum analyzer footer with smooth gradient bars"""
        if self.spectrum_height < 3:
            return

        # Band configuration: name, color pair index
        bands_config = [
            ("SUB", 10),  # Purple for sub-bass
            ("BAS", 4),  # Magenta for bass
            ("LMD", 5),  # Blue for low-mid
            ("MID", 3),  # Cyan for mid
            ("HMD", 1),  # Green for high-mid
            ("TRE", 6),  # Yellow for treble
            ("AIR", 7),  # Orange for sparkle/air
        ]

        # Map spectrum_values to 7 bands
        band_values = [
            self.spectrum_values[0],
            max(self.spectrum_values[1:3]),
            max(self.spectrum_values[3:5]),
            max(self.spectrum_values[5:8]),
            max(self.spectrum_values[8:10]),
            self.spectrum_values[10],
            self.spectrum_values[11],
        ]

        # Layout calculation
        start_x = 15
        available_width = self.spectrum_width - start_x - 3
        band_spacing = max(5, available_width // len(bands_config))

        # Vertical bar characters for smooth gradient
        bar_chars = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

        for i, ((name, color_idx), value) in enumerate(zip(bands_config, band_values)):
            x = start_x + (i * band_spacing)
            color = curses.color_pair(color_idx)

            # Map value (0-1) to bar character (0-8)
            level = int(value * 8)
            level = max(0, min(8, level))

            # Draw 3-row meter with smooth transitions
            if level >= 6:
                top_char = bar_chars[min(8, level - 4)]
                mid_char = "█"
            elif level >= 3:
                top_char = " "
                mid_char = bar_chars[min(8, level)]
            else:
                top_char = " "
                mid_char = " "

            # Draw with glow effect on high values
            attr = color | curses.A_BOLD if value > 0.5 else color

            self.safe_addstr(self.spectrum_start, x, top_char, attr)
            self.safe_addstr(self.spectrum_start + 1, x, mid_char, attr)

            # Label with dimmer color
            self.safe_addstr(self.spectrum_start + 2, x, name, curses.color_pair(8))

    def draw_rgb_preview(self):
        """Draw RGB sync preview with gradient bars"""
        x = self.rgb_x_start
        max_bar_width = min(20, self.width - x - 8)

        # Channel configuration with smooth gradient characters
        channels = [
            ("LOW", self.bass_level, 4, 10),  # Magenta/Purple
            ("MID", self.mid_level, 3, 5),  # Cyan/Blue
            ("HI ", self.treble_level, 6, 7),  # Yellow/Orange
        ]

        # Gradient block characters
        gradient = ["░", "▒", "▓", "█"]

        for i, (label, level, color1, color2) in enumerate(channels):
            y = self.rgb_y_start + 1 + i

            # Draw label
            self.safe_addstr(y, x, label, curses.color_pair(8))

            # Calculate bar segments
            bar_length = int(level * max_bar_width)

            if bar_length > 0:
                # Create gradient bar
                bar_x = x + 4
                for j in range(min(bar_length, max_bar_width)):
                    # Transition from color1 to color2 across the bar
                    progress = j / max(1, max_bar_width - 1)
                    color = curses.color_pair(color1 if progress < 0.5 else color2)

                    # Use denser characters toward the front
                    char_idx = min(3, int((1 - j / max(1, bar_length)) * 4))
                    char = gradient[3 - char_idx] if j < bar_length else " "

                    attr = color | curses.A_BOLD if level > 0.6 else color
                    self.safe_addstr(y, bar_x + j, char, attr)

    def draw_debug_stats(self):
        """Draw performance debug overlay"""
        if not self.DEBUG_MODE:
            return

        hit_rate = (
            (self.shm_hits / self.total_reads * 100) if self.total_reads > 0 else 0
        )

        # Calculate recent events per second (rough approximation)
        # For simplicity, we just show total counts, or we could do a window.
        # Let's just show FPS and SHM stats for now as requested.

        stats = (
            f"FPS: {self.fps:.1f} | "
            f"SHM Hits: {self.shm_hits}/{self.total_reads} ({hit_rate:.1f}%) | "
            f"Events: {self.total_events}"
        )
        if self.fps >= 25:
            fps_color = curses.color_pair(1)  # Green
        elif self.fps >= 20:
            fps_color = curses.color_pair(6)  # Yellow
        else:
            fps_color = curses.color_pair(4)  # Magenta (warning)

        self.safe_addstr(1, 2, stats, fps_color | curses.A_BOLD)

    def draw_status(self):
        """Draw modern status bar"""
        status_y = self.height - 1

        # Clear the line first
        self.safe_addstr(status_y, 0, " " * (self.width - 1), curses.color_pair(8))

        # Left side: keyboard hints with subtle separators
        hints = [
            ("S", "Style"),
            ("C", "Config"),
            ("D", "Mode"),
            ("Q", "Quit"),
        ]

        x = 1
        for key, label in hints:
            self.safe_addstr(status_y, x, key, curses.color_pair(6) | curses.A_BOLD)
            self.safe_addstr(status_y, x + 1, f":{label}", curses.color_pair(8))
            x += len(key) + len(label) + 3

        # Center: audio status indicator
        if self.current_freq > 0:
            # Pulsing indicator when audio active
            indicator = "● "
            self.safe_addstr(
                status_y, x + 2, indicator, curses.color_pair(1) | curses.A_BOLD
            )
            self.safe_addstr(
                status_y, x + 4, f"{self.current_freq:.0f}Hz", curses.color_pair(8)
            )
        else:
            self.safe_addstr(status_y, x + 2, "○ awaiting signal", curses.color_pair(8))

        # Right side: style name with accent
        style_name = getattr(self.style, "STYLE_NAME", "Unknown")
        right_text = f"◈ {style_name}"
        right_x = self.width - len(right_text) - 2
        self.safe_addstr(
            status_y, right_x, right_text, curses.color_pair(3) | curses.A_BOLD
        )

    def check_for_events(self):
        """Poll for events from Shared Memory or Legacy File"""
        event = None
        self.total_reads += 1

        # 1. Try Shared Memory (Fast path)
        if self.shm.is_available():
            event = self.shm.read_event()
            if event:
                self.shm_hits += 1

        # 2. If no SHM event, check Legacy File (Slow path)
        if event is None:
            legacy_event, mtime = read_event_legacy()
            if legacy_event and mtime > self.last_event_time:
                self.last_event_time = mtime
                event = legacy_event

        # Process event if found. The state owns the dispatch + signal math;
        # we keep the counter here since it tracks the IO loop, not the signal.
        if self.state.ingest(event, self.config_model):
            self.total_events += 1

    # These delegate to the signal engine; method names are kept so the
    # main loop calls them unchanged.
    def add_scroll_sample(self):
        """Advance the smoothing/scroll state by one frame (see engine)."""
        self.state.add_scroll_sample(self.config_model)

    def decay_all(self):
        """Decay waveform, spectrum, and RGB state (see engine)."""
        self.state.decay(self.config_model)

    def clear_waveform_area(self):
        """Clear only waveform pixels, restoring grid/background"""
        for i, y in enumerate(self.last_ys):
            if y is not None:
                x = self.graph_x_start + i

                # Check bounds essentially
                if self.waveform_start <= y < self.waveform_end:
                    # Restore background character
                    char, attr = self.get_bg_char(y, x)
                    self.safe_addstr(y, x, char, attr)
                # Clear tracking
                self.last_ys[i] = None

    def clear_spectrum_area(self):
        """Clear spectrum bars area only"""
        if not hasattr(self, "spectrum_end"):
            return

        # Determine clear area based on mode
        if self.design_mode == "SPECTRUM":
            start_x = 0
            width_to_clear = self.width
        else:
            start_x = 15
            width_to_clear = self.spectrum_width - 15

        if width_to_clear <= 0:
            return

        for y in range(self.spectrum_start, self.spectrum_end):
            blank = " " * width_to_clear
            self.safe_addstr(y, start_x, blank, 0)

        # Also clear RGB area (separate because it's on right side)
        # In SPECTRUM mode, rgb_x_start is offscreen, so this clears nothing (safe)
        rgb_clear_width = self.width - self.rgb_x_start - 2
        for y in range(self.rgb_y_start, self.rgb_y_start + 4):  # +4 for 3 bars + label
            if y < self.height:
                self.safe_addstr(y, self.rgb_x_start, " " * rgb_clear_width, 0)

    def switch_style(self):
        """Show the style-selection overlay (logic in ui/overlays.py)."""
        overlays.run_style_picker(self)

    def show_config(self):
        """Show the configuration overlay (logic in ui/overlays.py)."""
        overlays.run_config_menu(self)

    def run(self):
        """Main loop"""
        self.stdscr.clear()
        self.draw_static_elements()
        self.draw_waveform_grid()
        self.stdscr.refresh()

        frame_time = 1.0 / self.TARGET_FPS

        try:
            while True:
                start_time = time.perf_counter()

                # Check for events (updates target_amp/target_freq)
                self.check_for_events()

                # Add one sample per frame for smooth scrolling
                self.add_scroll_sample()

                # Clear dynamic areas only
                self.clear_waveform_area()
                self.clear_spectrum_area()

                # Redraw ONLY dynamic content
                # Redraw frame (dispatches to current design)
                self.draw_frame()

                self.draw_status()
                self.draw_debug_stats()

                self.stdscr.refresh()

                # Measure FPS
                self.frame_count += 1
                now = time.time()
                if now - self.last_fps_time >= 1.0:
                    self.fps = self.frame_count / (now - self.last_fps_time)
                    self.frame_count = 0
                    self.last_fps_time = now

                # Check for quit or style switch
                try:
                    key = self.stdscr.getch()
                    if key == curses.KEY_RESIZE:
                        # Optimization: Check if size actually changed to avoid flicker
                        h, w = self.stdscr.getmaxyx()
                        if h != self.height or w != self.width:
                            self.recalculate_layout()
                            self.stdscr.clear()
                            self.draw_static_elements()
                            self.draw_waveform_grid()
                    elif key == ord("q") or key == ord("Q"):
                        break
                    elif key == ord("s") or key == ord("S"):
                        self.switch_style()
                    elif key == ord("c") or key == ord("C"):
                        self.show_config()
                    elif key == ord("d") or key == ord("D"):
                        # Toggle Design Mode
                        self.design_mode = (
                            "SPECTRUM"
                            if self.design_mode == "OSCILLOSCOPE"
                            else "OSCILLOSCOPE"
                        )
                        self.recalculate_layout()
                        self.stdscr.clear()
                        self.draw_static_elements()
                        if self.design_mode == "OSCILLOSCOPE":
                            self.draw_waveform_grid()
                except Exception:
                    pass

                self.decay_all()

                # Maintain stable FPS
                elapsed = time.perf_counter() - start_time
                sleep_time = max(0, frame_time - elapsed)
                time.sleep(sleep_time)
        finally:
            if hasattr(self, "shm"):
                self.shm.close()


def load_default_style():
    """Fallback to a known safe style (neon_wave or classic_wave)"""
    styles_dir = Path(__file__).parent / "styles"

    # Try neon_wave first (newer, nicer default)
    for default_name in ["neon_wave", "classic_wave"]:
        style_path = styles_dir / f"{default_name}.py"
        if style_path.exists():
            try:
                spec = importlib.util.spec_from_file_location(default_name, style_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            except Exception:
                continue

    print("CRITICAL: No default styles found!")
    sys.exit(1)


def load_style(style_name=None):
    """Load a visualization style"""
    styles_dir = Path(__file__).parent / "styles"

    if not styles_dir.exists():
        print("No styles directory found!")
        sys.exit(1)

    # Get available styles
    available_styles = sorted(
        [f.stem for f in styles_dir.glob("*.py") if f.stem != "__init__"]
    )

    if not available_styles:
        print("No styles found in styles/ directory!")
        sys.exit(1)

    # If no style specified, prompt user
    if style_name is None:
        print("\n" + "=" * 70)
        print(" ⚡ AETHER VISUALIZATION STYLES ⚡".center(70))
        print("=" * 70)
        for idx, style in enumerate(available_styles, 1):
            style_path = styles_dir / f"{style}.py"
            spec = importlib.util.spec_from_file_location(style, style_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            desc = getattr(module, "STYLE_DESCRIPTION", "No description")
            name = getattr(module, "STYLE_NAME", style)
            print(f"  {idx:2d}. {name:20s} - {desc}")
        print("=" * 70)

        choice = input("\nSelect style (number or name): ").strip()

        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(available_styles):
                style_name = available_styles[choice_idx]
        except ValueError:
            style_name = choice

    # Load the style module
    style_path = styles_dir / f"{style_name}.py"
    if not style_path.exists():
        print(f"Style '{style_name}' not found!")
        print(f"Available styles: {', '.join(available_styles)}")
        sys.exit(1)

    try:
        spec = importlib.util.spec_from_file_location(style_name, style_path)
        style_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(style_module)
    except Exception as e:
        print(f"Error loading style '{style_name}': {e}")
        return load_default_style()

    print(f"\n🎨 Loading style: {getattr(style_module, 'STYLE_NAME', style_name)}")
    time.sleep(0.5)

    return style_module


# Global style variable for curses wrapper
_style_module = None


def main(stdscr):
    global _style_module
    scope = UltimateOscilloscope(stdscr, _style_module)
    scope.run()


def cli():
    global _style_module

    style_name = None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("--style="):
            style_name = arg.split("=")[1]
        elif arg in ("-h", "--help"):
            print("Usage: aether.py [style_name|--style=name]")
            print("\nRun without arguments for interactive style selection.")
            sys.exit(0)
        else:
            style_name = arg

    _style_module = load_style(style_name)
    curses.wrapper(main)


if __name__ == "__main__":
    cli()
