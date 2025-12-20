#!/usr/bin/env python3
"""
Aether Client Library
=====================

Read live audio analysis from Aether daemon via shared memory.
Uses the existing AetherSharedMemory protocol for compatibility.

Usage:
    from aether_client import AetherClient

    client = AetherClient()
    bands = client.get_bands()

    print(f"Bass: {bands['bass']:.2f}")
    print(f"Total Energy: {bands['total']:.2f}")

Command-line usage:
    $ aether-query --band bass
    0.73

    $ aether-query --json
    {"sub_bass": 0.12, "bass": 0.73, ...}
"""

import sys
import json
import time
import os
from typing import Dict, Optional

# Import existing SHM implementation
try:
    from aether_shm import AetherSharedMemory
except ImportError:
    print("Error: aether_shm.py must be in Python path", file=sys.stderr)
    print(
        "Run: sudo cp aether_shm.py /usr/local/lib/python$(python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")')/site-packages/",
        file=sys.stderr,
    )
    sys.exit(1)


class AetherClient:
    """Client for reading live audio analysis from Aether daemon."""

    BAND_NAMES = [
        "sub_bass",  # 20-60 Hz
        "bass",  # 60-250 Hz
        "low_mid",  # 250-500 Hz
        "mid",  # 500-2000 Hz
        "high_mid",  # 2000-4000 Hz
        "treble",  # 4000-8000 Hz
        "sparkle",  # 8000-16000 Hz (NOTE: Not 'presence')
    ]

    def __init__(self):
        """Initialize Aether client using existing SHM protocol."""
        self.shm = AetherSharedMemory(is_writer=False)
        self._last_event = None

    def connect(self) -> bool:
        """
        Check if Aether daemon is running.

        Returns:
            True if shared memory is available, False otherwise
        """
        return self.shm.is_available()

    def get_bands(self) -> Optional[Dict[str, float]]:
        """
        Read current frequency band energies.

        Returns:
            Dictionary mapping band names to energy values (0.0-1.0),
            or None if daemon is not running or no data available.
        """
        event = self.shm.read_event()

        if event and "bands" in event:
            self._last_event = event
            return event["bands"]

        return None

    def get_band(self, band_name: str) -> float:
        """
        Get energy for a specific frequency band.

        Args:
            band_name: One of: sub_bass, bass, low_mid, mid, high_mid, treble, sparkle, total

        Returns:
            Energy value (0.0-1.0), or 0.0 if unavailable
        """
        bands = self.get_bands()
        return bands.get(band_name, 0.0) if bands else 0.0

    def get_total_energy(self) -> float:
        """Get total audio energy across all bands."""
        bands = self.get_bands()
        return bands.get("total", 0.0) if bands else 0.0

    def get_timestamp(self) -> Optional[float]:
        """Get timestamp of last audio event."""
        if self._last_event:
            return self._last_event.get("timestamp")
        return None

    def close(self):
        """Close shared memory connection."""
        self.shm.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def main():
    """Command-line interface for querying Aether daemon."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Query live audio analysis from Aether daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aether-query --band bass          # Get bass frequency energy
  aether-query --json               # Get all bands as JSON
  aether-query --monitor            # Live monitoring mode
  aether-query --bars               # ASCII bar chart
  
Band names:
  sub_bass, bass, low_mid, mid, high_mid, treble, sparkle, total
        """,
    )

    parser.add_argument("--band", type=str, help="Get specific frequency band value")

    parser.add_argument("--json", action="store_true", help="Output all bands as JSON")

    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Live monitoring mode (updates continuously)",
    )

    parser.add_argument("--bars", action="store_true", help="Display ASCII bar chart")

    args = parser.parse_args()

    client = AetherClient()

    if not client.connect():
        print("Error: Aether daemon not running", file=sys.stderr)
        print("Start with: ./aether-start.sh daemon", file=sys.stderr)
        sys.exit(1)

    try:
        if args.monitor:
            # Live monitoring mode
            while True:
                os.system("clear")
                bands = client.get_bands()

                if bands:
                    print("🎵 Aether Live Audio Analysis")
                    print("=" * 50)
                    for name in AetherClient.BAND_NAMES + ["total"]:
                        value = bands.get(name, 0.0)
                        bar_length = int(value * 40)
                        bar = "█" * bar_length + "░" * (40 - bar_length)
                        print(f"{name:12s}: {bar} {value:.3f}")

                    timestamp = client.get_timestamp()
                    if timestamp:
                        print(f"\nTimestamp: {timestamp:.3f}")

                    print("\nPress Ctrl+C to stop")
                else:
                    print("Waiting for audio data...")

                time.sleep(0.1)

        elif args.bars:
            # ASCII bar chart (single frame)
            bands = client.get_bands()
            if bands:
                for name in AetherClient.BAND_NAMES + ["total"]:
                    value = bands.get(name, 0.0)
                    bar_length = int(value * 40)
                    bar = "█" * bar_length + "░" * (40 - bar_length)
                    print(f"{name:12s}: {bar} {value:.3f}")
            else:
                print("No audio data available")

        elif args.json:
            # JSON output
            bands = client.get_bands()
            if bands:
                print(json.dumps(bands, indent=2))
            else:
                print("{}")

        elif args.band:
            # Single band value
            value = client.get_band(args.band)
            print(f"{value:.3f}")

        else:
            # Default: show all bands (simple format)
            bands = client.get_bands()
            if bands:
                for name in AetherClient.BAND_NAMES + ["total"]:
                    value = bands.get(name, 0.0)
                    print(f"{name}: {value:.3f}")
            else:
                print("No audio data available")

    except KeyboardInterrupt:
        print("\nStopped")

    finally:
        client.close()


if __name__ == "__main__":
    main()
