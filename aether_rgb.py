#!/home/kareem/code/aether/venv/bin/python3
# aether_rgb.py - Traveling wave RGB effect with multi-band audio analysis
import time
import sys
import signal
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from aether_shm import AetherSharedMemory, read_event_legacy


class AetherRGB:
    """RGB controller with traveling wave effect for 311 individual LEDs"""

    # Band to color mapping for spectrum visualization
    BAND_COLORS = {
        "sub_bass": (75, 0, 130),  # Deep purple (Indigo)
        "bass": (138, 43, 226),  # Blue-violet
        "low_mid": (0, 0, 255),  # Blue
        "mid": (0, 255, 255),  # Cyan
        "high_mid": (0, 255, 0),  # Green
        "treble": (255, 255, 0),  # Yellow
        "sparkle": (255, 140, 0),  # Orange
    }

    # RAM spectrum: 5 bands mapped to 5 LEDs
    RAM_BAND_MAPPING = [
        ("sub_bass", (75, 0, 130)),
        ("bass", (138, 43, 226)),
        ("mid", (0, 255, 255)),
        ("high_mid", (0, 255, 0)),
        ("treble", (255, 255, 0)),
    ]

    def __init__(self):
        # OpenRGB connection
        try:
            self.client = OpenRGBClient()
            print("[RGB] Connected to OpenRGB")
        except Exception as e:
            print(f"[ERROR] Could not connect to OpenRGB: {e}")
            print("Make sure OpenRGB is running with --server flag")
            sys.exit(1)

        # Get devices
        self.devices = self.client.devices
        self.setup_devices()

        # Event tracking
        # Event tracking
        self.event_file = "/tmp/aether_last_event.json"
        self.last_event_sequence_time = 0  # For legacy file polling
        self.last_audio_timestamp = 0  # For decay logic (silence detection)

        # Initialize Shared Memory Reader
        self.shm = AetherSharedMemory(is_writer=False)

        # Traveling wave buffer for motherboard (300 LEDs)
        # Each entry is an RGBColor that shifts left each frame
        self.mobo_led_count = 300
        self.wave_buffer = [RGBColor(0, 0, 0) for _ in range(self.mobo_led_count)]

        # Signal handling
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print(f"[RGB] Found {len(self.devices)} devices")
        for idx, device in enumerate(self.devices):
            print(
                f"  [{idx}] {device.name} ({device.type.name}) - {len(device.leds)} LEDs"
            )
        print("\n[RGB] Device mapping:")
        print("  [0,1] RAM sticks (5 LEDs each) → Mini spectrum")
        print("  [2]   Mouse logo (1 LED) → Brightness indicator")
        print("  [3]   Motherboard (300 LEDs) → Traveling wave")

    def setup_devices(self):
        """Set all devices to Direct mode for per-LED control"""
        for device in self.devices:
            try:
                # Find Direct mode
                direct_mode = None
                for mode in device.modes:
                    if mode.name.lower() == "direct":
                        direct_mode = mode
                        break

                if direct_mode:
                    device.set_mode(direct_mode)
                    print(f"[RGB] Set {device.name} to Direct mode")
                else:
                    print(f"[WARNING] {device.name} has no Direct mode")
            except Exception as e:
                print(f"[WARNING] Could not set {device.name} to Direct: {e}")

    def signal_handler(self, sig, frame):
        print("\n[RGB] Shutting down...")
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        """Reset all LEDs to off"""
        try:
            for device in self.devices:
                device.set_color(RGBColor(0, 0, 0))
            print("[RGB] All LEDs off")
        except Exception:
            pass

    def bands_to_spectrum_color(self, bands):
        """Convert frequency bands to a blended rainbow color.

        Each band contributes its characteristic color weighted by energy.
        Creates a rich, shifting color that represents the full audio spectrum.
        """
        r, g, b = 0.0, 0.0, 0.0
        total_weight = 0.0

        for band_name, (cr, cg, cb) in self.BAND_COLORS.items():
            weight = bands.get(band_name, 0)
            r += cr * weight
            g += cg * weight
            b += cb * weight
            total_weight += weight

        # Normalize to prevent overflow
        if total_weight > 0:
            r = min(255, int(r / total_weight))
            g = min(255, int(g / total_weight))
            b = min(255, int(b / total_weight))
        else:
            r, g, b = 0, 0, 0

        # Boost brightness based on total energy for more punch
        total_energy = bands.get("total", 0)
        brightness = min(1.0, total_energy * 2.5)  # Boost for visibility
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)

        return RGBColor(r, g, b)

    def update_traveling_wave(self, bands):
        """Update the traveling wave effect on motherboard (300 LEDs).

        The wave buffer shifts left each frame, and a new color based on
        current audio is added at the end. This creates a flowing rainbow
        waterfall effect where newest audio is on one end and fades out.
        """
        # Get new color from current audio spectrum
        new_color = self.bands_to_spectrum_color(bands)

        # Shift buffer left (wave travels from right to left)
        self.wave_buffer = self.wave_buffer[1:] + [new_color]

        # Apply to motherboard LEDs
        if len(self.devices) > 3:
            mobo = self.devices[3]  # ASUS motherboard
            try:
                # Set each LED individually
                for i, color in enumerate(self.wave_buffer):
                    if i < len(mobo.leds):
                        mobo.leds[i].set_color(color)
                mobo.update()
            except Exception:
                # Fallback: set whole device if per-LED fails
                try:
                    mobo.set_color(new_color)
                except Exception:
                    pass

    def update_ram_spectrum(self, bands):
        """Show mini frequency spectrum on RAM LEDs (5 LEDs each).

        Each LED represents a frequency band:
        LED 1 = sub_bass (purple), LED 2 = bass (violet), LED 3 = mid (cyan),
        LED 4 = high_mid (green), LED 5 = treble (yellow)
        Brightness of each LED = energy in that band.
        """
        # Apply to both RAM sticks (devices 0 and 1)
        for device_idx in [0, 1]:
            if device_idx < len(self.devices):
                ram_device = self.devices[device_idx]
                try:
                    for led_idx, (band_name, (r, g, b)) in enumerate(
                        self.RAM_BAND_MAPPING
                    ):
                        if led_idx < len(ram_device.leds):
                            energy = bands.get(band_name, 0)
                            # Scale color by band energy (brightness = energy)
                            color = RGBColor(
                                int(r * energy), int(g * energy), int(b * energy)
                            )
                            ram_device.leds[led_idx].set_color(color)
                    ram_device.update()
                except Exception:
                    # Fallback: set whole device to dominant color
                    try:
                        dominant_color = self.bands_to_spectrum_color(bands)
                        ram_device.set_color(dominant_color)
                    except Exception:
                        pass

    def update_mouse_brightness(self, bands):
        """Show overall audio energy on mouse logo LED.

        Single white LED that pulses based on total audio energy.
        """
        total = bands.get("total", 0)

        # White color scaled by total energy
        brightness = int(255 * min(1.0, total * 2.5))  # Boost for visibility
        color = RGBColor(brightness, brightness, brightness)

        if len(self.devices) > 2:
            mouse = self.devices[2]  # Razer Viper
            try:
                mouse.set_color(color)
            except Exception:
                pass

    def check_for_events(self):
        """Poll for audio events and update all LED rendering strategies"""
        event = None

        # 1. Try Shared Memory (Fast path)
        if self.shm.is_available():
            event = self.shm.read_event()

        # 2. If no SHM event, check Legacy File (Slow path)
        if event is None:
            legacy_event, mtime = read_event_legacy()
            if legacy_event and mtime > self.last_event_sequence_time:
                self.last_event_sequence_time = mtime
                event = legacy_event

        if event:
            # We have fresh data! Update silence tracker
            self.last_audio_timestamp = time.time()

            if event.get("type") == "audio" and "bands" in event:
                bands = event["bands"]

                # Update all three rendering strategies
                self.update_traveling_wave(bands)
                self.update_ram_spectrum(bands)
                self.update_mouse_brightness(bands)

                # Debug output
                total = bands.get("total", 0)
                bar = "█" * int(total * 20)
                print(
                    f"[RGB] Wave flowing | {bar:20s} | Total: {total:.2f}",
                    end="\r",
                )

    def decay_wave(self):
        """Gradually fade the wave buffer when no new audio.

        This creates a smooth fade-out effect instead of abrupt stop.
        """
        # Shift buffer left with a faded black color
        faded_color = RGBColor(0, 0, 0)
        self.wave_buffer = self.wave_buffer[1:] + [faded_color]

        # Apply to motherboard
        if len(self.devices) > 3:
            mobo = self.devices[3]
            try:
                for i, color in enumerate(self.wave_buffer):
                    if i < len(mobo.leds):
                        mobo.leds[i].set_color(color)
                mobo.update()
            except Exception:
                pass

        # Fade RAM and mouse
        for device_idx in [0, 1, 2]:
            if device_idx < len(self.devices):
                try:
                    self.devices[device_idx].set_color(RGBColor(0, 0, 0))
                except Exception:
                    pass

    def run(self):
        """Main loop - 20 FPS update rate"""
        print("\n[RGB] Listening for audio events...")
        print("[RGB] Rendering strategies active:")
        print("      • Motherboard: Traveling rainbow wave (300 LEDs)")
        print("      • RAM sticks: 5-band mini spectrum")
        print("      • Mouse logo: Volume brightness indicator")
        print("[RGB] Press Ctrl+C to stop\n")

        decay_counter = 0

        try:
            while True:
                current_time = time.time()

                # Check for new events
                self.check_for_events()

                # If no new events for a while, start decay
                # If no new events for a while, start decay
                if (
                    current_time - self.last_audio_timestamp > 0.1
                ):  # 100ms without audio
                    decay_counter += 1
                    if decay_counter > 5:  # Start decay after ~250ms
                        self.decay_wave()
                else:
                    decay_counter = 0

                time.sleep(0.05)  # 20 FPS
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()


def main():
    rgb = AetherRGB()
    rgb.run()


if __name__ == "__main__":
    main()
