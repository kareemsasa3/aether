#!/usr/bin/env python3
# aether_daemon.py - Direct PipeWire pipeline
import subprocess
import numpy as np
import sys
import signal
import time
import math
from aether_shm import AetherSharedMemory, write_event_legacy
import aether_config as config


class AetherDaemon:
    DEBUG = False
    # ==========================================================================
    # AUDIO PROCESSING CONSTANTS
    # ==========================================================================

    # FFT/Buffer settings (tunable in aether_config.py).
    # 2048 samples @ 48kHz = ~42.7ms latency, good balance of frequency resolution
    # vs responsiveness. Larger = better bass resolution, smaller = faster response.
    CHUNK_SIZE = config.CHUNK_SIZE
    SAMPLE_RATE = config.SAMPLE_RATE  # Hz, matches PipeWire default

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
    LOG_ENERGY_MIN_BAND = config.LOG_ENERGY_MIN_BAND  # log10 floor for bands
    LOG_ENERGY_RANGE_BAND = config.LOG_ENERGY_RANGE_BAND  # log10 range

    # For total energy (sum of all bands):
    #   - Higher baseline because summing 7 bands yields higher total
    #   - log10(1M) = 6.0 floor, log10(100M) = 8.0 ceiling
    LOG_ENERGY_MIN_TOTAL = config.LOG_ENERGY_MIN_TOTAL  # log10 floor for total
    LOG_ENERGY_RANGE_TOTAL = config.LOG_ENERGY_RANGE_TOTAL  # log10 range

    # --------------------------------------------------------------------------
    # Frequency Band Definitions (Hz) — defined in aether_config.py
    # --------------------------------------------------------------------------
    # Based on standard audio engineering frequency ranges.
    # Each band captures distinct musical/voice characteristics.
    FREQUENCY_BANDS = config.FREQUENCY_BANDS

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
        print("[Audio Daemon V3] Using system default microphone")
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
        # Apply Hann window to reduce spectral leakage
        # This prevents energy from bleeding between frequency bins
        window = np.hanning(len(audio_data))
        windowed_data = audio_data * window
        
        # Apply FFT to windowed data
        fft = np.fft.rfft(windowed_data)
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
            "timestamp": time.time(),
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
        # No --target flag = uses system default microphone
        cmd = [
            "pw-record",
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
                stderr=subprocess.PIPE,
                bufsize=self.CHUNK_SIZE * 2,  # 2 bytes per sample
            )

            # Give pw-record a moment to fail if no source is available
            time.sleep(0.3)
            if self.process.poll() is not None:
                stderr_out = self.process.stderr.read().decode(errors="replace").strip()
                if "no target node available" in stderr_out:
                    print("[Audio Daemon V3] ERROR: No PipeWire input source available.")
                    print("[Audio Daemon V3] Plug in or select a microphone, then retry.")
                else:
                    print(f"[Audio Daemon V3] ERROR: pw-record exited (code {self.process.returncode})")
                    if stderr_out:
                        for line in stderr_out.splitlines()[:5]:
                            print(f"  {line}")
                return 1

            print("🎤 Listening to default microphone!")
            print("Play music, talk, whistle, sing!")
            print("-" * 70)

            bytes_per_sample = 2  # 16-bit = 2 bytes
            bytes_to_read = self.CHUNK_SIZE * bytes_per_sample

            while self.running:
                # Read chunk of audio data
                raw_data = self.process.stdout.read(bytes_to_read)

                if len(raw_data) < bytes_to_read:
                    # Stream ended — check if pw-record failed
                    rc = self.process.wait()
                    if rc != 0:
                        stderr_out = self.process.stderr.read().decode(errors="replace").strip()
                        if stderr_out:
                            print(f"\n[Audio Daemon V3] pw-record error: {stderr_out}")
                    break

                # Convert bytes to numpy array
                audio_data = np.frombuffer(raw_data, dtype=np.int16)

                # Analyze with multi-band FFT
                bands = self.get_frequency_bands(audio_data)
                total = bands.get("total", 0)

                # ALWAYS print, even below threshold
                if self.DEBUG:
                    print(f"[DEBUG] Total: {total:.3f} | Bands: {bands}")

                # Only process if above threshold (configurable)
                if total > config.AUDIO_THRESHOLD:
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
            return 1
        finally:
            if hasattr(self, "process"):
                if self.process.poll() is None:
                    self.process.terminate()
                self.process.wait()
            print("\n[Audio Daemon V3] Stopped.")
        return 0


def main():
    daemon = AetherDaemon()
    sys.exit(daemon.run())


if __name__ == "__main__":
    main()
