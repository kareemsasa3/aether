"""Signal-processing state for the Aether visualizer.

Phase 4a of the TUI refactor (see REFACTOR.md): the pure ingestion / decay /
smoothing logic — the waveform deques, spectrum bars, RGB levels, and the
scalars driving them — moves out of `UltimateOscilloscope` into
`VisualizerState`.

This object is deliberately dependency-light:
- no curses, no stdscr, no shared memory,
- no terminal geometry (it learns only its buffer length via `resize`),
- it reads tuning values from a VizConfig-like object passed in per call.

That makes the whole signal pipeline unit-testable headless. Geometry, the
`last_ys` render scratch buffer, the performance counters, the SHM reader, and
the event loop stay on `UltimateOscilloscope` (see the Phase 4 audit).
"""

import math
import time
from collections import deque


class VisualizerState:
    """Owns the visualizer's dynamic signal state and the math that updates it.

    Current values are plain attributes so the oscilloscope can expose them to
    its draw methods via read-only properties without any draw-method changes.
    """

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

    # Legacy single-frequency spectrum decay (non-selected bins fade)
    SPECTRUM_DECAY_LEGACY = 0.8

    # Keep the last audio amplitude across the gap between daemon publications,
    # then release it after the same 100 ms silence grace used by the RGB
    # consumer. The engine owns this constant so its timing remains headless
    # and independent of device-specific RGB configuration.
    AUDIO_EVENT_GRACE_SECONDS = 0.1

    def __init__(self, spectrum_bins=12, clock=None):
        # Monotonic time avoids wall-clock adjustments changing event age. Tests
        # inject a deterministic clock so freshness transitions require no sleep.
        self._clock = clock if clock is not None else time.monotonic
        self._last_audio_event_time = None

        # Spectrum data (frequency bins)
        self.spectrum_bins = spectrum_bins
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

        # Smooth Scrolling State
        self.target_freq = 8
        self.target_amp = 0.0
        self.smooth_amp = 0.0
        self.sample_count = 0

        # Beat / quiet envelope for frame styles. beat_pulse snaps to 1.0 on
        # a bass onset and decays every frame; silence_frames counts
        # consecutive near-silent frames so styles can switch to ambient
        # "resting" visuals instead of going blank.
        self.beat_pulse = 0.0
        self.silence_frames = 0
        self._bass_baseline = 0.0

        # Waveform buffers (sized on resize). Empty until the caller resizes to
        # the current terminal geometry.
        self.waveform_left = deque(maxlen=0)
        self.waveform_right = deque(maxlen=0)
        self.waveform_age_left = deque(maxlen=0)
        self.waveform_age_right = deque(maxlen=0)

    def resize(self, half_width):
        """Resize the waveform deques to `half_width`, preserving existing data.

        Mirrors the buffer logic formerly in recalculate_layout: keep current
        samples, pad missing slots with 0.0 amplitude and age 999 (very old =
        invisible). The state never sees terminal height/width — only the
        already-computed half width.
        """
        current_left = list(self.waveform_left)
        current_right = list(self.waveform_right)
        current_age_left = list(self.waveform_age_left)
        current_age_right = list(self.waveform_age_right)

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

    # ========== INGESTION ==========

    def ingest(self, event, config):
        """Update state from an audio/key event. Returns True if consumed.

        Handles both the new multi-band format and the legacy single-frequency
        format. The caller owns the SHM read, counters, and event filtering;
        this only mutates signal state.
        """
        if not (event and event.get("type") in ["key_press", "audio"]):
            return False

        if "bands" in event:
            # New multi-band format from audio daemon
            self.add_wave_from_bands(event["bands"])
            self.update_spectrum_from_bands(event["bands"], config)
            self.update_rgb_levels_from_bands(event["bands"], config)
        else:
            # Legacy single-frequency format (keyboard mode)
            self.add_wave(event["frequency"], event.get("amplitude", 0.8))
            self.update_spectrum(event["frequency"], event.get("amplitude", 0.8))
            self.update_rgb_levels(event["frequency"], event.get("amplitude", 0.8))

        if event.get("type") == "audio":
            self._last_audio_event_time = self._clock()
        else:
            # A legacy key event now owns the target; an older audio timestamp
            # must not expire the newly supplied non-audio amplitude.
            self._last_audio_event_time = None
        return True

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

    # ========== MULTI-BAND METHODS ==========

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

    def add_scroll_sample(self, config):
        """Add samples to center, radiating outward in both directions.

        Called once per frame in the main loop for fluid animation.
        Adds SAMPLES_PER_FRAME samples to both left and right halves.
        """
        # Preserve the latest daemon amplitude across normal publication gaps,
        # but release a stale audio target so smoothing and silence accounting
        # can carry the visualizer into its quiet state. Deliberately leave
        # smooth_amp untouched here; the existing interpolation decays it.
        if (
            self._last_audio_event_time is not None
            and self._clock() - self._last_audio_event_time
            >= self.AUDIO_EVENT_GRACE_SECONDS
        ):
            self.target_amp = 0.0
            self._last_audio_event_time = None

        # Smooth interpolation toward target amplitude
        # Apply intensity multiplier to target amplitude
        boosted_target = min(1.0, self.target_amp * config.intensity)
        self.smooth_amp += (boosted_target - self.smooth_amp) * config.smooth_factor

        # Smooth interpolation for RGB levels
        self.bass_level += (self.target_bass - self.bass_level) * config.smooth_factor
        self.mid_level += (self.target_mid - self.mid_level) * config.smooth_factor
        self.treble_level += (
            self.target_treble - self.treble_level
        ) * config.smooth_factor

        # Beat detection: an onset is target_bass jumping well above its own
        # slow-moving baseline. The beat_pulse < 0.25 guard is a refractory
        # window so a sustained bass note reads as one hit, not a strobe.
        if (
            self.target_bass > 0.15
            and self.target_bass > self._bass_baseline * 1.35
            and self.beat_pulse < 0.25
        ):
            self.beat_pulse = 1.0
        else:
            self.beat_pulse *= 0.85
        self._bass_baseline += (self.target_bass - self._bass_baseline) * 0.08

        if self.smooth_amp < 0.04 and self.target_amp < 0.04:
            self.silence_frames += 1
        else:
            self.silence_frames = 0

        # Add samples to BOTH halves (they radiate outward from center)
        for _ in range(int(config.samples_per_frame)):
            phase = 2 * math.pi * self.target_freq * self.sample_count / config.RATE
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

    def update_spectrum_from_bands(self, bands, config):
        """Update spectrum analyzer with actual frequency bands.

        Maps 7 audio bands to 12 spectrum display bins for accurate visualization.
        """
        # Map audio bands to spectrum bins (12 bins, 7 bands)
        # Apply intensity multiplier for boosted reactivity
        for band, bins in self.BAND_TO_BINS.items():
            value = min(1.0, bands.get(band, 0) * config.intensity)
            for bin_idx in bins:
                self.spectrum_values[bin_idx] = value

        # Update current frequency display (use dominant band)
        dominant = max(
            ((k, v) for k, v in bands.items() if k != "total"), key=lambda x: x[1]
        )
        self.current_freq = self.BAND_FREQS.get(dominant[0], 440)
        self.current_amp = dominant[1]

    def update_rgb_levels_from_bands(self, bands, config):
        """Update RGB preview targets from frequency bands"""
        # Apply intensity multiplier
        intensity = config.intensity

        # Bass: sub_bass (Indigo) + bass (Violet) -> Purple/Magenta
        self.target_bass = min(
            1.0, (bands.get("sub_bass", 0) + bands.get("bass", 0)) / 2 * intensity
        )

        # Mid: low_mid (Blue) + mid (Cyan) + high_mid (Green) -> Cyan avg
        self.target_mid = min(
            1.0,
            (bands.get("low_mid", 0) + bands.get("mid", 0) + bands.get("high_mid", 0))
            / 3
            * intensity,
        )

        # Treble: treble (Yellow) + sparkle (Orange) -> Yellow avg
        self.target_treble = min(
            1.0, (bands.get("treble", 0) + bands.get("sparkle", 0)) / 2 * intensity
        )

    # ========== DECAY ==========

    def decay(self, config):
        """Decay waveform and age samples in both halves.

        Reuses each deque's existing maxlen (set by `resize` from the current
        geometry), so the state needs no terminal dimensions of its own. This
        matches the former decay_all, which recomputed the same half width from
        graph_width that resize is kept in sync with.
        """
        hw_left = self.waveform_left.maxlen
        hw_right = self.waveform_right.maxlen

        # Age all samples in both halves
        self.waveform_age_left = deque(
            [age + 1 for age in self.waveform_age_left], maxlen=hw_left
        )
        self.waveform_age_right = deque(
            [age + 1 for age in self.waveform_age_right], maxlen=hw_right
        )

        # Decay waveform amplitudes in both halves
        self.waveform_left = deque(
            [v * config.waveform_decay for v in self.waveform_left], maxlen=hw_left
        )
        self.waveform_right = deque(
            [v * config.waveform_decay for v in self.waveform_right], maxlen=hw_right
        )

        # Decay spectrum
        self.spectrum_values = [v * config.spectrum_decay for v in self.spectrum_values]

        # Decay RGB targets (simulates silence if no new events arrive)
        # We decay targets so the smoothing logic naturally brings levels down
        self.target_bass *= config.rgb_decay
        self.target_mid *= config.rgb_decay
        self.target_treble *= config.rgb_decay
