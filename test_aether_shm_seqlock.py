#!/usr/bin/env python3
"""Behavioral tests for the aether_shm seqlock protocol.

`test_config_wiring.py` covers plumbing (constants resolve to config); this
file covers the thing that is actually hard to get right: the seqlock in
`aether_shm.AetherSharedMemory`. The protocol's correctness rests on a handful
of reader decisions, so each gets a focused, deterministic test:

  - a committed (even) sequence is readable
  - sequence 0 (uninitialized) is ignored
  - an odd sequence (write-in-progress marker) is ignored
  - an already-seen sequence is ignored
  - a mismatched seq1 != seq2 (writer moved mid-read) skips the torn frame
  - a writer -> reader round trip returns the exact payload
  - an odd sequence injected between two committed frames yields neither a torn
    nor a stale frame — the reader skips it and then reads the next commit

Everything runs against a private shared-memory file (the module's SHM_PATH is
redirected to a unique temp path per pair), so the tests never collide with a
live daemon. No PipeWire, OpenRGB, curses, or systemd is required — only
`aether_shm` is imported.

Run directly (`python3 test_aether_shm_seqlock.py`) or via pytest.
"""
import json
import os
import struct
import sys
import tempfile
from contextlib import contextmanager

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import aether_shm  # noqa: E402
from aether_shm import (  # noqa: E402
    AetherSharedMemory,
    HEADER_FORMAT,
    HEADER_SIZE,
    MAGIC,
    SEQ_OFFSET,
    SHM_SIZE,
    VERSION,
)


def _unique_shm_path():
    """A private, RAM-backed-if-possible path that won't hit a live daemon."""
    base = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
    fd, path = tempfile.mkstemp(prefix="aether_seqlock_test_", dir=base)
    os.close(fd)
    # Remove it so the writer creates a fresh, correctly-sized region.
    os.unlink(path)
    return path


@contextmanager
def shm_pair():
    """Yield a (writer, reader) bound to a private shared-memory region.

    SHM_PATH is patched before either instance is constructed (each captures
    the path at init) and restored on exit; the backing file is removed.
    """
    path = _unique_shm_path()
    old_path = aether_shm.SHM_PATH
    aether_shm.SHM_PATH = path
    writer = reader = None
    try:
        writer = AetherSharedMemory(is_writer=True)  # creates file + seq=0 header
        reader = AetherSharedMemory(is_writer=False)  # opens the same file
        assert writer.is_available(), "writer failed to map shared memory"
        assert reader.is_available(), "reader failed to map shared memory"
        yield writer, reader
    finally:
        if reader is not None:
            reader.close()
        if writer is not None:
            writer.close()
        try:
            os.unlink(path)
        except OSError:
            pass
        aether_shm.SHM_PATH = old_path


def _poke_sequence(writer, seq):
    """Overwrite only the 8-byte sequence field via the writer's mapping."""
    writer._mm.seek(SEQ_OFFSET)
    writer._mm.write(struct.pack("@Q", seq))


def _frame_buffer(seq, payload):
    """A full SHM_SIZE buffer holding one frame: header(seq, len) + JSON data."""
    data = json.dumps(payload).encode("utf-8")
    buf = bytearray(SHM_SIZE)
    struct.pack_into(HEADER_FORMAT, buf, 0, MAGIC, VERSION, seq, len(data))
    buf[HEADER_SIZE:HEADER_SIZE + len(data)] = data
    return buf


class _FakeMmap:
    """Minimal seek/read mmap stand-in backed by a bytearray.

    After a configured number of read() calls it rewrites the sequence field,
    simulating a writer that commits a new frame *between* the reader's two
    sequence samples (seq1 captured in the header read, seq2 re-read at the
    end). This is the only way to exercise the seq1 != seq2 branch
    deterministically in a single thread.
    """

    def __init__(self, buf, mutate_after=None, new_seq=None):
        self._buf = bytearray(buf)
        self._pos = 0
        self._reads = 0
        self._mutate_after = mutate_after
        self._new_seq = new_seq

    def seek(self, pos):
        self._pos = pos

    def read(self, n):
        self._reads += 1
        chunk = bytes(self._buf[self._pos:self._pos + n])
        self._pos += n
        if self._mutate_after is not None and self._reads == self._mutate_after:
            struct.pack_into("@Q", self._buf, SEQ_OFFSET, self._new_seq)
        return chunk

    def close(self):
        pass


def test_committed_even_sequence_is_readable():
    with shm_pair() as (writer, reader):
        assert writer.write_event({"type": "audio", "v": 1})  # seq -> 2 (even)
        assert (writer.last_sequence % 2) == 0
        event = reader.read_event()
        assert event == {"type": "audio", "v": 1}


def test_sequence_zero_is_ignored():
    with shm_pair() as (writer, reader):
        # Fresh writer initialized the header with seq=0 and never wrote a frame.
        assert reader.read_event() is None


def test_odd_sequence_is_ignored():
    with shm_pair() as (writer, reader):
        assert writer.write_event({"type": "audio"})  # commits seq=2 with data
        _poke_sequence(writer, 3)  # odd => write-in-progress marker
        assert reader.read_event() is None


def test_already_seen_sequence_is_ignored():
    with shm_pair() as (writer, reader):
        assert writer.write_event({"type": "audio", "n": 1})
        assert reader.read_event() == {"type": "audio", "n": 1}
        # No new commit: the sequence is unchanged, so the reader must not
        # re-deliver the same frame.
        assert reader.read_event() is None


def test_seq_mismatch_skips_torn_read():
    with shm_pair() as (writer, reader):
        buf = _frame_buffer(2, {"type": "audio", "torn": False})
        # Drop the real mapping and drive read_event() against a fake that
        # changes the sequence after the data read but before the seq2 re-read.
        reader._mm.close()
        reader._mm = _FakeMmap(buf, mutate_after=2, new_seq=4)
        reader.last_sequence = 0
        assert reader.read_event() is None  # seq1 (2) != seq2 (4) => skipped


def test_writer_reader_round_trip():
    with shm_pair() as (writer, reader):
        payload = {
            "type": "audio",
            "bands": {"bass": 0.73, "treble": 0.21},
            "frequency": 150,
            "amplitude": 0.73,
            "timestamp": 1234.5,
        }
        assert writer.write_event(payload)
        assert reader.read_event() == payload


def test_injected_odd_between_committed_frames_no_torn_or_stale():
    with shm_pair() as (writer, reader):
        frame_a = {"type": "audio", "frame": "A"}
        frame_b = {"type": "audio", "frame": "B"}

        assert writer.write_event(frame_a)  # seq -> 2
        assert reader.read_event() == frame_a

        # Simulate a write starting: sequence goes odd. The reader must skip it
        # rather than hand back a torn frame or re-deliver the stale A.
        _poke_sequence(writer, writer.last_sequence + 1)  # 3 (odd)
        assert reader.read_event() is None

        # The write completes and commits the next frame; the reader catches it.
        assert writer.write_event(frame_b)  # seq -> 4
        assert reader.read_event() == frame_b


def test_sequential_frames_are_delivered_in_order():
    # Deterministic, single-threaded, bounded: each fresh commit reads back
    # exactly once, exercising monotonic sequence handling without timing.
    with shm_pair() as (writer, reader):
        for i in range(50):
            assert writer.write_event({"type": "audio", "i": i})
            event = reader.read_event()
            assert event == {"type": "audio", "i": i}


_TESTS = [
    test_committed_even_sequence_is_readable,
    test_sequence_zero_is_ignored,
    test_odd_sequence_is_ignored,
    test_already_seen_sequence_is_ignored,
    test_seq_mismatch_skips_torn_read,
    test_writer_reader_round_trip,
    test_injected_odd_between_committed_frames_no_torn_or_stale,
    test_sequential_frames_are_delivered_in_order,
]


if __name__ == "__main__":
    for t in _TESTS:
        t()
        print(f"OK: {t.__name__}")
    print(f"\nAll {len(_TESTS)} seqlock tests passed.")
