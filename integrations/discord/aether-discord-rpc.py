#!/usr/bin/env python3
"""
Aether Discord Rich Presence
Show live audio analysis in Discord status
"""

import time
import sys

try:
    from pypresence import Presence
except ImportError:
    print("Error: pypresence not installed", file=sys.stderr)
    print("Install with: pip install pypresence", file=sys.stderr)
    sys.exit(1)

try:
    from aether_client import AetherClient
except ImportError:
    print("Error: aether_client not installed", file=sys.stderr)
    sys.exit(1)

# Discord Application Configuration
# Create your app at: https://discord.com/developers/applications
CLIENT_ID = "1234567890123456789"  # Replace with your Discord app client ID

# Update interval (seconds)
UPDATE_INTERVAL = 5


def classify_music(bands):
    """Classify music genre based on frequency profile"""
    if not bands:
        return "🎵 No Audio", "Waiting for sound..."

    bass = bands.get("bass", 0)
    mid = bands.get("mid", 0)
    treble = bands.get("treble", 0)
    total = bands.get("total", 0)

    # Genre classification based on frequency distribution
    if bass > 0.7:
        return "🎧 Bass-Heavy", "EDM / Dubstep / Trap"
    elif mid > 0.6 and bass > 0.4:
        return "🎸 Guitar-Driven", "Rock / Metal"
    elif treble > 0.5 and mid > 0.4:
        return "🎹 Bright & Crisp", "Pop / Electronic"
    elif total < 0.2:
        return "🎵 Quiet", "Ambient / Silent"
    else:
        return "🎶 Balanced", "Acoustic / Mixed"


def format_energy_bar(value, length=10):
    """Create ASCII bar graph for energy level"""
    filled = int(value * length)
    return "█" * filled + "░" * (length - filled)


def main():
    # Initialize Discord RPC
    try:
        rpc = Presence(CLIENT_ID)
        rpc.connect()
        print("✓ Connected to Discord")
    except Exception as e:
        print(f"Error connecting to Discord: {e}", file=sys.stderr)
        print("Make sure Discord is running and CLIENT_ID is correct", file=sys.stderr)
        sys.exit(1)

    # Initialize Aether client
    client = AetherClient()

    if not client.connect():
        print("Warning: Aether daemon not running", file=sys.stderr)
        print("Status will update when daemon starts", file=sys.stderr)

    print("🎵 Aether Discord RPC active")
    print(f"   Update interval: {UPDATE_INTERVAL}s")
    print("   Press Ctrl+C to stop")

    try:
        while True:
            bands = client.get_bands()

            if bands:
                genre_emoji, genre_name = classify_music(bands)
                total = bands["total"]
                energy_bar = format_energy_bar(total)

                rpc.update(
                    state=f"{genre_emoji} {genre_name}",
                    details=f"Energy: {energy_bar} {total:.2f}",
                    large_image="aether_logo",  # Upload image to Discord app
                    large_text="Aether Audio Visualizer",
                    small_image="music_note",
                    small_text=f"Bass: {bands['bass']:.2f}",
                )

                print(f"Updated: {genre_emoji} {genre_name} | Energy: {total:.2f}")
            else:
                rpc.update(
                    state="🎵 Waiting for audio...",
                    details="Aether daemon inactive",
                    large_image="aether_logo",
                    large_text="Aether Audio Visualizer",
                )

            time.sleep(UPDATE_INTERVAL)

    except KeyboardInterrupt:
        print("\n✓ Stopped")
        rpc.close()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        rpc.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
