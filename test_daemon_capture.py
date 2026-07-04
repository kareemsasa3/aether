#!/usr/bin/env python3
"""Behavioral tests for the daemon's audio capture wiring.

Two behaviors introduced for system-audio (sink monitor) capture are covered:

1. pw-record command construction in `AetherDaemon.run()`:
   - with `AETHER_AUDIO_TARGET` unset (or blank), the command has no
     `--target` flag, preserving the default-microphone behavior
   - with `AETHER_AUDIO_TARGET` set, `--target <value>` is passed so PipeWire
     captures from that node (e.g. a sink monitor) instead of the default mic

2. Event gating in `AetherDaemon.send_event()`:
   - gating uses the single shared `config.AUDIO_THRESHOLD`, not the old
     hardcoded `total < 0.10 and band < 0.15` pair, which suppressed valid
     (quieter) sink-monitor audio
   - a payload with `max(total, dominant_band) >= config.AUDIO_THRESHOLD`
     produces an event; one below the threshold is suppressed

No PipeWire, audio hardware, OpenRGB, or shared memory is required:
`subprocess.Popen` is replaced with a fake that records the command and
reports immediate exit (run() then returns via its existing early-exit path),
and `AetherSharedMemory` is replaced with an in-memory recorder.

Run directly (`python3 test_daemon_capture.py`) or via pytest.
"""
import io
import os
import sys
from contextlib import contextmanager
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether_config as config  # noqa: E402
import aether_daemon  # noqa: E402

MONITOR_TARGET = "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"


class _RecordingShm:
    """Stand-in for AetherSharedMemory that records written events."""

    def __init__(self, is_writer=False):
        self.is_writer = is_writer
        self.events = []

    def is_available(self):
        return True

    def write_event(self, event):
        self.events.append(event)
        return True

    def close(self):
        pass


class _ExitedProcess:
    """Fake pw-record process that has already exited.

    run() checks poll() shortly after Popen and bails out with its
    error-reporting path, so the main read loop never starts.
    """

    def __init__(self):
        self.returncode = 1
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(b"")

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


@contextmanager
def _make_daemon(env_target=None):
    """Build an AetherDaemon with no real SHM/signal side effects.

    env_target: value for AETHER_AUDIO_TARGET, or None to leave it unset.
    """
    env = dict(os.environ)
    env.pop("AETHER_AUDIO_TARGET", None)
    if env_target is not None:
        env["AETHER_AUDIO_TARGET"] = env_target

    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(aether_daemon.signal, "signal"), \
            mock.patch.object(aether_daemon, "AetherSharedMemory", _RecordingShm):
        yield aether_daemon.AetherDaemon()


def _run_and_capture_cmd(daemon):
    """Run the daemon against a fake pw-record and return the command used."""
    popen_calls = []

    def fake_popen(cmd, **kwargs):
        popen_calls.append(list(cmd))
        return _ExitedProcess()

    with mock.patch.object(aether_daemon.subprocess, "Popen", fake_popen), \
            mock.patch.object(aether_daemon.time, "sleep"):
        rc = daemon.run()

    # The fake process reports immediate failure, so run() exits early.
    assert rc == 1
    assert len(popen_calls) == 1
    return popen_calls[0]


def _bands(dominant=0.0, total=0.0):
    """Band payload with one dominant band; others zero."""
    payload = {name: 0.0 for name in config.FREQUENCY_BANDS}
    payload["bass"] = dominant
    payload["total"] = total
    return payload


# ---------------------------------------------------------------------------
# pw-record command construction
# ---------------------------------------------------------------------------

def test_default_pw_record_cmd_omits_target():
    with _make_daemon() as daemon:
        cmd = _run_and_capture_cmd(daemon)
    assert cmd[0] == "pw-record"
    assert "--target" not in cmd
    assert cmd[-1] == "-"  # still streams to stdout


def test_env_audio_target_adds_target_flag():
    with _make_daemon(env_target=MONITOR_TARGET) as daemon:
        cmd = _run_and_capture_cmd(daemon)
    idx = cmd.index("--target")
    assert cmd[idx + 1] == MONITOR_TARGET
    assert cmd[-1] == "-"  # target flag must not displace the stdout arg


def test_blank_audio_target_treated_as_unset():
    with _make_daemon(env_target="   ") as daemon:
        cmd = _run_and_capture_cmd(daemon)
    assert "--target" not in cmd


# ---------------------------------------------------------------------------
# send_event() gating
# ---------------------------------------------------------------------------

def test_send_event_emits_at_audio_threshold():
    with _make_daemon() as daemon:
        daemon.send_event(_bands(dominant=config.AUDIO_THRESHOLD,
                                 total=config.AUDIO_THRESHOLD))
        assert len(daemon.shm.events) == 1


def test_send_event_emits_when_only_dominant_band_clears_threshold():
    # max(total, band) semantics: a strong band with weak total still emits.
    with _make_daemon() as daemon:
        daemon.send_event(_bands(dominant=config.AUDIO_THRESHOLD * 2, total=0.0))
        assert len(daemon.shm.events) == 1


def test_send_event_suppressed_below_audio_threshold():
    with _make_daemon() as daemon:
        daemon.send_event(_bands(dominant=config.AUDIO_THRESHOLD * 0.5,
                                 total=config.AUDIO_THRESHOLD * 0.5))
        assert daemon.shm.events == []


def test_send_event_gate_tracks_config_threshold():
    """Gating follows config.AUDIO_THRESHOLD, not the old 0.10/0.15 pair."""
    with _make_daemon() as daemon:
        with mock.patch.object(config, "AUDIO_THRESHOLD", 0.42):
            # 0.30 beat both old hardcoded gates but is below the config value.
            daemon.send_event(_bands(dominant=0.30, total=0.30))
            assert daemon.shm.events == []
            daemon.send_event(_bands(dominant=0.50, total=0.50))
            assert len(daemon.shm.events) == 1


if __name__ == "__main__":
    test_default_pw_record_cmd_omits_target()
    print("OK: default pw-record command omits --target")
    test_env_audio_target_adds_target_flag()
    print("OK: AETHER_AUDIO_TARGET adds --target <value>")
    test_blank_audio_target_treated_as_unset()
    print("OK: blank AETHER_AUDIO_TARGET is treated as unset")
    test_send_event_emits_at_audio_threshold()
    print("OK: event emitted at config.AUDIO_THRESHOLD")
    test_send_event_emits_when_only_dominant_band_clears_threshold()
    print("OK: dominant band alone can clear the threshold")
    test_send_event_suppressed_below_audio_threshold()
    print("OK: event suppressed below config.AUDIO_THRESHOLD")
    test_send_event_gate_tracks_config_threshold()
    print("OK: gate tracks config.AUDIO_THRESHOLD")
