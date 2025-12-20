"""
Aether Configuration

Central configuration for all Aether components.
Edit these values to tune the visualizer to your preferences.
"""

# =============================================================================
# AUDIO DAEMON SETTINGS
# =============================================================================

# FFT/Buffer settings
# Larger = better bass resolution, smaller = faster response
CHUNK_SIZE = 2048
SAMPLE_RATE = 48000  # Hz, matches PipeWire default

# Minimum energy threshold to process audio (reduces noise floor artifacts)
# Range: 0.0 - 1.0, typical: 0.05 - 0.15
AUDIO_THRESHOLD = 0.05

# Logarithmic scaling for FFT energy normalization
# Adjust these if your audio appears too dim or too bright
LOG_ENERGY_MIN_BAND = 5.5   # log10 floor for frequency bands
LOG_ENERGY_RANGE_BAND = 2.0  # log10 range for bands
LOG_ENERGY_MIN_TOTAL = 6.0   # log10 floor for total energy
LOG_ENERGY_RANGE_TOTAL = 2.0  # log10 range for total

# =============================================================================
# RGB CONTROLLER SETTINGS
# =============================================================================

# Update rate (higher = smoother but more CPU)
RGB_FPS = 30

# Decay factor for smooth fade-out (0.0-1.0)
# Higher = slower fade, lower = faster fade
RGB_DECAY_FACTOR = 0.85

# Global brightness multiplier for all LEDs
# Increase if LEDs appear too dim, decrease if too bright
RGB_BRIGHTNESS_BOOST = 2.5

# Silence detection threshold in seconds
# LEDs start fading after this much silence
RGB_SILENCE_THRESHOLD = 0.1

# =============================================================================
# VISUALIZER SETTINGS  
# =============================================================================

# Target frame rate for terminal visualizer
VIZ_FPS = 30

# Waveform decay rate (0.0-1.0)
# Controls how long waveform trails persist
WAVEFORM_DECAY = 0.98

# Spectrum decay rate
SPECTRUM_DECAY = 0.92

# Smoothing factor for amplitude changes (0.0-1.0)
# Lower = more responsive, higher = smoother
SMOOTH_FACTOR = 0.3

# =============================================================================
# SHARED MEMORY IPC SETTINGS
# =============================================================================

# Size of shared memory region in bytes
SHM_SIZE = 4096

# Enable debug logging for IPC
SHM_DEBUG = False

# =============================================================================
# COLOR SCHEMES
# =============================================================================

# RGB colors for each frequency band (R, G, B)
BAND_COLORS = {
    "sub_bass": (75, 0, 130),    # Deep purple (Indigo)
    "bass": (138, 43, 226),      # Blue-violet
    "low_mid": (0, 0, 255),      # Blue
    "mid": (0, 255, 255),        # Cyan
    "high_mid": (0, 255, 0),     # Green
    "treble": (255, 255, 0),     # Yellow
    "sparkle": (255, 140, 0),    # Orange
}

# Frequency ranges for each band (Hz)
FREQUENCY_BANDS = {
    "sub_bass": (20, 60),
    "bass": (60, 250),
    "low_mid": (250, 500),
    "mid": (500, 1000),
    "high_mid": (1000, 2000),
    "treble": (2000, 4000),
    "sparkle": (4000, 8000),
}

