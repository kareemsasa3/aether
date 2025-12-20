#!/usr/bin/env python3
"""
Aether Philips Hue Sync
Sync smart lights to system audio in real-time
"""

import time
import sys

try:
    from phue import Bridge
except ImportError:
    print("Error: phue not installed", file=sys.stderr)
    print("Install with: pip install phue", file=sys.stderr)
    sys.exit(1)

try:
    from aether_client import AetherClient
except ImportError:
    print("Error: aether_client not installed", file=sys.stderr)
    sys.exit(1)

# Hue Bridge Configuration
BRIDGE_IP = "192.168.1.100"  # Replace with your bridge IP

# Light mapping (customize for your setup)
LIGHT_MAP = {
    "Living Room": "bass",  # Bass frequencies
    "Bedroom": "total",  # Total energy
    "Kitchen": "mid",  # Mid frequencies
    "Office": "treble",  # High frequencies
}

# Performance settings
UPDATE_FPS = 20  # Updates per second
BRIGHTNESS_MULTIPLIER = 254  # Max Hue brightness
MIN_BRIGHTNESS = 10  # Minimum brightness (prevent total darkness)


def frequency_to_hue(bands):
    """
    Map frequency spectrum to HSV color wheel

    Returns hue value (0-65535) based on dominant frequency
    """
    bass = bands.get("bass", 0)
    mid = bands.get("mid", 0)
    treble = bands.get("treble", 0)

    # Dominant frequency determines color
    if bass > mid and bass > treble:
        return 0  # Red (bass)
    elif mid > bass and mid > treble:
        return 25500  # Green (mids)
    elif treble > bass and treble > mid:
        return 46920  # Blue (treble)
    else:
        return 12750  # Cyan (balanced)


def main():
    # Connect to Hue Bridge
    try:
        bridge = Bridge(BRIDGE_IP)
        bridge.connect()
        print("✓ Connected to Philips Hue Bridge")
    except Exception as e:
        print(f"Error connecting to Hue Bridge: {e}", file=sys.stderr)
        print(
            "Make sure bridge IP is correct and you've pressed the button",
            file=sys.stderr,
        )
        sys.exit(1)

    # Get lights
    try:
        lights = bridge.get_light_objects("name")
        print(f"✓ Found {len(lights)} lights")
    except Exception as e:
        print(f"Error getting lights: {e}", file=sys.stderr)
        sys.exit(1)

    # Verify configured lights exist
    for light_name in LIGHT_MAP.keys():
        if light_name not in lights:
            print(f"Warning: Light '{light_name}' not found", file=sys.stderr)

    # Connect to Aether
    client = AetherClient()
    if not client.connect():
        print("Error: Aether daemon not running", file=sys.stderr)
        sys.exit(1)

    print("💡 Aether Hue Sync active")
    print(f"   FPS: {UPDATE_FPS}")
    print("   Light mapping:")
    for light, band in LIGHT_MAP.items():
        if light in lights:
            print(f"      {light} → {band}")
    print("   Press Ctrl+C to stop")

    frame_time = 1.0 / UPDATE_FPS

    try:
        while True:
            start_time = time.time()
            bands = client.get_bands()

            if bands:
                # Update each configured light
                for light_name, band_name in LIGHT_MAP.items():
                    if light_name not in lights:
                        continue

                    light = lights[light_name]
                    value = bands.get(band_name, 0.0)

                    # Calculate brightness (0-254)
                    brightness = max(MIN_BRIGHTNESS, int(value * BRIGHTNESS_MULTIPLIER))

                    # Calculate color
                    hue = frequency_to_hue(bands)

                    # Update light
                    try:
                        light.on = brightness > MIN_BRIGHTNESS
                        light.brightness = brightness
                        light.hue = hue
                        light.saturation = 254  # Full saturation
                    except Exception as e:
                        print(f"Error updating {light_name}: {e}", file=sys.stderr)

            # Maintain target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_time - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        # Restore lights to white on exit
        print("\n💡 Restoring lights...")
        for light_name in LIGHT_MAP.keys():
            if light_name in lights:
                lights[light_name].on = True
                lights[light_name].brightness = 254
                lights[light_name].saturation = 0  # White
        print("✓ Stopped")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
