#!/usr/bin/env python3
"""Smoke test: components source their tunable constants from aether_config.

Three things are checked:
1. `aether_daemon` imports cleanly. systemd runs it as
   `python3 /path/aether_daemon.py`, which puts the script's own directory on
   sys.path[0] — the same mechanism that resolves `import aether_config`. This
   test forces that layout (script dir on path, cwd elsewhere) so a regression
   would surface here rather than as a runtime ModuleNotFoundError.
2. The previously-duplicated daemon constants resolve to the config values,
   i.e. aether_config.py is the single source of truth.
3. The RGB controller's tuning constants likewise resolve to the config values.
   `aether_rgb` imports the `openrgb` library at module load, which need not be
   installed wherever this test runs (CI, dev box without RGB hardware), so we
   inject a lightweight stub for it before importing. The stub only has to let
   the class body evaluate — the constants under test are plain class
   attributes set at definition time.

Run directly (`python3 test_config_wiring.py`) or via pytest.
"""
import os
import sys
import types

# Make the import resolvable exactly the way `python3 aether_daemon.py` does:
# the script's directory on sys.path, regardless of current working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether_config as config  # noqa: E402
import aether_daemon  # noqa: E402  (must import without starting the audio loop)


def _ensure_openrgb_importable():
    """Stub the optional `openrgb` dependency so aether_rgb can be imported.

    No-op if the real library is present; otherwise registers minimal stand-in
    modules so the `from openrgb import ...` / `from openrgb.utils import ...`
    statements at the top of aether_rgb succeed.
    """
    try:
        import openrgb  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    openrgb_mod = types.ModuleType("openrgb")
    openrgb_mod.OpenRGBClient = object
    utils_mod = types.ModuleType("openrgb.utils")
    utils_mod.RGBColor = object
    sys.modules["openrgb"] = openrgb_mod
    sys.modules["openrgb.utils"] = utils_mod


_ensure_openrgb_importable()
import aether_rgb  # noqa: E402  (must import without connecting to OpenRGB)


def test_daemon_sources_constants_from_config():
    d = aether_daemon.AetherDaemon
    assert d.CHUNK_SIZE == config.CHUNK_SIZE
    assert d.SAMPLE_RATE == config.SAMPLE_RATE
    assert d.LOG_ENERGY_MIN_BAND == config.LOG_ENERGY_MIN_BAND
    assert d.LOG_ENERGY_RANGE_BAND == config.LOG_ENERGY_RANGE_BAND
    assert d.LOG_ENERGY_MIN_TOTAL == config.LOG_ENERGY_MIN_TOTAL
    assert d.LOG_ENERGY_RANGE_TOTAL == config.LOG_ENERGY_RANGE_TOTAL
    assert d.FREQUENCY_BANDS == config.FREQUENCY_BANDS


def test_rgb_sources_constants_from_config():
    r = aether_rgb.AetherRGB
    assert r.TARGET_FPS == config.RGB_FPS
    assert r.DECAY_FACTOR == config.RGB_DECAY_FACTOR
    assert r.BRIGHTNESS_BOOST == config.RGB_BRIGHTNESS_BOOST
    # FRAME_TIME is derived from the config-backed FPS.
    assert r.FRAME_TIME == 1.0 / config.RGB_FPS

    # Color/band maps source from config (verbatim for colors and full order;
    # RAM mapping is a controller-local band selection painted with config
    # colors).
    assert r.BAND_COLORS == config.BAND_COLORS
    assert r.BAND_ORDER == config.BAND_ORDER
    assert r.RAM_BANDS == ["sub_bass", "bass", "mid", "high_mid", "treble"]
    assert r.RAM_BAND_MAPPING == [
        (band, config.BAND_COLORS[band]) for band in r.RAM_BANDS
    ]

    # The silence threshold itself (int(config.RGB_SILENCE_THRESHOLD *
    # TARGET_FPS)) is computed as a local inside AetherRGB.run(), which can't be
    # invoked without a live OpenRGB connection. We assert its inputs are
    # config-backed (TARGET_FPS above, plus the threshold constant existing
    # here); fully asserting the computed value would require refactoring run()
    # to expose it, which is intentionally out of scope for now.
    assert isinstance(config.RGB_SILENCE_THRESHOLD, (int, float))


if __name__ == "__main__":
    test_daemon_sources_constants_from_config()
    print("OK: daemon sources its tunable constants from aether_config.py")
    test_rgb_sources_constants_from_config()
    print("OK: RGB controller sources its tunable constants from aether_config.py")
