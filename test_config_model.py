#!/usr/bin/env python3
"""Unit tests for config_model.VizConfig.

Phase 2 of the TUI refactor moved the visualizer's tunable settings out of
`UltimateOscilloscope` into `VizConfig`. These tests pin the behavior that was
previously embedded in the `_init_config` / `_get_config_value` /
`_set_config_value` / `_load_preset` methods:

  - defaults are seeded from CONFIG_SCHEMA
  - get() returns the current value
  - set() clamps to each setting's [min, max] range
  - set() keeps the derived RATE in sync with virtual_sample_rate
  - apply_preset() applies every value in a known preset (and reports missing)
  - the overlay's "save custom preset" pattern round-trips through apply_preset

No curses, audio, or numpy required — VizConfig is pure data.

Run directly (`python3 test_config_model.py`) or via pytest.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether_config  # noqa: E402
import config_model  # noqa: E402
from config_model import CONFIG_SCHEMA, PRESETS, VizConfig  # noqa: E402


def test_defaults_match_schema():
    vc = VizConfig()
    for key, spec in CONFIG_SCHEMA.items():
        default = spec[0]
        assert getattr(vc, key) == default
        assert vc.get(key) == default
    # Config-derived defaults resolve to the central aether_config values.
    assert vc.get("waveform_decay") == aether_config.WAVEFORM_DECAY
    assert vc.get("spectrum_decay") == aether_config.SPECTRUM_DECAY
    assert vc.get("smooth_factor") == aether_config.SMOOTH_FACTOR


def test_keys_match_schema_order():
    vc = VizConfig()
    assert vc.keys == list(CONFIG_SCHEMA.keys())


def test_rate_seeded_from_virtual_sample_rate():
    vc = VizConfig()
    assert vc.RATE == vc.virtual_sample_rate
    assert vc.RATE == CONFIG_SCHEMA["virtual_sample_rate"][0]


def test_set_within_range():
    vc = VizConfig()
    vc.set("intensity", 1.5)  # range 0.5 - 2.0
    assert vc.get("intensity") == 1.5


def test_set_clamps_below_min_and_above_max():
    vc = VizConfig()
    _, min_val, max_val, _, _, _ = CONFIG_SCHEMA["intensity"]
    vc.set("intensity", min_val - 10)
    assert vc.get("intensity") == min_val
    vc.set("intensity", max_val + 10)
    assert vc.get("intensity") == max_val


def test_set_virtual_sample_rate_updates_rate():
    vc = VizConfig()
    vc.set("virtual_sample_rate", 600)
    assert vc.get("virtual_sample_rate") == 600
    assert vc.RATE == 600
    # Clamping also flows through to the derived value.
    _, vmin, vmax, _, _, _ = CONFIG_SCHEMA["virtual_sample_rate"]
    vc.set("virtual_sample_rate", vmax + 1000)
    assert vc.RATE == vmax


def test_apply_known_preset_sets_all_values():
    vc = VizConfig()
    assert vc.apply_preset("edm") is True
    for key, value in PRESETS["edm"].items():
        assert vc.get(key) == value
    # Derived RATE tracks the preset's virtual_sample_rate.
    assert vc.RATE == PRESETS["edm"]["virtual_sample_rate"]


def test_apply_unknown_preset_returns_false_and_no_change():
    vc = VizConfig()
    before = {k: vc.get(k) for k in vc.keys}
    assert vc.apply_preset("does_not_exist") is False
    after = {k: vc.get(k) for k in vc.keys}
    assert before == after


def test_save_custom_preset_round_trip():
    # Mirrors the config overlay's "W" save: stash current values under a
    # "custom" preset, then re-apply it. PRESETS is module-level, so restore it.
    had_custom = "custom" in PRESETS
    saved = PRESETS.get("custom")
    try:
        vc = VizConfig()
        vc.set("intensity", 1.7)
        vc.set("samples_per_frame", 5)
        PRESETS["custom"] = {k: vc.get(k) for k in vc.keys}

        fresh = VizConfig()  # defaults
        assert fresh.get("intensity") != 1.7
        assert fresh.apply_preset("custom") is True
        assert fresh.get("intensity") == 1.7
        assert fresh.get("samples_per_frame") == 5
    finally:
        if had_custom:
            PRESETS["custom"] = saved
        else:
            PRESETS.pop("custom", None)


def test_instances_are_independent():
    a = VizConfig()
    b = VizConfig()
    a.set("intensity", 2.0)
    assert b.get("intensity") == CONFIG_SCHEMA["intensity"][0]


_TESTS = [
    test_defaults_match_schema,
    test_keys_match_schema_order,
    test_rate_seeded_from_virtual_sample_rate,
    test_set_within_range,
    test_set_clamps_below_min_and_above_max,
    test_set_virtual_sample_rate_updates_rate,
    test_apply_known_preset_sets_all_values,
    test_apply_unknown_preset_returns_false_and_no_change,
    test_save_custom_preset_round_trip,
    test_instances_are_independent,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} config_model tests passed.")
