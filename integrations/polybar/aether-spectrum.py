#!/usr/bin/env python3
"""Polybar module - live frequency spectrum bars"""

from aether_client import AetherClient


def main():
    client = AetherClient()

    if not client.connect():
        print("-------")
        return

    bands = client.get_bands()

    if not bands:
        print("-------")
        return

    # Unicode block characters for bar chart
    chars = " ▁▂▃▄▅▆▇█"

    # Create spectrum visualization
    bars = []
    for name in ["sub_bass", "bass", "low_mid", "mid", "high_mid", "treble", "sparkle"]:
        value = bands.get(name, 0.0)
        height = min(8, int(value * 9))
        bars.append(chars[height])

    print("".join(bars))


if __name__ == "__main__":
    main()
