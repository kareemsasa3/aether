#!/usr/bin/env python3
"""Auto-pause notifications during heavy bass"""

import time
import subprocess
import sys

try:
    from aether_client import AetherClient
except ImportError:
    print("Error: aether_client not installed", file=sys.stderr)
    sys.exit(1)

# Configuration
BASS_THRESHOLD = 0.75  # Bass level to trigger pause
PAUSE_DURATION = 1.5  # Seconds to stay paused
CHECK_INTERVAL = 0.1  # Check frequency (seconds)


def main():
    client = AetherClient()

    if not client.connect():
        print("Error: Aether daemon not running", file=sys.stderr)
        sys.exit(1)

    print("🔕 Aether notification pauser active")
    print(f"   Bass threshold: {BASS_THRESHOLD}")
    print("   Press Ctrl+C to stop")

    paused_until = 0

    try:
        while True:
            current_time = time.time()
            bass = client.get_band("bass")

            if bass > BASS_THRESHOLD and current_time > paused_until:
                # Heavy bass - pause notifications
                subprocess.run(
                    ["dunstctl", "set-paused", "true"], capture_output=True, check=False
                )
                paused_until = current_time + PAUSE_DURATION
                print(f"🔊 Bass spike: {bass:.2f} - Paused for {PAUSE_DURATION}s")

            elif current_time > paused_until:
                # Resume notifications
                subprocess.run(
                    ["dunstctl", "set-paused", "false"],
                    capture_output=True,
                    check=False,
                )

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        # Ensure notifications are unpaused on exit
        subprocess.run(
            ["dunstctl", "set-paused", "false"], capture_output=True, check=False
        )
        print("\n✓ Stopped - notifications resumed")


if __name__ == "__main__":
    main()
