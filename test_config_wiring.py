#!/usr/bin/env python3
"""Smoke test: the daemon sources its tunable constants from aether_config.

Two things are checked:
1. `aether_daemon` imports cleanly. systemd runs it as
   `python3 /path/aether_daemon.py`, which puts the script's own directory on
   sys.path[0] — the same mechanism that resolves `import aether_config`. This
   test forces that layout (script dir on path, cwd elsewhere) so a regression
   would surface here rather than as a runtime ModuleNotFoundError.
2. The previously-duplicated daemon constants resolve to the config values,
   i.e. aether_config.py is the single source of truth.

Run directly (`python3 test_config_wiring.py`) or via pytest.
"""
import os
import sys

# Make the import resolvable exactly the way `python3 aether_daemon.py` does:
# the script's directory on sys.path, regardless of current working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether_config as config  # noqa: E402
import aether_daemon  # noqa: E402  (must import without starting the audio loop)


def test_daemon_sources_constants_from_config():
    d = aether_daemon.AetherDaemon
    assert d.CHUNK_SIZE == config.CHUNK_SIZE
    assert d.SAMPLE_RATE == config.SAMPLE_RATE
    assert d.LOG_ENERGY_MIN_BAND == config.LOG_ENERGY_MIN_BAND
    assert d.LOG_ENERGY_RANGE_BAND == config.LOG_ENERGY_RANGE_BAND
    assert d.LOG_ENERGY_MIN_TOTAL == config.LOG_ENERGY_MIN_TOTAL
    assert d.LOG_ENERGY_RANGE_TOTAL == config.LOG_ENERGY_RANGE_TOTAL
    assert d.FREQUENCY_BANDS == config.FREQUENCY_BANDS


if __name__ == "__main__":
    test_daemon_sources_constants_from_config()
    print("OK: daemon sources its tunable constants from aether_config.py")
