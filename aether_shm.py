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

# Byte offsets for atomic field-level writes, derived from the format so they
# stay correct under native alignment. The sequence sits at an 8-byte-aligned
# offset, so writing it is a single atomic 64-bit store on x86.
SEQ_OFFSET = struct.calcsize("@4sI")   # 8:  after MAGIC + VERSION
LEN_OFFSET = struct.calcsize("@4sIQ")  # 16: after MAGIC + VERSION + SEQUENCE

# Maximum JSON payload size
MAX_PAYLOAD_SIZE = SHM_SIZE - HEADER_SIZE

# Debug mode for error logging
DEBUG = False


class AetherSharedMemory:
    """
    Lock-free shared memory for audio event IPC using a seqlock.

    Protocol V1:
    - Committed sequence numbers are EVEN; an ODD sequence marks a write in
      progress, so readers skip it rather than latch torn data.
    - Writer: bump seq to odd -> write data + length -> bump seq to even (commit).
    - Reader: read Header (Seq1); bail if Seq1 is 0/odd/already-seen; read data;
      read Seq2. Data is consistent only if Seq1 == Seq2 (and Seq1 is even).
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
        # Clean up any existing mapping first
        if self._mm is not None:
            try:
                self._mm.close()
            except Exception:
                pass
            self._mm = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None

        try:
            if self.is_writer:
                # Writer creates the file if needed, but doesn't truncate existing
                # This prevents race condition with active readers
                file_exists = os.path.exists(self.shm_path)
                
                if file_exists:
                    # Open existing file without truncation
                    self._fd = os.open(self.shm_path, os.O_RDWR, 0o644)
                    # Check if it's the right size
                    current_size = os.fstat(self._fd).st_size
                    if current_size != SHM_SIZE:
                        # Wrong size, need to resize (rare edge case)
                        os.ftruncate(self._fd, SHM_SIZE)
                else:
                    # Create new file
                    self._fd = os.open(
                        self.shm_path, os.O_RDWR | os.O_CREAT, 0o644
                    )
                    os.ftruncate(self._fd, SHM_SIZE)
                
                # Reset sequence on fresh start (write header with seq=0)
                # This signals to readers that we're starting fresh
                self.last_sequence = 0
                
            else:
                # Reader opens existing file (may not exist yet)
                if not os.path.exists(self.shm_path):
                    return  # Will fall back to legacy mode
                self._fd = os.open(self.shm_path, os.O_RDONLY)

            # Memory-map the file
            access = mmap.ACCESS_WRITE if self.is_writer else mmap.ACCESS_READ
            self._mm = mmap.mmap(self._fd, SHM_SIZE, access=access)
            
            # Writer: Initialize header on fresh file
            if self.is_writer:
                header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, 0, 0)
                self._mm.seek(0)
                self._mm.write(header)

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

            # Seqlock write. Committed sequences are EVEN; the intermediate
            # ODD value marks a write in progress. We move only the seq and
            # length fields (a whole-header rewrite isn't atomic); MAGIC and
            # VERSION are written once at init and never change.
            in_progress = self.last_sequence + 1  # odd
            committed = self.last_sequence + 2     # even

            # 1. Mark write in progress (odd). Readers seeing this skip the frame.
            self._mm.seek(SEQ_OFFSET)
            self._mm.write(struct.pack("@Q", in_progress))

            # 2. Write payload, then length. Both land before the commit, so any
            # reader that later observes the even sequence sees a matching length
            # and intact data (x86 TSO orders the stores).
            self._mm.seek(HEADER_SIZE)
            self._mm.write(data)
            self._mm.seek(LEN_OFFSET)
            self._mm.write(struct.pack("@I", data_len))

            # 3. Commit (even). On x86-64 the 8-byte-aligned sequence lands as a
            # single atomic 64-bit store, so this publishes the frame cleanly.
            # Correctness does not depend on that, though: Python's mmap.write()
            # makes no cross-platform atomicity promise, and the reader's seqlock
            # retry (step 4 in read_event: seq1 == seq2, skip odd) rejects any
            # torn read regardless of how the store decomposes on other targets.
            self._mm.seek(SEQ_OFFSET)
            self._mm.write(struct.pack("@Q", committed))

            self.last_sequence = committed

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

            # Skip if uninitialized (seq1 == 0), mid-write (odd = in-progress
            # marker), or already seen (== last read sequence).
            if seq1 == 0 or (seq1 & 1) == 1 or seq1 == self.last_sequence:
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
