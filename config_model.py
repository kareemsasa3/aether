"""Configuration model for the Aether terminal visualizer.

Phase 2 of the TUI refactor (see REFACTOR.md): the tunable-settings schema,
the presets, and the get/set/apply behavior that previously lived as class
attributes and helper methods on `UltimateOscilloscope` move here behind a
small `VizConfig` object.

This is a behavior-preserving extraction, not a redesign:
- `CONFIG_SCHEMA` and `PRESETS` are moved verbatim (same keys, ranges, labels,
  and preset values).
- `VizConfig` owns the current values as plain attributes and reproduces the
  exact semantics of the former `_init_config` / `_get_config_value` /
  `_set_config_value` / `_load_preset` methods, including the `RATE` derived
  value kept in sync with `virtual_sample_rate`.

`VizConfig` is pure data (no curses, no shared memory), so it is unit-testable
in isolation.
"""

import aether_config as config


# Configurable settings with their ranges: (default, min, max, step, name, description)
CONFIG_SCHEMA = {
    "samples_per_frame": (2, 1, 8, 1, "Scroll Speed", "Animation speed"),
    "waveform_decay": (
        config.WAVEFORM_DECAY,
        0.90,
        0.999,
        0.005,
        "Trail Length",
        "Trail persistence",
    ),
    "spectrum_decay": (config.SPECTRUM_DECAY, 0.70, 0.99, 0.02, "Spectrum Decay", "Bar fade speed"),
    "rgb_decay": (0.85, 0.50, 0.95, 0.05, "RGB Decay", "RGB fade speed"),
    "smooth_factor": (config.SMOOTH_FACTOR, 0.05, 0.8, 0.05, "Smoothing", "Transition smoothness"),
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
        "waveform_decay": config.WAVEFORM_DECAY,
        "spectrum_decay": config.SPECTRUM_DECAY,
        "rgb_decay": 0.85,
        "smooth_factor": config.SMOOTH_FACTOR,
        "intensity": 1.0,
        "virtual_sample_rate": 500,
    },
}


class VizConfig:
    """Owns the visualizer's tunable settings: schema, presets, current values,
    and get/set/apply helpers.

    Current values are stored as plain attributes (e.g. ``self.intensity``) so
    callers can read them directly, exactly as they did on the oscilloscope
    instance before the extraction.
    """

    # Exposed for callers that read the schema/presets through the config model.
    CONFIG_SCHEMA = CONFIG_SCHEMA
    PRESETS = PRESETS

    def __init__(self):
        # Initialize current values from schema defaults (was _init_config).
        for key, (
            default,
            min_val,
            max_val,
            step,
            name,
            desc,
        ) in CONFIG_SCHEMA.items():
            setattr(self, key, default)

        # Stable ordering of the configurable keys (was self.config_keys).
        self.keys = list(CONFIG_SCHEMA.keys())

        # Derived runtime value, kept in sync with virtual_sample_rate (was
        # self.RATE on the oscilloscope).
        self.RATE = self.virtual_sample_rate

    def get(self, key):
        """Get current value of a config setting."""
        return getattr(self, key, CONFIG_SCHEMA[key][0])

    def set(self, key, value):
        """Set a config value, clamping to its valid range."""
        schema = CONFIG_SCHEMA[key]
        min_val, max_val = schema[1], schema[2]
        clamped = max(min_val, min(max_val, value))
        setattr(self, key, clamped)

        # Update derived values if needed.
        if key == "virtual_sample_rate":
            self.RATE = clamped

    def apply_preset(self, preset_name):
        """Load a configuration preset. Returns True if the preset exists."""
        if preset_name in PRESETS:
            for key, value in PRESETS[preset_name].items():
                self.set(key, value)
            return True
        return False
