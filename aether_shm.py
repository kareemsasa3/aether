#!/usr/bin/env python3
"""
Shared Memory IPC for Aether

Provides ultra-low-latency communication between the audio daemon and visualizer
using memory-mapped files instead of disk I/O.

Performance: ~1000x faster than file writes (microseconds vs milliseconds)
Mechanism: mmap'd file acts as shared memory region accessible by both processes.

Usage:
    Writer (audio daemon):
        writer = AetherSharedMemory(is_writer=True)
        writer.write_event(event_dict)

    Reader (visualizer):
        reader = AetherSharedMemory(is_writer=False)
        event = reader.read_event()  # Returns None if no new data
"""

import mmap
import os
import struct
import json
import sys

# =============================================================================
# SHARED MEMORY CONFIGURATION
# =============================================================================

# File path for the memory-mapped region (in tmpfs for true RAM-backed storage)
# /dev/shm is a tmpfs mount on Linux - writes never hit disk
SHM_PATH = "/dev/shm/aether_audio_event"

# Fallback to /tmp if /dev/shm doesn't exist (macOS, some containers)
if not os.path.isdir("/dev/shm"):
    SHM_PATH = "/tmp/aether_audio_event.shm"

# Size of the shared memory region in bytes
# 4KB is plenty for our JSON event data (~200-500 bytes typical)
# Structure: [4-byte MAGIC][4-byte VERSION][8-byte sequence][4-byte data length][data...]
SHM_SIZE = 4096

# Protocol Constants
MAGIC = b"AEHR"  # Aether Magic
VERSION = 1

# Header format: MAGIC (4s) + VERSION (I) + SEQUENCE (Q) + LENGTH (I)
# 4 + 4 + 8 + 4 = 20 bytes
HEADER_FORMAT = "@4sIQI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Maximum JSON payload size
MAX_PAYLOAD_SIZE = SHM_SIZE - HEADER_SIZE

# Debug mode for error logging
DEBUG = False


class AetherSharedMemory:
    """
    Lock-free shared memory for audio event IPC using Optimistic Concurrency Control.

    Protocol V1:
    - Writer: Writes Data first, then updates Header (Sequence)
    - Reader: Reads Header (Seq1), reads Data, reads Header (Seq2)
    - If Seq1 == Seq2, data is consistent.
    """

    def __init__(self, is_writer: bool = False):
        """
        Initialize shared memory.

        Args:
            is_writer: True for the audio daemon, False for visualizer
        """
        self.is_writer = is_writer
        self.shm_path = SHM_PATH
        self.last_sequence = 0
        self._mm = None
        self._fd = None

        self._init_shm()

    def _init_shm(self):
        """Initialize or open the shared memory region."""
        try:
            if self.is_writer:
                # Writer creates/truncates the file
                self._fd = os.open(
                    self.shm_path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644
                )
                # Extend to required size
                os.ftruncate(self._fd, SHM_SIZE)
            else:
                # Reader opens existing file (may not exist yet)
                if not os.path.exists(self.shm_path):
                    return  # Will fall back to legacy mode
                self._fd = os.open(self.shm_path, os.O_RDONLY)

            # Memory-map the file
            access = mmap.ACCESS_WRITE if self.is_writer else mmap.ACCESS_READ
            self._mm = mmap.mmap(self._fd, SHM_SIZE, access=access)

        except (OSError, PermissionError) as e:
            if DEBUG:
                print(f"[SHM] Init Error: {e}", file=sys.stderr)
            # Fall back gracefully - caller should check is_available()
            self._mm = None
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    def is_available(self) -> bool:
        """Check if shared memory is ready for use."""
        return self._mm is not None

    def write_event(self, event: dict) -> bool:
        """
        Write an event to shared memory.

        Args:
            event: Dictionary to serialize and write

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.is_available():
            return False

        try:
            # Serialize to JSON
            data = json.dumps(event).encode("utf-8")
            data_len = len(data)

            if data_len > MAX_PAYLOAD_SIZE:
                if DEBUG:
                    print(f"[SHM] Payload too large: {data_len}", file=sys.stderr)
                data = data[:MAX_PAYLOAD_SIZE]
                data_len = MAX_PAYLOAD_SIZE

            # Increment sequence number (atomic for single writer)
            self.last_sequence += 1

            # 1. Memory Barrier Simulation: Write Data FIRST
            # This ensures that if reader sees new sequence, data is already there.
            self._mm.seek(HEADER_SIZE)
            self._mm.write(data)

            # 2. Write Header (Commit)
            # Updates Sequence number, making the new data valid
            header = struct.pack(
                HEADER_FORMAT, MAGIC, VERSION, self.last_sequence, data_len
            )
            self._mm.seek(0)
            self._mm.write(header)

            return True

        except Exception as e:
            if DEBUG:
                print(f"[SHM] Write Error: {e}", file=sys.stderr)
            return False

    def read_event(self) -> dict | None:
        """
        Read the latest event using Optimistic Concurrency Control.

        Returns:
            Event dictionary if new data available, None otherwise
        """
        if not self.is_available():
            return None

        try:
            # 1. Read Header (Seq1)
            self._mm.seek(0)
            header_data = self._mm.read(HEADER_SIZE)

            if len(header_data) < HEADER_SIZE:
                return None

            magic, version, seq1, data_len = struct.unpack(HEADER_FORMAT, header_data)

            # Validate Protocol
            if magic != MAGIC or version != VERSION:
                if DEBUG:
                    print(
                        f"[SHM] Protocol Mismatch: {magic}/{version}", file=sys.stderr
                    )
                return None

            # Check if this is new data (optimization)
            if seq1 == 0 or seq1 <= self.last_sequence:
                return None

            # Validate data length
            if data_len == 0 or data_len > MAX_PAYLOAD_SIZE:
                return None

            # 2. Read Data
            self._mm.seek(HEADER_SIZE)
            data = self._mm.read(data_len)

            # 3. Read Sequence Again (Seq2) - OCC Verify
            self._mm.seek(0)
            # Just read enough to get sequence (4 + 4 + 8 bytes)
            # Offset 8 is where sequence starts (MAGIC=4 + VERSION=4)
            self._mm.seek(8)
            (seq2,) = struct.unpack("@Q", self._mm.read(8))

            # 4. Verify Consistency
            if seq1 != seq2:
                # Writer updated mid-read! Data is potentially corrupt.
                # Just return None, we'll catch the next frame (it's 48kHz audio).
                if DEBUG:
                    print(f"[SHM] Race detected: {seq1} != {seq2}", file=sys.stderr)
                return None

            # Consistent read! Parse data.
            event = json.loads(data.decode("utf-8"))

            # Update last seen sequence
            self.last_sequence = seq1

            return event

        except Exception as e:
            if DEBUG:
                print(f"[SHM] Read Error: {e}", file=sys.stderr)
            return None

    def close(self):
        """Clean up resources."""
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# =============================================================================
# LEGACY COMPATIBILITY LAYER
# =============================================================================
# For backward compatibility, we also provide file-based fallback

LEGACY_EVENT_FILE = "/tmp/aether_last_event.json"


def write_event_legacy(event: dict) -> bool:
    """Write event using legacy file method (fallback)."""
    try:
        with open(LEGACY_EVENT_FILE, "w") as f:
            json.dump(event, f)
        return True
    except Exception:
        return False


def read_event_legacy() -> tuple[dict | None, float]:
    """
    Read event using legacy file method.

    Returns:
        Tuple of (event_dict or None, modification_time)
    """
    try:
        if not os.path.exists(LEGACY_EVENT_FILE):
            return None, 0.0

        mtime = os.path.getmtime(LEGACY_EVENT_FILE)
        with open(LEGACY_EVENT_FILE, "r") as f:
            event = json.load(f)
        return event, mtime
    except Exception:
        return None, 0.0
