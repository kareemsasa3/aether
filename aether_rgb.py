#!/usr/bin/env python3
# aether_rgb.py - Traveling wave RGB effect with multi-band audio analysis
import time
import sys
import signal
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
from aether_shm import AetherSharedMemory, read_event_legacy


class AetherRGB:
    """RGB controller with traveling wave effect for individual LEDs"""

    # Target FPS for RGB updates (higher = smoother but more CPU)
    TARGET_FPS = 30
    FRAME_TIME = 1.0 / TARGET_FPS

    # Decay factor for smooth fade-out (0.0-1.0, higher = slower fade)
    DECAY_FACTOR = 0.85

    # Brightness multiplier (consistent across all devices)
    BRIGHTNESS_BOOST = 2.5

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

    # Band order for spatial mapping
    BAND_ORDER = ["sub_bass", "bass", "low_mid", "mid", "high_mid", "treble", "sparkle"]

    # RAM spectrum: 5 bands mapped to 5 LEDs
    RAM_BAND_MAPPING = [
        ("sub_bass", (75, 0, 130)),
        ("bass", (138, 43, 226)),
        ("mid", (0, 255, 255)),
        ("high_mid", (0, 255, 0)),
        ("treble", (255, 255, 0)),
    ]

    def __init__(self):
        # OpenRGB connection with retry
        self.client = None
        self._connect_openrgb()

        # Get devices and categorize them by type
        self.devices = self.client.devices
        self.ram_devices = []
        self.mouse_device = None
        self.mobo_device = None

        # Categorize devices by type
        for device in self.devices:
            if device.type.name == "DRAM":
                self.ram_devices.append(device)
            elif device.type.name == "MOUSE":
                self.mouse_device = device
            elif device.type.name == "MOTHERBOARD":
                self.mobo_device = device

        self.setup_devices()

        # Initialize color state arrays for smooth decay
        # We track current colors ourselves since OpenRGB can't read back
        self._init_color_state()

        # Event tracking
        self.event_file = "/tmp/aether_last_event.json"
        self.last_event_sequence_time = 0  # For legacy file polling
        self.last_audio_timestamp = 0  # For decay logic (silence detection)
        self.shm_retry_counter = 0  # Counter for retrying SHM initialization
        self.got_new_event = False  # Track if we got a NEW event this frame

        # Initialize Shared Memory Reader
        self.shm = AetherSharedMemory(is_writer=False)

        # Signal handling
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print(f"[RGB] Found {len(self.devices)} devices")
        for idx, device in enumerate(self.devices):
            print(
                f"  [{idx}] {device.name} ({device.type.name}) - {len(device.leds)} LEDs"
            )
        print("\n[RGB] Device mapping:")
        print(f"  RAM: {len(self.ram_devices)} stick(s) → Mini spectrum")
        print(f"  Mouse: {'Yes' if self.mouse_device else 'No'} → Brightness indicator")
        print(f"  Motherboard: {'Yes' if self.mobo_device else 'No'} → Spatial spectrum analyzer")

    def _connect_openrgb(self, max_retries=3):
        """Connect to OpenRGB with retry logic"""
        for attempt in range(max_retries):
            try:
                self.client = OpenRGBClient()
                print("[RGB] Connected to OpenRGB")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[RGB] Connection attempt {attempt + 1} failed, retrying...")
                    time.sleep(1)
                else:
                    print(f"[ERROR] Could not connect to OpenRGB: {e}")
                    print("Make sure OpenRGB is running with --server flag")
                    sys.exit(1)

    def _init_color_state(self):
        """Initialize color state arrays for tracking current LED colors"""
        # Motherboard colors: list of (r, g, b) tuples
        if self.mobo_device:
            self.mobo_colors = [(0, 0, 0)] * len(self.mobo_device.leds)
        else:
            self.mobo_colors = []

        # RAM colors: dict of device -> color list
        self.ram_colors = {}
        for ram in self.ram_devices:
            self.ram_colors[id(ram)] = [(0, 0, 0)] * len(ram.leds)

        # Mouse color: single (r, g, b)
        self.mouse_color = (0, 0, 0)

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
        brightness = min(1.0, total_energy * 5.0)  # Boost for visibility
        r = min(255, int(r * brightness * 2.0))
        g = min(255, int(g * brightness * 2.0))
        b = min(255, int(b * brightness * 2.0))

        return RGBColor(r, g, b)

    def update_traveling_wave(self, bands):
        """Map motherboard sections to frequency bands for spatial spectrum.

        Each section of LEDs represents a different frequency band, creating
        a rainbow spectrum that pulses with the energy of each band.
        Uses bulk color updates for efficiency.
        """
        if not self.mobo_device:
            return

        try:
            num_leds = len(self.mobo_device.leds)
            num_bands = len(self.BAND_ORDER)

            # Calculate LED distribution to cover ALL LEDs
            # Use ceiling division to ensure we cover everything
            base_leds = num_leds // num_bands
            extra_leds = num_leds % num_bands

            led_idx = 0
            for band_idx, band_name in enumerate(self.BAND_ORDER):
                energy = bands.get(band_name, 0)
                base_r, base_g, base_b = self.BAND_COLORS[band_name]

                # Calculate target color with consistent brightness boost
                target_r = min(255, int(base_r * energy * self.BRIGHTNESS_BOOST))
                target_g = min(255, int(base_g * energy * self.BRIGHTNESS_BOOST))
                target_b = min(255, int(base_b * energy * self.BRIGHTNESS_BOOST))

                # Distribute extra LEDs among first bands
                section_size = base_leds + (1 if band_idx < extra_leds else 0)

                # Update color state for this section
                for i in range(section_size):
                    if led_idx < num_leds:
                        self.mobo_colors[led_idx] = (target_r, target_g, target_b)
                        led_idx += 1

            # Bulk update all LEDs at once (much faster than per-LED)
            colors = [RGBColor(r, g, b) for r, g, b in self.mobo_colors]
            self.mobo_device.set_colors(colors)

        except Exception as e:
            # Fallback: set whole device to dominant color
            try:
                dominant_color = self.bands_to_spectrum_color(bands)
                self.mobo_device.set_color(dominant_color)
            except Exception:
                pass

    def update_ram_spectrum(self, bands):
        """Show mini frequency spectrum on RAM LEDs (5 LEDs each).

        Each LED represents a frequency band:
        LED 1 = sub_bass (purple), LED 2 = bass (violet), LED 3 = mid (cyan),
        LED 4 = high_mid (green), LED 5 = treble (yellow)
        Brightness of each LED = energy in that band.
        Uses bulk color updates for efficiency.
        """
        for ram_device in self.ram_devices:
            try:
                device_id = id(ram_device)
                colors_state = self.ram_colors.get(device_id, [(0, 0, 0)] * len(ram_device.leds))

                for led_idx, (band_name, (base_r, base_g, base_b)) in enumerate(
                    self.RAM_BAND_MAPPING
                ):
                    if led_idx < len(ram_device.leds):
                        energy = bands.get(band_name, 0)
                        # Scale color with consistent brightness boost
                        target_r = min(255, int(base_r * energy * self.BRIGHTNESS_BOOST))
                        target_g = min(255, int(base_g * energy * self.BRIGHTNESS_BOOST))
                        target_b = min(255, int(base_b * energy * self.BRIGHTNESS_BOOST))
                        colors_state[led_idx] = (target_r, target_g, target_b)

                # Update state
                self.ram_colors[device_id] = colors_state

                # Bulk update
                colors = [RGBColor(r, g, b) for r, g, b in colors_state]
                ram_device.set_colors(colors)

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
        if not self.mouse_device:
            return

        total = bands.get("total", 0)

        # White color scaled by total energy with consistent boost
        brightness = min(255, int(255 * total * self.BRIGHTNESS_BOOST))
        self.mouse_color = (brightness, brightness, brightness)

        try:
            self.mouse_device.set_color(RGBColor(*self.mouse_color))
        except Exception:
            pass

    def check_for_events(self):
        """Poll for audio events and update all LED rendering strategies.
        
        Returns True if a new event was processed, False otherwise.
        """
        event = None
        self.got_new_event = False

        # Retry shared memory initialization if it wasn't available at startup
        # (daemon might start after RGB controller)
        if not self.shm.is_available():
            self.shm_retry_counter += 1
            # Retry every 75 frames (~2.5 seconds at 30 FPS)
            if self.shm_retry_counter % 75 == 0:
                try:
                    # Try to re-initialize shared memory
                    self.shm._init_shm()
                    if self.shm.is_available():
                        print("\n[RGB] Shared memory connection established!", flush=True)
                except Exception:
                    pass

        # 1. Try Shared Memory (Fast path)
        if self.shm.is_available():
            try:
                event = self.shm.read_event()
            except Exception as e:
                # If read fails, shared memory might be corrupted, try legacy
                print(f"\n[RGB] SHM read error: {e}", flush=True)
                event = None

        # 2. If no SHM event, check Legacy File (Slow path)
        if event is None:
            legacy_event, mtime = read_event_legacy()
            if legacy_event and mtime > self.last_event_sequence_time:
                self.last_event_sequence_time = mtime
                event = legacy_event

        if event and event.get("type") == "audio" and "bands" in event:
            # We have fresh audio data!
            self.got_new_event = True
            self.last_audio_timestamp = time.time()

            bands = event["bands"]

            # Update all three rendering strategies
            self.update_traveling_wave(bands)
            self.update_ram_spectrum(bands)
            self.update_mouse_brightness(bands)

            # Visual feedback (single line, overwrite)
            total = bands.get("total", 0)
            bar = "█" * int(total * 20)
            print(
                f"\r[RGB] Spectrum active | {bar:20s} | Total: {total:.2f}",
                end="",
                flush=True,
            )

        return self.got_new_event

    def decay_wave(self):
        """Gradually fade all LEDs when no new audio.

        Applies exponential decay to tracked color state for smooth fade-out.
        """
        decay = self.DECAY_FACTOR

        # Fade motherboard with smooth decay
        if self.mobo_device and self.mobo_colors:
            try:
                # Apply decay to each color component
                self.mobo_colors = [
                    (int(r * decay), int(g * decay), int(b * decay))
                    for r, g, b in self.mobo_colors
                ]
                # Bulk update
                colors = [RGBColor(r, g, b) for r, g, b in self.mobo_colors]
                self.mobo_device.set_colors(colors)
            except Exception:
                pass

        # Fade RAM devices with smooth decay
        for ram_device in self.ram_devices:
            try:
                device_id = id(ram_device)
                if device_id in self.ram_colors:
                    self.ram_colors[device_id] = [
                        (int(r * decay), int(g * decay), int(b * decay))
                        for r, g, b in self.ram_colors[device_id]
                    ]
                    colors = [RGBColor(r, g, b) for r, g, b in self.ram_colors[device_id]]
                    ram_device.set_colors(colors)
            except Exception:
                pass

        # Fade mouse with smooth decay
        if self.mouse_device:
            try:
                r, g, b = self.mouse_color
                self.mouse_color = (int(r * decay), int(g * decay), int(b * decay))
                self.mouse_device.set_color(RGBColor(*self.mouse_color))
            except Exception:
                pass

    def run(self):
        """Main loop - 30 FPS update rate for smooth animations"""
        mobo_leds = len(self.mobo_device.leds) if self.mobo_device else 0
        
        print(f"\n[RGB] Listening for audio events at {self.TARGET_FPS} FPS...")
        print("[RGB] Rendering strategies active:")
        print(f"      • Motherboard: Spatial spectrum analyzer ({mobo_leds} LEDs)")
        print(f"      • RAM sticks: {len(self.ram_devices)}x 5-band mini spectrum")
        print(f"      • Mouse logo: {'Yes' if self.mouse_device else 'No'} - Volume brightness")
        
        # Show connection status
        if self.shm.is_available():
            print("[RGB] ✓ Shared memory connected")
        else:
            print("[RGB] ⚠ Shared memory not available, using legacy file I/O")
            print("[RGB]   (Will retry connection every 2.5 seconds)")
        
        print("[RGB] Press Ctrl+C to stop\n")

        frames_without_event = 0
        silence_threshold_frames = int(0.1 * self.TARGET_FPS)  # 100ms worth of frames

        try:
            while True:
                frame_start = time.perf_counter()

                # Check for new events
                got_event = self.check_for_events()

                if got_event:
                    frames_without_event = 0
                else:
                    frames_without_event += 1
                    
                    # Apply decay if we've had silence for a bit
                    if frames_without_event > silence_threshold_frames:
                        self.decay_wave()

                # Warning if no events for extended period
                if frames_without_event == self.TARGET_FPS * 10:  # 10 seconds
                    print("\n[RGB] ⚠ No audio events received for 10 seconds", flush=True)
                    print("[RGB]   Make sure aether_daemon.py is running", flush=True)

                # Maintain stable frame rate
                elapsed = time.perf_counter() - frame_start
                sleep_time = max(0, self.FRAME_TIME - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\n[RGB] Error in main loop: {e}", flush=True)
        finally:
            self.cleanup()


def main():
    rgb = AetherRGB()
    rgb.run()


if __name__ == "__main__":
    main()
