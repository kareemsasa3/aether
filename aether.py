#!/home/kareem/code/aether/venv/bin/python3
# aether.py - THE FINAL FORM
import curses
import math
import time
import sys
import importlib.util
from pathlib import Path
from collections import deque
from aether_shm import AetherSharedMemory, read_event_legacy


class UltimateOscilloscope:
    WAVEFORM_DECAY = (
        0.98  # 0.98^50 ≈ 0.36, so trails visible for ~50 frames (1.6s at 30fps)
    )
    SPECTRUM_DECAY = 0.92
    RGB_DECAY = 0.85
    TARGET_FPS = 30
    DEBUG_MODE = False  # Enable performance overlay

    # Magic Numbers / Configuration
    BURST_WIDTH_RATIO = 0.6  # Waveform burst takes 60% of screen
    VIRTUAL_SAMPLE_RATE = 500  # For math.sin phase calculation
    SPECTRUM_DECAY_LEGACY = 0.8  # Decay rate for legacy single-freq mode
    SAMPLES_PER_FRAME = 2  # Scroll speed: higher = faster scrolling

    def __init__(self, stdscr, style_module):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        curses.use_default_colors()

        # Colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Bright green
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # Dim green
        curses.init_pair(3, curses.COLOR_CYAN, -1)  # Cyan for spectrum
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)  # Pink for bass
        curses.init_pair(5, curses.COLOR_BLUE, -1)  # Blue for legacy
        curses.init_pair(6, curses.COLOR_YELLOW, -1)  # Yellow for treble

        # State Initialization
        self.design_mode = "OSCILLOSCOPE"  # Options: "OSCILLOSCOPE", "SPECTRUM"

        # Spectrum data (frequency bins)
        self.spectrum_bins = 12  # Musical notes
        self.spectrum_values = [0.0] * self.spectrum_bins
        self.spectrum_freqs = [
            130,
            147,
            165,
            175,
            196,
            220,
            247,
            262,
            330,
            440,
            659,
            880,
        ]

        # Current state (smoothed)
        self.current_freq = 0
        self.current_amp = 0
        self.bass_level = 0.0
        self.mid_level = 0.0
        self.treble_level = 0.0

        # Target state (for smoothing)
        self.target_bass = 0.0
        self.target_mid = 0.0
        self.target_treble = 0.0

        # Event tracking
        self.event_file = "/tmp/aether_last_event.json"
        self.last_event_time = 0

        # Initialize Shared Memory Reader
        self.shm = AetherSharedMemory(is_writer=False)

        # Style module for waveform rendering
        self.style = style_module

        # Smooth Scrolling State
        self.target_freq = 8
        self.target_amp = 0.0
        self.smooth_amp = 0.0
        self.SMOOTH_FACTOR = 0.3
        self.sample_count = 0
        self.RATE = self.VIRTUAL_SAMPLE_RATE

        # Calculate Layout (depends on state above)
        self.recalculate_layout()

        # Draw static elements (depends on layout)
        self.draw_static_elements()

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
            HEADER_LINES = 3  # Title + separator + waveform label

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

        # CENTER-OUT RADIATION: Two deques radiating from center
        half_width = max(5, self.graph_width // 2)

        # Preserve existing data if resizing
        current_left = (
            list(self.waveform_left) if hasattr(self, "waveform_left") else []
        )
        current_right = (
            list(self.waveform_right) if hasattr(self, "waveform_right") else []
        )
        current_age_left = (
            list(self.waveform_age_left) if hasattr(self, "waveform_age_left") else []
        )
        current_age_right = (
            list(self.waveform_age_right) if hasattr(self, "waveform_age_right") else []
        )

        self.waveform_left = deque(current_left, maxlen=half_width)
        self.waveform_right = deque(current_right, maxlen=half_width)
        self.waveform_age_left = deque(current_age_left, maxlen=half_width)
        self.waveform_age_right = deque(current_age_right, maxlen=half_width)

        # Fill with zeros if empty
        while len(self.waveform_left) < half_width:
            self.waveform_left.append(0.0)
            self.waveform_age_left.append(999)  # Very old = invisible
        while len(self.waveform_right) < half_width:
            self.waveform_right.append(0.0)
            self.waveform_age_right.append(999)

        self.last_ys = [None] * self.graph_width

        # Performance Monitoring
        self.shm_hits = 0
        self.total_reads = 0
        self.total_events = 0
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()

    def get_bg_char(self, y, x):
        """Get the background character for a given coordinate"""
        center_y = self.waveform_start + (self.waveform_height // 2)

        # Center Line Only
        if y == center_y:
            return "─", curses.color_pair(2)  # Dim green

        return " ", 0

    def safe_addstr(self, y, x, text, attr=0):
        try:
            if 0 <= y < self.height and 0 <= x < self.width:
                text = str(text)[: self.width - x - 1]
                self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def draw_static_elements(self):
        """Draw static UI elements once"""
        # Title bar (centered)
        title = "  ░▒▓ K E Y B E A T S ▓▒░   [ULTIMATE MODE]  "
        self.safe_addstr(
            0,
            (self.width - len(title)) // 2,
            title,
            curses.color_pair(1) | curses.A_BOLD,
        )

        self.safe_addstr(1, 0, "═" * self.width, curses.color_pair(1))

        if self.design_mode == "OSCILLOSCOPE":
            # Waveform section label
            self.safe_addstr(
                self.waveform_start - 1,
                5,
                "WAVEFORM (Time Domain)",
                curses.color_pair(1) | curses.A_BOLD,
            )

            # Bottom panel separator
            self.safe_addstr(
                self.bottom_panel_start - 1,
                0,
                "─" * self.width,
                curses.color_pair(2),
            )

            # Spectrum label (bottom left)
            self.safe_addstr(
                self.spectrum_start,
                5,
                "SPECTRUM",
                curses.color_pair(3) | curses.A_BOLD,
            )

            # RGB label (bottom right area)
            self.safe_addstr(
                self.rgb_y_start,
                self.rgb_x_start,
                "RGB SYNC",
                curses.color_pair(1) | curses.A_BOLD,
            )
        elif self.design_mode == "SPECTRUM":
            self.safe_addstr(
                self.spectrum_start - 1,
                5,
                "FULL SPECTRUM ANALYZER",
                curses.color_pair(3) | curses.A_BOLD,
            )

    def draw_waveform_grid(self):
        """Draw minimal center line only"""
        center_y = self.waveform_start + (self.waveform_height // 2)

        # Dim center line
        self.safe_addstr(
            center_y, self.graph_x_start, "─" * (self.graph_width), curses.color_pair(2)
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

                result = self.style.render_waveform(
                    i, amp, age, self.graph_width // 2, colors
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

                result = self.style.render_waveform(
                    i, amp, age, self.graph_width // 2, colors
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
        """Draw massive full-screen spectrum bars"""
        # Clear entire spectrum area first
        for y in range(self.spectrum_start, self.spectrum_end):
            self.safe_addstr(y, 0, " " * self.width, 0)

        # Band names and mapping (same as footer but bigger)
        bands = ["SUB BASS", "BASS", "LOW MID", "MID", "HIGH MID", "TREBLE", "SPARKLE"]

        band_values = [
            self.spectrum_values[0],  # sub_bass
            max(self.spectrum_values[1:3]),  # bass
            max(self.spectrum_values[3:5]),  # low_mid
            max(self.spectrum_values[5:8]),  # mid
            max(self.spectrum_values[8:10]),  # high_mid
            self.spectrum_values[10],  # treble
            self.spectrum_values[11],  # sparkle
        ]

        # Calculate Layout
        num_bands = len(bands)
        # Margins
        margin_x = 4
        total_width = self.width - (2 * margin_x)
        bar_width = (total_width // num_bands) - 2  # -2 for spacing
        bar_max_height = self.spectrum_height - 4  # -4 for labels/header

        start_y = self.spectrum_end - 2  # Bottom up

        for i, (name, value) in enumerate(zip(bands, band_values)):
            x_pos = margin_x + (i * (bar_width + 2))

            # Color based on frequency
            if i < 2:
                color = curses.color_pair(4)  # Bass
            elif i < 5:
                color = curses.color_pair(3)  # Mid
            else:
                color = curses.color_pair(6)  # Treble

            # Draw Label (bottom)
            label = name[:bar_width].center(bar_width)
            self.safe_addstr(start_y + 1, x_pos, label, color)

            # Draw Bar
            bar_height = int(value * bar_max_height)
            bar_height = max(0, min(bar_height, bar_max_height))

            # Draw blocks from bottom up
            # Using block characters for smoother look
            # █ (full), ▆ (3/4), ▄ (1/2), ▂ (1/4)

            for h in range(bar_max_height):
                y = start_y - h
                if h < bar_height:
                    # Determine block char based on position in height
                    # Simple full block for now
                    self.safe_addstr(y, x_pos, "█" * bar_width, color | curses.A_BOLD)
                else:
                    # Peak hold or empty? Just empty for now, maybe phantom top
                    pass

    def draw_spectrum(self):
        """Draw compact spectrum analyzer footer (7 bands in 3 lines)"""
        # Add bounds check
        if self.spectrum_height < 3:
            return  # Not enough room to draw 3-line meters

        # Band names for display
        bands = ["SUB", "BASS", "LMID", "MID", "HMID", "TRE", "SPK"]

        # Map spectrum_values (12 bins) back to 7 bands for display
        band_values = [
            self.spectrum_values[0],  # sub_bass
            max(self.spectrum_values[1:3]),  # bass
            max(self.spectrum_values[3:5]),  # low_mid
            max(self.spectrum_values[5:8]),  # mid
            max(self.spectrum_values[8:10]),  # high_mid
            self.spectrum_values[10],  # treble
            self.spectrum_values[11],  # sparkle
        ]

        # Calculate spacing based on spectrum width (left 60%)
        # Start X is 15 (after "SPECTRUM" label)
        # Available width is spectrum_width - 15 - margin
        start_x = 15
        available_width = self.spectrum_width - start_x - 5
        band_spacing = max(4, available_width // len(bands))  # Minimum spacing of 4

        for i, (name, value) in enumerate(zip(bands, band_values)):
            x = start_x + (i * band_spacing)

            # 3-line mini meter: ▂▄▆█ based on value
            meter_chars = [" ", "▂", "▄", "▆", "█"]
            level = int(value * 4)  # 0-4
            level = max(0, min(4, level))

            # Draw meter (3 lines: top=high, mid, bottom=low)
            # Top line (shows at high levels)
            top_char = meter_chars[max(0, level - 2)] if level > 2 else " "
            # Mid line
            mid_char = meter_chars[max(0, min(4, level))] if level > 0 else "▂"

            # Color based on band
            if i < 2:  # Bass = magenta
                color = curses.color_pair(4)
            elif i < 5:  # Mid = cyan
                color = curses.color_pair(3)
            else:  # Treble = yellow
                color = curses.color_pair(6)

            # Draw the mini meter
            self.safe_addstr(self.spectrum_start, x, top_char, color | curses.A_BOLD)
            self.safe_addstr(
                self.spectrum_start + 1, x, mid_char, color | curses.A_BOLD
            )
            self.safe_addstr(self.spectrum_start + 2, x, name[:3], curses.color_pair(2))

    def draw_rgb_preview(self):
        """Draw RGB sync preview as horizontal bars in bottom right panel"""
        x = self.rgb_x_start
        max_bar_width = self.width - x - 5  # Leave margin on right

        # Draw horizontal bars for each channel (3 rows)
        channels = [
            ("BASS", self.bass_level, curses.color_pair(4)),  # Magenta
            ("MID ", self.mid_level, curses.color_pair(3)),  # Cyan
            ("TRE ", self.treble_level, curses.color_pair(6)),  # Yellow
        ]

        for i, (label, level, color) in enumerate(channels):
            y = self.rgb_y_start + 1 + i  # +1 to skip the label row

            # Draw label
            self.safe_addstr(y, x, label, color | curses.A_BOLD)

            # Draw horizontal bar
            bar_length = int(level * max_bar_width)
            if bar_length > 0:
                bar = "█" * min(bar_length, max_bar_width)
                self.safe_addstr(y, x + 5, bar, color | curses.A_BOLD)

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
        """Draw status bar with style indicator on right"""
        status_y = self.height - 1

        # Left side: controls and freq
        if self.current_freq > 0:
            left_status = (
                f" S: Style │ D: Design │ Q: Quit │ FREQ: {self.current_freq:.0f}Hz"
            )
        else:
            left_status = " S: Style │ D: Design │ Q: Quit │ Waiting for audio..."

        # Right side: current style + design
        style_name = getattr(self.style, "STYLE_NAME", "Unknown")
        design_label = self.design_mode
        right_status = f"[ {design_label} ] [ {style_name} ] "

        # Draw left-aligned status
        self.safe_addstr(status_y, 0, left_status, curses.color_pair(1))

        # Draw right-aligned style indicator
        right_x = self.width - len(right_status) - 1
        self.safe_addstr(
            status_y, right_x, right_status, curses.color_pair(3) | curses.A_BOLD
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

        # Process event if found
        if event and event.get("type") in ["key_press", "audio"]:
            self.total_events += 1
            # Handle both new multi-band format and legacy single-frequency
            if "bands" in event:
                # New multi-band format from audio daemon
                self.add_wave_from_bands(event["bands"])
                self.update_spectrum_from_bands(event["bands"])
                self.update_rgb_levels_from_bands(event["bands"])
            else:
                # Legacy single-frequency format (keyboard mode)
                self.add_wave(event["frequency"], event.get("amplitude", 0.8))
                self.update_spectrum(event["frequency"], event.get("amplitude", 0.8))
                self.update_rgb_levels(event["frequency"], event.get("amplitude", 0.8))

    def add_wave(self, frequency, amplitude=0.8):
        """Store targets for legacy single-frequency mode (keyboard events)"""
        # Map legacy frequency to visual frequency (avoid aliasing)
        # Use log scale to compress 130-880 Hz range to 2-20 Hz visual range
        visual_freq = max(2, min(20, int(frequency / 50)))
        self.target_freq = visual_freq
        self.target_amp = amplitude

    def update_spectrum(self, frequency, amplitude):
        """Update spectrum analyzer"""
        # Find closest frequency bin
        closest_idx = min(
            range(len(self.spectrum_freqs)),
            key=lambda i: abs(self.spectrum_freqs[i] - frequency),
        )

        # Set that bin to full, others decay
        for i in range(len(self.spectrum_values)):
            if i == closest_idx:
                self.spectrum_values[i] = amplitude
            else:
                self.spectrum_values[i] *= self.SPECTRUM_DECAY_LEGACY  # Decay

    def update_rgb_levels(self, frequency, amplitude):
        """Update RGB preview targets (legacy single-frequency mode)"""
        # Bass (low frequencies)
        if 130 <= frequency <= 250:
            self.target_bass = amplitude
        else:
            self.target_bass = 0.0

        # Treble (high frequencies)
        if 600 <= frequency <= 1100:
            self.target_treble = amplitude
        else:
            self.target_treble = 0.0

        # Mid (everything else)
        if 250 < frequency < 600:
            self.target_mid = amplitude
        else:
            self.target_mid = 0.0

    # ========== NEW MULTI-BAND METHODS ==========

    # VISUAL frequency mapping for waveform display (NOT actual audio frequencies!)
    # These are chosen to look good on screen: 2-20Hz gives 25-250 samples/cycle
    # at VIRTUAL_SAMPLE_RATE=500, resulting in smooth visible waves.
    # Higher bands get slightly higher visual freq for character differentiation.
    BAND_FREQS = {
        "sub_bass": 2,  # Slow, rolling waves
        "bass": 4,  # Medium-slow waves
        "low_mid": 6,  # Medium waves
        "mid": 8,  # Medium waves
        "high_mid": 12,  # Faster waves
        "treble": 16,  # Fast waves
        "sparkle": 20,  # Fastest waves
    }

    # Map bands to spectrum display bins
    BAND_TO_BINS = {
        "sub_bass": [0],
        "bass": [1, 2],
        "low_mid": [3, 4],
        "mid": [5, 6, 7],
        "high_mid": [8, 9],
        "treble": [10],
        "sparkle": [11],
    }

    def add_wave_from_bands(self, bands):
        """Store target amplitude/frequency from audio event (smooth mode)"""
        # Find dominant band (highest energy, excluding 'total')
        dominant_band = max(
            ((k, v) for k, v in bands.items() if k != "total"), key=lambda x: x[1]
        )
        band_name, amplitude = dominant_band

        # Store targets - actual sample generation happens in add_scroll_sample()
        self.target_freq = self.BAND_FREQS.get(band_name, 8)
        self.target_freq = max(2, min(20, self.target_freq))
        self.target_amp = max(0.0, min(1.0, amplitude))

    def add_scroll_sample(self):
        """Add samples to center, radiating outward in both directions.

        Called once per frame in the main loop for fluid animation.
        Adds SAMPLES_PER_FRAME samples to both left and right halves.
        """
        # Smooth interpolation toward target amplitude
        self.smooth_amp += (self.target_amp - self.smooth_amp) * self.SMOOTH_FACTOR

        # Smooth interpolation for RGB levels
        self.bass_level += (self.target_bass - self.bass_level) * self.SMOOTH_FACTOR
        self.mid_level += (self.target_mid - self.mid_level) * self.SMOOTH_FACTOR
        self.treble_level += (
            self.target_treble - self.treble_level
        ) * self.SMOOTH_FACTOR

        # Add samples to BOTH halves (they radiate outward from center)
        for _ in range(self.SAMPLES_PER_FRAME):
            phase = 2 * math.pi * self.target_freq * self.sample_count / self.RATE
            sample = self.smooth_amp * math.sin(phase)

            # Push new samples to front of both deques (index 0 = center)
            # Old samples are pushed outward toward edges
            self.waveform_left.appendleft(sample)
            self.waveform_age_left.appendleft(0)
            self.waveform_right.appendleft(sample)
            self.waveform_age_right.appendleft(0)

            self.sample_count += 1

        # Update display state
        self.current_freq = self.target_freq
        self.current_amp = self.smooth_amp

    def update_spectrum_from_bands(self, bands):
        """Update spectrum analyzer with actual frequency bands.

        Maps 7 audio bands to 12 spectrum display bins for accurate visualization.
        """
        # Map audio bands to spectrum bins (12 bins, 7 bands)
        for band, bins in self.BAND_TO_BINS.items():
            value = bands.get(band, 0)
            for bin_idx in bins:
                self.spectrum_values[bin_idx] = value

        # Update current frequency display (use dominant band)
        dominant = max(
            ((k, v) for k, v in bands.items() if k != "total"), key=lambda x: x[1]
        )
        self.current_freq = self.BAND_FREQS.get(dominant[0], 440)
        self.current_amp = dominant[1]

    def update_rgb_levels_from_bands(self, bands):
        """Update RGB preview targets from frequency bands"""
        # Bass: sub_bass (Indigo) + bass (Violet) -> Purple/Magenta
        self.target_bass = (bands.get("sub_bass", 0) + bands.get("bass", 0)) / 2

        # Mid: low_mid (Blue) + mid (Cyan) + high_mid (Green) -> Cyan avg
        self.target_mid = (
            bands.get("low_mid", 0) + bands.get("mid", 0) + bands.get("high_mid", 0)
        ) / 3

        # Treble: treble (Yellow) + sparkle (Orange) -> Yellow avg
        self.target_treble = (bands.get("treble", 0) + bands.get("sparkle", 0)) / 2

    def decay_all(self):
        """Decay waveform and age samples in both halves"""
        half_width = max(5, self.graph_width // 2)

        # Age all samples in both halves
        self.waveform_age_left = deque(
            [age + 1 for age in self.waveform_age_left], maxlen=half_width
        )
        self.waveform_age_right = deque(
            [age + 1 for age in self.waveform_age_right], maxlen=half_width
        )

        # Decay waveform amplitudes in both halves
        self.waveform_left = deque(
            [v * self.WAVEFORM_DECAY for v in self.waveform_left], maxlen=half_width
        )
        self.waveform_right = deque(
            [v * self.WAVEFORM_DECAY for v in self.waveform_right], maxlen=half_width
        )

        # Decay spectrum
        self.spectrum_values = [v * self.SPECTRUM_DECAY for v in self.spectrum_values]

        # Decay RGB targets (simulates silence if no new events arrive)
        # We decay targets so the smoothing logic naturally brings levels down
        self.target_bass *= self.RGB_DECAY
        self.target_mid *= self.RGB_DECAY
        self.target_treble *= self.RGB_DECAY

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
        """Show style selection overlay menu"""
        styles_dir = Path(__file__).parent / "styles"
        available_styles = sorted(
            [f.stem for f in styles_dir.glob("*.py") if f.stem != "__init__"]
        )

        # Load style metadata
        style_info = []
        for style_name in available_styles:
            style_path = styles_dir / f"{style_name}.py"
            try:
                spec = importlib.util.spec_from_file_location(style_name, style_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                style_info.append(
                    {
                        "name": style_name,
                        "display": getattr(module, "STYLE_NAME", style_name),
                        "module": module,
                    }
                )
            except Exception:
                # Skip broken styles in the menu
                continue

        # Dynamic sizing for scrollable menu
        max_visible_items = max(5, self.height - 10)
        visible_count = min(len(style_info), max_visible_items)

        menu_width = 50
        menu_height = visible_count + 6  # Title + Divider + Padding + Footer
        menu_y = max(2, (self.height - menu_height) // 2)
        menu_x = max(2, (self.width - menu_width) // 2)

        scroll_offset = 0

        # Wait for input (blocking mode)
        self.stdscr.nodelay(False)

        while True:
            # Draw menu box background
            for y in range(menu_y, min(menu_y + menu_height, self.height)):
                self.safe_addstr(
                    y, menu_x, " " * menu_width, curses.color_pair(1) | curses.A_REVERSE
                )

            # Title
            title = "⚡ SELECT VISUALIZATION STYLE ⚡"
            self.safe_addstr(
                menu_y + 1,
                menu_x + (menu_width - len(title)) // 2,
                title,
                curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE,
            )

            # Divider
            self.safe_addstr(
                menu_y + 2,
                menu_x + 2,
                "─" * (menu_width - 4),
                curses.color_pair(1) | curses.A_REVERSE,
            )

            # Scroll Indicators
            if scroll_offset > 0:
                self.safe_addstr(
                    menu_y + 2,
                    menu_width - 3,
                    "▲",
                    curses.color_pair(1) | curses.A_REVERSE,
                )

            if scroll_offset + visible_count < len(style_info):
                self.safe_addstr(
                    menu_y + menu_height - 2,
                    menu_width - 3,
                    "▼",
                    curses.color_pair(1) | curses.A_REVERSE,
                )

            # List visible styles
            for i in range(visible_count):
                idx = scroll_offset + i
                if idx >= len(style_info):
                    break

                info = style_info[idx]

                # Use letters for 10+ (a=10, b=11, etc.)
                if idx < 9:
                    key_label = str(idx + 1)
                else:
                    key_label = chr(ord("a") + idx - 9)  # a, b, c...

                label = f" {key_label}. {info['display']}"
                row = menu_y + 3 + i

                self.safe_addstr(
                    row,
                    menu_x + 2,
                    label[: menu_width - 4],
                    curses.color_pair(1) | curses.A_REVERSE,
                )

            # Footer
            footer = "ESC: Cancel | ▲/▼: Scroll"
            self.safe_addstr(
                menu_y + menu_height - 2,
                menu_x + (menu_width - len(footer)) // 2,
                footer,
                curses.color_pair(2) | curses.A_REVERSE,
            )

            self.stdscr.refresh()

            key = self.stdscr.getch()

            if key == 27:  # ESC
                break
            elif key == curses.KEY_UP:
                scroll_offset = max(0, scroll_offset - 1)
            elif key == curses.KEY_DOWN:
                scroll_offset = max(
                    0, min(len(style_info) - visible_count, scroll_offset + 1)
                )
            elif key == curses.KEY_PPAGE:  # Page Up
                scroll_offset = max(0, scroll_offset - visible_count)
            elif key == curses.KEY_NPAGE:  # Page Down
                scroll_offset = max(
                    0,
                    min(len(style_info) - visible_count, scroll_offset + visible_count),
                )
            elif ord("1") <= key <= ord("9"):
                # Number keys 1-9
                choice = key - ord("0") - 1
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break
            elif ord("a") <= key <= ord("z"):  # Supported range a-z
                # Letter keys a-z for 10-35
                choice = key - ord("a") + 9
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break
            elif ord("A") <= key <= ord("Z"):
                # Uppercase letter keys
                choice = key - ord("A") + 9
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break

        # Restore non-blocking mode
        self.stdscr.nodelay(True)

        # Redraw everything
        self.stdscr.clear()
        self.draw_static_elements()
        self.draw_waveform_grid()

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
    """Fallback to a known safe style (classic_wave)"""
    print("⚠️ Falling back to default style 'classic_wave'...")
    styles_dir = Path(__file__).parent / "styles"
    style_path = styles_dir / "classic_wave.py"

    if not style_path.exists():
        print("CRITICAL: Default style 'classic_wave.py' not found!")
        sys.exit(1)

    try:
        spec = importlib.util.spec_from_file_location("classic_wave", style_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"CRITICAL: Error loading default style: {e}")
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
