#!/usr/bin/env python3
"""Unit tests for engine.VisualizerState.

Phase 4a of the TUI refactor moved the visualizer's signal pipeline — waveform
buffers, spectrum bars, RGB levels, and the smoothing scalars — out of
`UltimateOscilloscope` into `VisualizerState`. These tests pin that behavior:

  - default initialization
  - resize() grow/shrink, value/age padding (amp 0.0, age 999)
  - legacy update_spectrum (closest bin set, others decay)
  - banded update_spectrum_from_bands (band->bins mapping, intensity clamp)
  - RGB level math + clamping
  - legacy vs banded event dispatch via ingest()
  - add_scroll_sample smoothing + sample-count + fresh-sample insertion
  - decay() for spectrum, waveform, ages, and RGB targets

All headless: no curses, no stdscr, no shared memory. A tiny config stand-in
supplies the tuning values the engine reads from a VizConfig.

Run directly (`python3 test_engine.py`) or via pytest.
"""
import os
import sys
from collections import deque

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import VisualizerState  # noqa: E402


class _Config:
    """Minimal VizConfig stand-in with controllable tuning values."""

    def __init__(self, **kw):
        self.intensity = 1.0
        self.smooth_factor = 0.5
        self.samples_per_frame = 2
        self.RATE = 500
        self.waveform_decay = 0.9
        self.spectrum_decay = 0.5
        self.rgb_decay = 0.8
        for k, v in kw.items():
            setattr(self, k, v)


def test_default_initialization():
    s = VisualizerState()
    assert s.spectrum_bins == 12
    assert s.spectrum_values == [0.0] * 12
    assert len(s.spectrum_freqs) == 12
    assert s.bass_level == s.mid_level == s.treble_level == 0.0
    assert s.target_bass == s.target_mid == s.target_treble == 0.0
    assert s.target_freq == 8
    assert s.target_amp == 0.0
    assert s.smooth_amp == 0.0
    assert s.sample_count == 0
    # Buffers empty until resized.
    assert len(s.waveform_left) == 0
    assert len(s.waveform_right) == 0


def test_resize_from_empty_pads_values_and_ages():
    s = VisualizerState()
    s.resize(4)
    for buf in (s.waveform_left, s.waveform_right):
        assert list(buf) == [0.0, 0.0, 0.0, 0.0]
    for ages in (s.waveform_age_left, s.waveform_age_right):
        assert list(ages) == [999, 999, 999, 999]  # very old = invisible


def test_resize_grow_preserves_and_pads():
    s = VisualizerState()
    s.resize(3)
    s.waveform_left = deque([1.0, 2.0, 3.0], maxlen=3)
    s.waveform_age_left = deque([0, 1, 2], maxlen=3)

    s.resize(5)
    assert list(s.waveform_left) == [1.0, 2.0, 3.0, 0.0, 0.0]
    assert list(s.waveform_age_left) == [0, 1, 2, 999, 999]
    assert s.waveform_left.maxlen == 5


def test_resize_shrink_keeps_most_recent():
    s = VisualizerState()
    s.resize(4)
    s.waveform_left = deque([1.0, 2.0, 3.0, 4.0], maxlen=4)
    s.resize(2)
    # deque truncates from the left when re-created with a smaller maxlen.
    assert list(s.waveform_left) == [3.0, 4.0]
    assert s.waveform_left.maxlen == 2


def test_update_spectrum_legacy_sets_closest_and_decays_others():
    s = VisualizerState()
    s.spectrum_values = [1.0] * 12
    # spectrum_freqs[9] == 440 -> exact closest bin
    s.update_spectrum(440, 0.9)
    assert s.spectrum_values[9] == 0.9
    for i in range(12):
        if i != 9:
            assert s.spectrum_values[i] == 1.0 * s.SPECTRUM_DECAY_LEGACY


def test_update_spectrum_from_bands_maps_and_clamps():
    s = VisualizerState()
    cfg = _Config(intensity=1.0)
    s.update_spectrum_from_bands({"bass": 0.5, "treble": 0.3, "total": 9.9}, cfg)
    # bass -> bins [1, 2]; treble -> bin [10]
    assert s.spectrum_values[1] == 0.5
    assert s.spectrum_values[2] == 0.5
    assert s.spectrum_values[10] == 0.3
    # intensity clamp at 1.0
    cfg2 = _Config(intensity=4.0)
    s.update_spectrum_from_bands({"sub_bass": 0.8}, cfg2)
    assert s.spectrum_values[0] == 1.0
    # dominant band drives current_freq
    assert s.current_freq == s.BAND_FREQS["sub_bass"]


def test_rgb_levels_from_bands_math_and_clamp():
    s = VisualizerState()
    cfg = _Config(intensity=1.0)
    s.update_rgb_levels_from_bands(
        {"sub_bass": 0.4, "bass": 0.6, "low_mid": 0.3, "mid": 0.3, "high_mid": 0.3,
         "treble": 0.2, "sparkle": 0.4},
        cfg,
    )
    assert abs(s.target_bass - (0.4 + 0.6) / 2) < 1e-9
    assert abs(s.target_mid - (0.3 + 0.3 + 0.3) / 3) < 1e-9
    assert abs(s.target_treble - (0.2 + 0.4) / 2) < 1e-9
    # clamp at 1.0 with high intensity
    cfg2 = _Config(intensity=10.0)
    s.update_rgb_levels_from_bands({"sub_bass": 1.0, "bass": 1.0}, cfg2)
    assert s.target_bass == 1.0


def test_ingest_legacy_event_dispatch():
    s = VisualizerState()
    cfg = _Config()
    consumed = s.ingest(
        {"type": "audio", "frequency": 440, "amplitude": 0.7}, cfg
    )
    assert consumed is True
    assert s.target_freq == max(2, min(20, 440 // 50))  # 8
    assert s.target_amp == 0.7
    assert s.spectrum_values[9] == 0.7
    # 250 < 440 < 600 -> mid only
    assert s.target_mid == 0.7
    assert s.target_bass == 0.0
    assert s.target_treble == 0.0


def test_ingest_banded_event_dispatch():
    s = VisualizerState()
    cfg = _Config(intensity=1.0)
    consumed = s.ingest(
        {"type": "audio", "bands": {"bass": 0.9, "treble": 0.2, "total": 5.0}}, cfg
    )
    assert consumed is True
    assert s.spectrum_values[1] == 0.9  # bass -> bin 1
    assert s.target_freq == s.BAND_FREQS["bass"]  # dominant band
    assert s.target_amp == 0.9


def test_ingest_rejects_non_consumable_events():
    s = VisualizerState()
    cfg = _Config()
    assert s.ingest(None, cfg) is False
    assert s.ingest({"type": "heartbeat"}, cfg) is False
    # unchanged
    assert s.spectrum_values == [0.0] * 12
    assert s.target_amp == 0.0


def test_add_scroll_sample_smoothing_and_count():
    s = VisualizerState()
    s.resize(10)
    cfg = _Config(intensity=1.0, smooth_factor=0.5, samples_per_frame=2, RATE=500)
    s.target_amp = 1.0
    s.target_freq = 4

    s.add_scroll_sample(cfg)

    # smooth_amp moves halfway toward boosted target (1.0): 0 + (1.0-0)*0.5
    assert abs(s.smooth_amp - 0.5) < 1e-9
    # two samples added this frame
    assert s.sample_count == 2
    # freshly inserted samples carry age 0 at the front
    assert s.waveform_age_left[0] == 0
    assert s.waveform_age_right[0] == 0
    # display state updated
    assert s.current_freq == 4
    assert s.current_amp == s.smooth_amp


def test_decay_applies_all_factors():
    s = VisualizerState()
    s.resize(3)
    s.waveform_left = deque([1.0, 1.0, 1.0], maxlen=3)
    s.waveform_right = deque([2.0, 2.0, 2.0], maxlen=3)
    s.waveform_age_left = deque([0, 1, 2], maxlen=3)
    s.waveform_age_right = deque([5, 5, 5], maxlen=3)
    s.spectrum_values = [1.0] * 12
    s.target_bass = s.target_mid = s.target_treble = 1.0
    cfg = _Config(waveform_decay=0.9, spectrum_decay=0.5, rgb_decay=0.8)

    s.decay(cfg)

    assert all(abs(v - 0.9) < 1e-9 for v in s.waveform_left)
    assert all(abs(v - 1.8) < 1e-9 for v in s.waveform_right)
    assert list(s.waveform_age_left) == [1, 2, 3]
    assert list(s.waveform_age_right) == [6, 6, 6]
    assert all(abs(v - 0.5) < 1e-9 for v in s.spectrum_values)
    assert abs(s.target_bass - 0.8) < 1e-9
    assert abs(s.target_mid - 0.8) < 1e-9
    assert abs(s.target_treble - 0.8) < 1e-9
    # maxlen preserved through decay
    assert s.waveform_left.maxlen == 3


def test_beat_pulse_fires_on_bass_onset_and_decays():
    s = VisualizerState()
    s.resize(5)
    cfg = _Config()

    # Quiet frames first: baseline settles near zero, no pulse.
    for _ in range(5):
        s.add_scroll_sample(cfg)
    assert s.beat_pulse < 0.01

    # A bass hit well above baseline snaps the pulse to 1.0.
    s.target_bass = 0.8
    s.add_scroll_sample(cfg)
    assert s.beat_pulse == 1.0

    # With bass sustained, the refractory window keeps it from re-snapping
    # every frame: the pulse decays below 1.0 on the following frames.
    s.add_scroll_sample(cfg)
    assert s.beat_pulse < 1.0
    first_decay = s.beat_pulse
    s.add_scroll_sample(cfg)
    assert s.beat_pulse < first_decay


def test_beat_pulse_ignores_weak_bass():
    s = VisualizerState()
    s.resize(5)
    cfg = _Config()
    s.target_bass = 0.1  # Below the absolute onset floor.
    for _ in range(10):
        s.add_scroll_sample(cfg)
    assert s.beat_pulse < 0.01


def test_silence_frames_counts_quiet_and_resets_on_signal():
    s = VisualizerState()
    s.resize(5)
    cfg = _Config()

    for _ in range(4):
        s.add_scroll_sample(cfg)
    assert s.silence_frames == 4

    s.target_amp = 0.9
    s.add_scroll_sample(cfg)
    assert s.silence_frames == 0


_TESTS = [
    test_default_initialization,
    test_resize_from_empty_pads_values_and_ages,
    test_resize_grow_preserves_and_pads,
    test_resize_shrink_keeps_most_recent,
    test_update_spectrum_legacy_sets_closest_and_decays_others,
    test_update_spectrum_from_bands_maps_and_clamps,
    test_rgb_levels_from_bands_math_and_clamp,
    test_ingest_legacy_event_dispatch,
    test_ingest_banded_event_dispatch,
    test_ingest_rejects_non_consumable_events,
    test_add_scroll_sample_smoothing_and_count,
    test_decay_applies_all_factors,
    test_beat_pulse_fires_on_bass_onset_and_decays,
    test_beat_pulse_ignores_weak_bass,
    test_silence_frames_counts_quiet_and_resets_on_signal,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} engine tests passed.")
