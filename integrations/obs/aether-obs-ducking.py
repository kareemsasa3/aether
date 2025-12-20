#!/usr/bin/env python3
"""
Aether OBS Auto-Ducking
Automatically adjust microphone volume when music plays
"""

import time
import sys

try:
    import obsws_python as obs
except ImportError:
    print("Error: obs-websocket-py not installed", file=sys.stderr)
    print("Install with: pip install obs-websocket-py", file=sys.stderr)
    sys.exit(1)

try:
    from aether_client import AetherClient
except ImportError:
    print("Error: aether_client not installed", file=sys.stderr)
    sys.exit(1)

# OBS WebSocket Configuration
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "your-password-here"  # Set in OBS: Tools → WebSocket Server Settings

# Audio source names (must match OBS exactly)
MIC_SOURCE = "Microphone"  # Your mic input source
MUSIC_SOURCE = "Desktop Audio"  # System audio capture

# Ducking configuration
MUSIC_THRESHOLD = 0.4  # Music energy level to trigger ducking
MIC_NORMAL_DB = 0.0  # Normal mic volume (dB)
MIC_DUCKED_DB = -12.0  # Reduced mic volume when music plays (dB)
CHECK_INTERVAL = 0.05  # Check frequency (seconds)


def db_to_mul(db):
    """Convert dB to OBS multiplier (0.0-1.0)"""
    return pow(10.0, db / 20.0)


def main():
    # Connect to OBS
    try:
        client = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
        print("✓ Connected to OBS Studio")
    except Exception as e:
        print(f"Error connecting to OBS: {e}", file=sys.stderr)
        print("Make sure OBS is running with WebSocket server enabled", file=sys.stderr)
        sys.exit(1)

    # Connect to Aether
    aether = AetherClient()
    if not aether.connect():
        print("Error: Aether daemon not running", file=sys.stderr)
        sys.exit(1)

    print("🎙️  Aether OBS Auto-Ducking active")
    print(f"   Music threshold: {MUSIC_THRESHOLD}")
    print(f"   Mic normal: {MIC_NORMAL_DB} dB")
    print(f"   Mic ducked: {MIC_DUCKED_DB} dB")
    print("   Press Ctrl+C to stop")

    currently_ducked = False

    try:
        while True:
            bands = aether.get_bands()

            if bands:
                total_energy = bands["total"]

                # Check if music is playing
                should_duck = total_energy > MUSIC_THRESHOLD

                if should_duck and not currently_ducked:
                    # Duck the microphone
                    volume_mul = db_to_mul(MIC_DUCKED_DB)
                    client.set_input_volume(MIC_SOURCE, volume_mul)
                    currently_ducked = True
                    print(
                        f"🔉 Ducked mic to {MIC_DUCKED_DB} dB (music: {total_energy:.2f})"
                    )

                elif not should_duck and currently_ducked:
                    # Restore microphone
                    volume_mul = db_to_mul(MIC_NORMAL_DB)
                    client.set_input_volume(MIC_SOURCE, volume_mul)
                    currently_ducked = False
                    print(f"🔊 Restored mic to {MIC_NORMAL_DB} dB")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        # Restore mic volume on exit
        if currently_ducked:
            volume_mul = db_to_mul(MIC_NORMAL_DB)
            client.set_input_volume(MIC_SOURCE, volume_mul)
            print(f"\n✓ Mic restored to {MIC_NORMAL_DB} dB")
        print("✓ Stopped")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
