#!/usr/bin/env python3
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
    # Static defaults
    TARGET_FPS = 30
    DEBUG_MODE = False
    BURST_WIDTH_RATIO = 0.6
    SPECTRUM_DECAY_LEGACY = 0.8
    
    # Configurable settings with their ranges: (default, min, max, step, name, description)
    CONFIG_SCHEMA = {
        "samples_per_frame": (2, 1, 8, 1, "Scroll Speed", "Animation speed"),
        "waveform_decay": (0.98, 0.90, 0.999, 0.005, "Trail Length", "Trail persistence"),
        "spectrum_decay": (0.92, 0.70, 0.99, 0.02, "Spectrum Decay", "Bar fade speed"),
        "rgb_decay": (0.85, 0.50, 0.95, 0.05, "RGB Decay", "RGB fade speed"),
        "smooth_factor": (0.3, 0.05, 0.8, 0.05, "Smoothing", "Transition smoothness"),
        "intensity": (1.0, 0.5, 2.0, 0.1, "Intensity", "Amplitude boost"),
        "virtual_sample_rate": (500, 200, 1000, 50, "Wave Detail", "Wave resolution"),
    }
    
    # Presets: name -> {setting: value}
    PRESETS = {
        "phosphor": {
            "samples_per_frame": 1,
            "waveform_decay": 0.993,
            "spectrum_decay": 0.96,
            "rgb_decay": 0.91,
            "smooth_factor": 0.45,
            "intensity": 1.0,
            "virtual_sample_rate": 400,
        },
        "edm": {
            "samples_per_frame": 3,
            "waveform_decay": 0.96,
            "spectrum_decay": 0.87,
            "rgb_decay": 0.80,
            "smooth_factor": 0.25,
            "intensity": 1.3,
            "virtual_sample_rate": 600,
        },
        "ambient": {
            "samples_per_frame": 1,
            "waveform_decay": 0.997,
            "spectrum_decay": 0.94,
            "rgb_decay": 0.88,
            "smooth_factor": 0.60,
            "intensity": 0.8,
            "virtual_sample_rate": 350,
        },
        "default": {
            "samples_per_frame": 2,
            "waveform_decay": 0.98,
            "spectrum_decay": 0.92,
            "rgb_decay": 0.85,
            "smooth_factor": 0.3,
            "intensity": 1.0,
            "virtual_sample_rate": 500,
        },
    }

    def __init__(self, stdscr, style_module):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        curses.use_default_colors()

        # Initialize configurable settings from schema
        self._init_config()
        
        # Config menu state
        self.config_keys = list(self.CONFIG_SCHEMA.keys())

        # Enhanced color palette
        # Using 256-color mode if available for richer colors
        if curses.can_change_color() and curses.COLORS >= 256:
            # Custom colors for a more vibrant look
            curses.init_pair(1, 46, -1)   # Bright green (neon)
            curses.init_pair(2, 22, -1)   # Dim green (forest)
            curses.init_pair(3, 51, -1)   # Cyan (electric)
            curses.init_pair(4, 201, -1)  # Magenta (hot pink)
            curses.init_pair(5, 33, -1)   # Blue (deep)
            curses.init_pair(6, 226, -1)  # Yellow (gold)
            curses.init_pair(7, 208, -1)  # Orange (amber)
            curses.init_pair(8, 245, -1)  # Gray (subtle)
            curses.init_pair(9, 196, -1)  # Red (hot)
            curses.init_pair(10, 129, -1) # Purple (violet)
        else:
            # Fallback to basic 8 colors
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_MAGENTA, -1)
            curses.init_pair(5, curses.COLOR_BLUE, -1)
            curses.init_pair(6, curses.COLOR_YELLOW, -1)
            curses.init_pair(7, curses.COLOR_YELLOW, -1)  # Orange fallback
            curses.init_pair(8, curses.COLOR_WHITE, -1)   # Gray fallback
            curses.init_pair(9, curses.COLOR_RED, -1)
            curses.init_pair(10, curses.COLOR_MAGENTA, -1)

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
        self.sample_count = 0
        self.RATE = self.virtual_sample_rate  # Use configurable value

        # Calculate Layout (depends on state above)
        self.recalculate_layout()

        # Draw static elements (depends on layout)
        self.draw_static_elements()

    def _init_config(self):
        """Initialize configurable settings from schema defaults"""
        for key, (default, min_val, max_val, step, name, desc) in self.CONFIG_SCHEMA.items():
            setattr(self, key, default)

    def _get_config_value(self, key):
        """Get current value of a config setting"""
        return getattr(self, key, self.CONFIG_SCHEMA[key][0])

    def _set_config_value(self, key, value):
        """Set a config value, clamping to valid range"""
        schema = self.CONFIG_SCHEMA[key]
        min_val, max_val = schema[1], schema[2]
        clamped = max(min_val, min(max_val, value))
        setattr(self, key, clamped)
        
        # Update derived values if needed
        if key == "virtual_sample_rate":
            self.RATE = clamped

    def _load_preset(self, preset_name):
        """Load a configuration preset"""
        if preset_name in self.PRESETS:
            for key, value in self.PRESETS[preset_name].items():
                self._set_config_value(key, value)
            return True
        return False

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
        self.safe_addstr(1, self.width - len(mode_str) - 2, mode_str, curses.color_pair(6))
        
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
            curses.color_pair(8)
        )
        
        # Fading edges using lighter dash characters
        fade_chars = ["╌", "┄", "┈", "·"]
        for i in range(min(fade_width, len(fade_chars))):
            # Left fade
            self.safe_addstr(
                center_y, 
                self.graph_x_start + i, 
                fade_chars[min(i, len(fade_chars)-1)], 
                curses.color_pair(8)
            )
            # Right fade  
            self.safe_addstr(
                center_y, 
                self.graph_x_end - i - 1, 
                fade_chars[min(i, len(fade_chars)-1)], 
                curses.color_pair(8)
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
        """Draw immersive full-screen spectrum analyzer with gradient bars"""
        # Clear spectrum area
        for y in range(self.spectrum_start, self.spectrum_end):
            self.safe_addstr(y, 0, " " * self.width, 0)

        # Band configuration with colors that create a rainbow gradient
        bands_config = [
            ("SUB", 10),    # Purple
            ("BASS", 4),    # Magenta
            ("LOW", 5),     # Blue
            ("MID", 3),     # Cyan
            ("HIGH", 1),    # Green
            ("TREBLE", 6),  # Yellow
            ("AIR", 7),     # Orange
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
                        self.safe_addstr(y, x_pos, "·" * bar_width, curses.color_pair(8) | curses.A_DIM)

    def draw_spectrum(self):
        """Draw compact spectrum analyzer footer with smooth gradient bars"""
        if self.spectrum_height < 3:
            return

        # Band configuration: name, color pair index
        bands_config = [
            ("SUB", 10),   # Purple for sub-bass
            ("BAS", 4),    # Magenta for bass
            ("LMD", 5),    # Blue for low-mid
            ("MID", 3),    # Cyan for mid
            ("HMD", 1),    # Green for high-mid
            ("TRE", 6),    # Yellow for treble
            ("AIR", 7),    # Orange for sparkle/air
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
                bot_char = "█"
            elif level >= 3:
                top_char = " "
                mid_char = bar_chars[min(8, level)]
                bot_char = "█"
            else:
                top_char = " "
                mid_char = " "
                bot_char = bar_chars[max(1, level * 2)] if level > 0 else "▁"

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
            ("LOW", self.bass_level, 4, 10),    # Magenta/Purple
            ("MID", self.mid_level, 3, 5),      # Cyan/Blue
            ("HI ", self.treble_level, 6, 7),   # Yellow/Orange
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
            self.safe_addstr(status_y, x + 2, indicator, curses.color_pair(1) | curses.A_BOLD)
            self.safe_addstr(status_y, x + 4, f"{self.current_freq:.0f}Hz", curses.color_pair(8))
        else:
            self.safe_addstr(status_y, x + 2, "○ awaiting signal", curses.color_pair(8))

        # Right side: style name with accent
        style_name = getattr(self.style, "STYLE_NAME", "Unknown")
        right_text = f"◈ {style_name}"
        right_x = self.width - len(right_text) - 2
        self.safe_addstr(status_y, right_x, right_text, curses.color_pair(3) | curses.A_BOLD)

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
        # Apply intensity multiplier to target amplitude
        boosted_target = min(1.0, self.target_amp * self.intensity)
        self.smooth_amp += (boosted_target - self.smooth_amp) * self.smooth_factor

        # Smooth interpolation for RGB levels
        self.bass_level += (self.target_bass - self.bass_level) * self.smooth_factor
        self.mid_level += (self.target_mid - self.mid_level) * self.smooth_factor
        self.treble_level += (
            self.target_treble - self.treble_level
        ) * self.smooth_factor

        # Add samples to BOTH halves (they radiate outward from center)
        for _ in range(int(self.samples_per_frame)):
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
        # Apply intensity multiplier for boosted reactivity
        for band, bins in self.BAND_TO_BINS.items():
            value = min(1.0, bands.get(band, 0) * self.intensity)
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
        # Apply intensity multiplier
        intensity = self.intensity
        
        # Bass: sub_bass (Indigo) + bass (Violet) -> Purple/Magenta
        self.target_bass = min(1.0, (bands.get("sub_bass", 0) + bands.get("bass", 0)) / 2 * intensity)

        # Mid: low_mid (Blue) + mid (Cyan) + high_mid (Green) -> Cyan avg
        self.target_mid = min(1.0, (
            bands.get("low_mid", 0) + bands.get("mid", 0) + bands.get("high_mid", 0)
        ) / 3 * intensity)

        # Treble: treble (Yellow) + sparkle (Orange) -> Yellow avg
        self.target_treble = min(1.0, (bands.get("treble", 0) + bands.get("sparkle", 0)) / 2 * intensity)

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
            [v * self.waveform_decay for v in self.waveform_left], maxlen=half_width
        )
        self.waveform_right = deque(
            [v * self.waveform_decay for v in self.waveform_right], maxlen=half_width
        )

        # Decay spectrum
        self.spectrum_values = [v * self.spectrum_decay for v in self.spectrum_values]

        # Decay RGB targets (simulates silence if no new events arrive)
        # We decay targets so the smoothing logic naturally brings levels down
        self.target_bass *= self.rgb_decay
        self.target_mid *= self.rgb_decay
        self.target_treble *= self.rgb_decay

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
        """Show modern style selection overlay"""
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
                        "desc": getattr(module, "STYLE_DESCRIPTION", ""),
                        "module": module,
                    }
                )
            except Exception:
                continue

        # Get current style name for highlighting
        current_style = getattr(self.style, "STYLE_NAME", "")

        # Menu sizing
        max_visible_items = max(5, self.height - 10)
        visible_count = min(len(style_info), max_visible_items)

        menu_width = min(55, self.width - 4)
        menu_height = visible_count + 6  # top + subtitle + divider + items + divider + bottom
        menu_y = max(2, (self.height - menu_height) // 2)
        menu_x = max(2, (self.width - menu_width) // 2)

        scroll_offset = 0
        selected_idx = 0  # Keyboard navigation

        # Find current style in list
        for i, info in enumerate(style_info):
            if info["display"] == current_style:
                selected_idx = i
                if i >= visible_count:
                    scroll_offset = i - visible_count + 1
                break

        self.stdscr.nodelay(False)

        while True:
            # Clear the menu area with spaces (no reverse, just empty)
            for y in range(menu_y, min(menu_y + menu_height, self.height)):
                self.safe_addstr(y, menu_x, " " * menu_width, 0)

            # Draw box border
            # Top
            self.safe_addstr(menu_y, menu_x, "┌" + "─" * (menu_width - 2) + "┐", curses.color_pair(3))
            # Sides
            for y in range(menu_y + 1, menu_y + menu_height - 1):
                self.safe_addstr(y, menu_x, "│", curses.color_pair(8))
                self.safe_addstr(y, menu_x + menu_width - 1, "│", curses.color_pair(8))
            # Bottom
            self.safe_addstr(menu_y + menu_height - 1, menu_x, "└" + "─" * (menu_width - 2) + "┘", curses.color_pair(8))
            
            # Title
            title = " ◈ SELECT STYLE "
            title_x = menu_x + (menu_width - len(title)) // 2
            self.safe_addstr(menu_y, title_x, title, curses.color_pair(3) | curses.A_BOLD)

            # Subtitle line
            subtitle = f"{len(style_info)} styles available"
            self.safe_addstr(menu_y + 1, menu_x + 3, subtitle, curses.color_pair(8))

            # Divider after subtitle
            self.safe_addstr(menu_y + 2, menu_x, "├" + "─" * (menu_width - 2) + "┤", curses.color_pair(8))

            # Scroll indicators (on the divider lines)
            if scroll_offset > 0:
                self.safe_addstr(menu_y + 2, menu_x + menu_width - 3, "▲", curses.color_pair(6) | curses.A_BOLD)
            if scroll_offset + visible_count < len(style_info):
                self.safe_addstr(menu_y + 3 + visible_count, menu_x + menu_width - 3, "▼", curses.color_pair(6) | curses.A_BOLD)

            # List styles
            for i in range(visible_count):
                idx = scroll_offset + i
                if idx >= len(style_info):
                    break

                info = style_info[idx]
                row = menu_y + 3 + i

                # Key label (1-9, then a-z)
                if idx < 9:
                    key_label = str(idx + 1)
                else:
                    key_label = chr(ord("a") + idx - 9)

                is_selected = (idx == selected_idx)
                is_current = (info["display"] == current_style)

                # Clear the row first
                self.safe_addstr(row, menu_x + 1, " " * (menu_width - 2), 0)

                if is_selected:
                    # Selected: cyan arrow and bright text
                    self.safe_addstr(row, menu_x + 2, "▸", curses.color_pair(3) | curses.A_BOLD)
                    self.safe_addstr(row, menu_x + 4, key_label, curses.color_pair(6) | curses.A_BOLD)
                    self.safe_addstr(row, menu_x + 5, ".", curses.color_pair(3))
                    self.safe_addstr(row, menu_x + 7, info["display"][:menu_width - 14], curses.color_pair(3) | curses.A_BOLD)
                else:
                    # Not selected: dimmer
                    self.safe_addstr(row, menu_x + 4, key_label, curses.color_pair(6))
                    self.safe_addstr(row, menu_x + 5, ".", curses.color_pair(8))
                    name_color = curses.color_pair(1) if is_current else curses.color_pair(8)
                    self.safe_addstr(row, menu_x + 7, info["display"][:menu_width - 14], name_color)

                # Current style indicator
                if is_current:
                    self.safe_addstr(row, menu_x + menu_width - 4, "✓", curses.color_pair(1) | curses.A_BOLD)

            # Footer divider and hints
            footer_y = menu_y + 3 + visible_count
            self.safe_addstr(footer_y, menu_x, "├" + "─" * (menu_width - 2) + "┤", curses.color_pair(8))
            
            hints = "↑↓ Navigate  Enter Select  Esc Cancel"
            hint_x = menu_x + (menu_width - len(hints)) // 2
            self.safe_addstr(footer_y + 1, hint_x, hints, curses.color_pair(8))

            self.stdscr.refresh()

            key = self.stdscr.getch()

            if key == 27:  # ESC
                break
            elif key == curses.KEY_UP or key == ord('k'):
                selected_idx = max(0, selected_idx - 1)
                if selected_idx < scroll_offset:
                    scroll_offset = selected_idx
            elif key == curses.KEY_DOWN or key == ord('j'):
                selected_idx = min(len(style_info) - 1, selected_idx + 1)
                if selected_idx >= scroll_offset + visible_count:
                    scroll_offset = selected_idx - visible_count + 1
            elif key == curses.KEY_PPAGE:
                selected_idx = max(0, selected_idx - visible_count)
                scroll_offset = max(0, scroll_offset - visible_count)
            elif key == curses.KEY_NPAGE:
                selected_idx = min(len(style_info) - 1, selected_idx + visible_count)
                scroll_offset = min(len(style_info) - visible_count, scroll_offset + visible_count)
            elif key == 10 or key == curses.KEY_ENTER:  # Enter
                if 0 <= selected_idx < len(style_info):
                    self.style = style_info[selected_idx]["module"]
                    break
            elif ord("1") <= key <= ord("9"):
                choice = key - ord("0") - 1
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break
            elif ord("a") <= key <= ord("z"):
                choice = key - ord("a") + 9
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break
            elif ord("A") <= key <= ord("Z"):
                choice = key - ord("A") + 9
                if 0 <= choice < len(style_info):
                    self.style = style_info[choice]["module"]
                    break

        self.stdscr.nodelay(True)
        self.stdscr.clear()
        self.draw_static_elements()
        self.draw_waveform_grid()

    def show_config(self):
        """Show real-time configuration overlay with presets"""
        selected_idx = 0
        current_preset = None  # Track which preset is active
        
        # Menu sizing - add room for presets
        menu_width = min(58, self.width - 4)
        menu_height = len(self.config_keys) + 8  # Extra rows for presets
        menu_y = max(2, (self.height - menu_height) // 2)
        menu_x = max(2, (self.width - menu_width) // 2)

        self.stdscr.nodelay(False)

        while True:
            # Clear menu area
            for y in range(menu_y, min(menu_y + menu_height, self.height)):
                self.safe_addstr(y, menu_x, " " * menu_width, 0)

            # Draw box
            self.safe_addstr(menu_y, menu_x, "┌" + "─" * (menu_width - 2) + "┐", curses.color_pair(6))
            for y in range(menu_y + 1, menu_y + menu_height - 1):
                self.safe_addstr(y, menu_x, "│", curses.color_pair(8))
                self.safe_addstr(y, menu_x + menu_width - 1, "│", curses.color_pair(8))
            self.safe_addstr(menu_y + menu_height - 1, menu_x, "└" + "─" * (menu_width - 2) + "┘", curses.color_pair(8))

            # Title
            title = " ◈ CONFIGURATION "
            title_x = menu_x + (menu_width - len(title)) // 2
            self.safe_addstr(menu_y, title_x, title, curses.color_pair(6) | curses.A_BOLD)

            # Preset buttons row
            preset_y = menu_y + 1
            self.safe_addstr(preset_y, menu_x + 3, "PRESETS:", curses.color_pair(8))
            
            presets_display = [
                ("1", "Phosphor", "phosphor"),
                ("2", "EDM", "edm"),
                ("3", "Ambient", "ambient"),
                ("0", "Default", "default"),
            ]
            # Add custom preset if it exists
            if "custom" in self.PRESETS:
                presets_display.append(("4", "Custom", "custom"))
            px = menu_x + 12
            for key_char, label, preset_name in presets_display:
                is_active = (current_preset == preset_name)
                self.safe_addstr(preset_y, px, f"[", curses.color_pair(8))
                self.safe_addstr(preset_y, px + 1, key_char, curses.color_pair(6) | curses.A_BOLD)
                self.safe_addstr(preset_y, px + 2, "]", curses.color_pair(8))
                label_attr = curses.color_pair(1) | curses.A_BOLD if is_active else curses.color_pair(8)
                self.safe_addstr(preset_y, px + 3, label, label_attr)
                px += len(label) + 5

            # Divider after presets
            self.safe_addstr(menu_y + 2, menu_x, "├" + "─" * (menu_width - 2) + "┤", curses.color_pair(8))

            # Draw each setting
            for i, cfg_key in enumerate(self.config_keys):
                row = menu_y + 3 + i
                schema = self.CONFIG_SCHEMA[cfg_key]
                default, min_val, max_val, step, name, desc = schema
                current = self._get_config_value(cfg_key)
                
                is_selected = (i == selected_idx)
                
                # Clear row
                self.safe_addstr(row, menu_x + 1, " " * (menu_width - 2), 0)
                
                # Selection indicator
                if is_selected:
                    self.safe_addstr(row, menu_x + 2, "▸", curses.color_pair(6) | curses.A_BOLD)
                    name_attr = curses.color_pair(6) | curses.A_BOLD
                else:
                    name_attr = curses.color_pair(8)
                
                # Setting name (shortened)
                self.safe_addstr(row, menu_x + 4, name[:14], name_attr)
                
                # Value bar visualization
                bar_x = menu_x + 19
                bar_width = 18
                
                # Calculate fill percentage
                value_range = max_val - min_val
                fill_pct = (current - min_val) / value_range if value_range > 0 else 0
                fill_chars = int(fill_pct * bar_width)
                
                # Draw bar background
                self.safe_addstr(row, bar_x, "░" * bar_width, curses.color_pair(8))
                
                # Draw bar fill
                if fill_chars > 0:
                    bar_color = curses.color_pair(1) if is_selected else curses.color_pair(3)
                    self.safe_addstr(row, bar_x, "█" * min(fill_chars, bar_width), bar_color | curses.A_BOLD)
                
                # Value display
                if isinstance(current, float):
                    if current >= 100:
                        val_str = f"{current:.0f}"
                    elif current >= 10:
                        val_str = f"{current:.1f}"
                    else:
                        val_str = f"{current:.2f}"
                else:
                    val_str = str(int(current))
                val_attr = curses.color_pair(3) if is_selected else curses.color_pair(8)
                self.safe_addstr(row, bar_x + bar_width + 1, val_str.rjust(5), val_attr)

            # Footer divider
            footer_y = menu_y + 3 + len(self.config_keys)
            self.safe_addstr(footer_y, menu_x, "├" + "─" * (menu_width - 2) + "┤", curses.color_pair(8))
            
            # Hints
            hints = "↑↓ ←→ Adjust  R Reset  W Save  Esc Close"
            hint_x = menu_x + (menu_width - len(hints)) // 2
            self.safe_addstr(footer_y + 1, hint_x, hints, curses.color_pair(8))

            self.stdscr.refresh()

            # Get input
            input_key = self.stdscr.getch()

            if input_key == 27:  # ESC
                break
            elif input_key == curses.KEY_UP or input_key == ord('k'):
                selected_idx = max(0, selected_idx - 1)
            elif input_key == curses.KEY_DOWN or input_key == ord('j'):
                selected_idx = min(len(self.config_keys) - 1, selected_idx + 1)
            elif input_key == curses.KEY_LEFT or input_key == ord('h'):
                cfg_key = self.config_keys[selected_idx]
                schema = self.CONFIG_SCHEMA[cfg_key]
                step = schema[3]
                current = self._get_config_value(cfg_key)
                self._set_config_value(cfg_key, current - step)
                current_preset = None  # Clear preset indicator
            elif input_key == curses.KEY_RIGHT or input_key == ord('l'):
                cfg_key = self.config_keys[selected_idx]
                schema = self.CONFIG_SCHEMA[cfg_key]
                step = schema[3]
                current = self._get_config_value(cfg_key)
                self._set_config_value(cfg_key, current + step)
                current_preset = None
            elif input_key in (ord('r'), ord('R')):
                # Reset selected setting to default
                cfg_key = self.config_keys[selected_idx]
                default = self.CONFIG_SCHEMA[cfg_key][0]
                self._set_config_value(cfg_key, default)
                current_preset = None
            elif input_key == ord('1'):
                self._load_preset("phosphor")
                current_preset = "phosphor"
            elif input_key == ord('2'):
                self._load_preset("edm")
                current_preset = "edm"
            elif input_key == ord('3'):
                self._load_preset("ambient")
                current_preset = "ambient"
            elif input_key == ord('0'):
                self._load_preset("default")
                current_preset = "default"
            elif input_key == ord('4'):
                # Load custom preset if it exists
                if "custom" in self.PRESETS:
                    self._load_preset("custom")
                    current_preset = "custom"
            elif input_key in (ord('w'), ord('W')):
                # Save current settings as custom preset
                self.PRESETS["custom"] = {
                    key: self._get_config_value(key) 
                    for key in self.config_keys
                }
                current_preset = "custom"

        self.stdscr.nodelay(True)
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
