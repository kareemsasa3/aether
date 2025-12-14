#!/home/kareem/code/aether/venv/bin/python3
# aether_daemon.py - Direct PipeWire pipeline
import subprocess
import numpy as np
import sys
import signal
import math
from aether_shm import AetherSharedMemory, write_event_legacy


class AetherDaemon:
    DEBUG = False
    # ==========================================================================
    # AUDIO PROCESSING CONSTANTS
    # ==========================================================================

    # FFT/Buffer settings
    # 2048 samples @ 48kHz = ~42.7ms latency, good balance of frequency resolution
    # vs responsiveness. Larger = better bass resolution, smaller = faster response.
    CHUNK_SIZE = 2048
    SAMPLE_RATE = 48000  # Standard professional audio rate, matches PipeWire default

    # --------------------------------------------------------------------------
    # Amplitude Thresholds
    # --------------------------------------------------------------------------
    # Minimum RMS amplitude to consider as "meaningful" audio.
    # Below this, we skip processing to avoid noise floor artifacts.
    # Empirically tuned: typical room noise is ~0.01-0.02, clear speech starts ~0.05
    # MIN_AMPLITUDE_THRESHOLD = 0.10

    # RMS normalization divisor. Converts raw 16-bit RMS (~0-32768) to 0.0-1.0 range.
    # 3000 chosen empirically: normal speech peaks at ~0.3-0.5, loud sounds hit 1.0
    RMS_NORMALIZATION_FACTOR = 3000.0

    # --------------------------------------------------------------------------
    # Logarithmic Energy Scaling Constants
    # --------------------------------------------------------------------------
    # FFT magnitude values span huge dynamic range (100K to 10M+).
    # We use log10 scaling to compress this into usable 0.0-1.0 range.
    #
    # For individual bands:
    #   - Quiet audio: log10(100K) ≈ 5.0 → maps to 0.0
    #   - Loud audio:  log10(10M)  ≈ 7.0 → maps to 1.0
    #   - Formula: normalized = (log_energy - 5.0) / 2.0
    LOG_ENERGY_MIN_BAND = 5.5  # log10 floor for individual frequency bands
    LOG_ENERGY_RANGE_BAND = 2.0  # log10 range (7.0 - 5.0 = 2.0)

    # For total energy (sum of all bands):
    #   - Higher baseline because summing 7 bands yields higher total
    #   - log10(1M) = 6.0 floor, log10(100M) = 8.0 ceiling
    LOG_ENERGY_MIN_TOTAL = 6.0  # log10 floor for total energy
    LOG_ENERGY_RANGE_TOTAL = 2.0  # log10 range (8.0 - 6.0 = 2.0)

    # --------------------------------------------------------------------------
    # Frequency Band Definitions (Hz)
    # --------------------------------------------------------------------------
    # Based on standard audio engineering frequency ranges.
    # Each band captures distinct musical/voice characteristics.
    FREQUENCY_BANDS = {
        "sub_bass": (20, 60),  # Deep rumble, sub-woofer territory
        "bass": (60, 250),  # Kick drums, bass guitar fundamentals
        "low_mid": (250, 500),  # Low vocals, guitar body, warmth
        "mid": (500, 1000),  # Main vocals, most instruments
        "high_mid": (1000, 2000),  # Presence, vocal clarity, attack
        "treble": (2000, 4000),  # Brightness, consonants, hi-hats
        "sparkle": (4000, 8000),  # Air, cymbals, sibilance
    }

    # Human hearing range used for total energy calculation
    AUDIBLE_FREQ_MIN = 20  # Lower limit of human hearing
    AUDIBLE_FREQ_MAX = 8000  # Upper limit for this analysis (avoid aliasing noise)

    # Representative center frequencies for each band (used for legacy format)
    # Geometric mean of band edges, rounded for simplicity
    BAND_CENTER_FREQUENCIES = {
        "sub_bass": 40,
        "bass": 150,
        "low_mid": 375,
        "mid": 750,
        "high_mid": 1500,
        "treble": 3000,
        "sparkle": 6000,
    }
    DEFAULT_FREQUENCY = 440  # A4 note, fallback if band lookup fails

    # --------------------------------------------------------------------------
    # Display Constants
    # --------------------------------------------------------------------------
    AMPLITUDE_BAR_WIDTH = 40  # Character width for visual amplitude bar

    def __init__(self):
        self.running = True

        # Handle Ctrl+C properly
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("[Audio Daemon V3] Using PipeWire direct pipeline")
        print("[Audio Daemon V3] Target: Razer Seiren X")
        print(f"[Audio Daemon V3] Sample rate: {self.SAMPLE_RATE} Hz")
        print("[Audio Daemon V3] Press Ctrl+C to stop\n")

        # Initialize Shared Memory
        self.shm = AetherSharedMemory(is_writer=True)
        if self.shm.is_available():
            print("[Audio Daemon V3] Shared memory IPC active")
        else:
            print(
                "[Audio Daemon V3] Warning: Shared memory unavailable, using legacy file I/O"
            )

    def signal_handler(self, sig, frame):
        print("\n\n[Audio Daemon V3] Shutting down...")
        self.running = False
        if hasattr(self, "process"):
            self.process.terminate()
        if hasattr(self, "shm"):
            self.shm.close()
        sys.exit(0)

    def get_frequency_bands(self, audio_data):
        """Analyze audio into multiple frequency bands for rich spectrum"""
        # Apply FFT
        fft = np.fft.rfft(audio_data)
        fft_magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(audio_data), 1.0 / self.SAMPLE_RATE)

        # Calculate normalized energy in each band using logarithmic scaling
        # Log scale handles the huge dynamic range of FFT values (100K - 10M+)
        band_energies = {}
        for band_name, (low, high) in self.FREQUENCY_BANDS.items():
            mask = (freqs >= low) & (freqs < high)
            energy = np.sum(fft_magnitude[mask])

            if energy > 0:
                log_energy = math.log10(energy)
                normalized = (
                    log_energy - self.LOG_ENERGY_MIN_BAND
                ) / self.LOG_ENERGY_RANGE_BAND
                band_energies[band_name] = max(0.0, min(1.0, normalized))
            else:
                band_energies[band_name] = 0.0

        # Calculate total energy for overall brightness
        total_energy = np.sum(
            fft_magnitude[
                (freqs >= self.AUDIBLE_FREQ_MIN) & (freqs < self.AUDIBLE_FREQ_MAX)
            ]
        )
        if total_energy > 0:
            log_total = math.log10(total_energy)
            normalized_total = (
                log_total - self.LOG_ENERGY_MIN_TOTAL
            ) / self.LOG_ENERGY_RANGE_TOTAL
            band_energies["total"] = max(0.0, min(1.0, normalized_total))
        else:
            band_energies["total"] = 0.0

        return band_energies

    def send_event(self, bands):
        """Send event (threshold already checked by caller)"""
        total_energy = bands.get("total", 0)

        # Find dominant band
        max_band = max(
            ((k, v) for k, v in bands.items() if k != "total"), key=lambda x: x[1]
        )
        band_name, band_value = max_band

        if total_energy < 0.10 and band_value < 0.15:
            return

        dominant_freq = self.BAND_CENTER_FREQUENCIES.get(
            band_name, self.DEFAULT_FREQUENCY
        )

        event_data = {
            "type": "audio",
            "bands": bands,
            "frequency": dominant_freq,
            "amplitude": max(total_energy, band_value),
        }

        # Try shared memory first, fall back to legacy file
        if self.shm.is_available():
            if not self.shm.write_event(event_data):
                write_event_legacy(event_data)
        else:
            write_event_legacy(event_data)
        if self.DEBUG:
            max_band = max(
                ((k, v) for k, v in bands.items() if k != "total"), key=lambda x: x[1]
            )
            print(
                f"\n[DEBUG] Max band: {max_band[0]} = {max_band[1]:.3f} | Total: {bands.get('total', 0):.3f}"
            )

    def run(self):
        """Main loop - read from pw-record pipe"""
        # Start pw-record as subprocess, pipe stdout to us
        cmd = [
            "pw-record",
            "--target",
            "alsa_input.usb-Razer_Inc_Razer_Seiren_X_UC2029L01304483-00.analog-stereo",
            "--format",
            "s16",  # 16-bit signed PCM
            "--channels",
            "1",  # Mono (simpler)
            "--rate",
            str(self.SAMPLE_RATE),
            "-",  # Output to stdout
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self.CHUNK_SIZE * 2,  # 2 bytes per sample
            )

            print("🎤 Listening to Razer Seiren X!")
            print("Play music, talk, whistle, sing!")
            print("-" * 70)

            bytes_per_sample = 2  # 16-bit = 2 bytes
            bytes_to_read = self.CHUNK_SIZE * bytes_per_sample

            while self.running:
                # Read chunk of audio data
                raw_data = self.process.stdout.read(bytes_to_read)

                if len(raw_data) < bytes_to_read:
                    break  # End of stream

                # Convert bytes to numpy array
                audio_data = np.frombuffer(raw_data, dtype=np.int16)

                # Analyze with multi-band FFT
                bands = self.get_frequency_bands(audio_data)
                total = bands.get("total", 0)

                # ALWAYS print, even below threshold
                if self.DEBUG:
                    print(f"[DEBUG] Total: {total:.3f} | Bands: {bands}")

                # Only process if above threshold
                if total > 0.05:
                    # Visual feedback
                    bar = "█" * int(total * 40)
                    top_bands = sorted(
                        [(k, v) for k, v in bands.items() if k != "total"],
                        key=lambda x: x[1],
                        reverse=True,
                    )[:3]
                    band_str = " ".join(f"{b[0][:3]}:{b[1]:.1f}" for b in top_bands)
                    print(f"[Audio] {bar:40s} | {band_str}", end="\r", flush=True)

                    # Send event (remove threshold check from send_event)
                    self.send_event(bands)

        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback

            traceback.print_exc()
        finally:
            if hasattr(self, "process"):
                self.process.terminate()
                self.process.wait()
            print("\n[Audio Daemon V3] Stopped.")


def main():
    daemon = AetherDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
