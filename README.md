# 🌊 Aether

> _Where sound becomes light_

A terminal-based audio visualizer with real-time frequency analysis and RGB LED synchronization. Watch your music ripple across your screen and illuminate your hardware.

![Aether Demo](demo.gif)

## ✨ Features

- **🎵 Real-time audio analysis** - 7-band FFT processing via PipeWire
- **🌊 Center-radiation waveforms** - Unique visual effect that radiates from the center
- **💡 Hardware RGB sync** - Synchronize 300+ LEDs with your music via OpenRGB
- **🎨 15+ visualization styles** - Hot-swappable styles with unique aesthetics
- **⚡ Low latency** - Lock-free shared memory IPC (~20-100μs)
- **🖥️ Terminal-native** - Works over SSH, no GUI required
- **🎚️ Dual modes** - Oscilloscope and full-spectrum analyzer views

## 🚀 Quick Start

### Prerequisites

```bash
# Arch Linux
sudo pacman -S python pipewire openrgb

# Ubuntu/Debian
sudo apt install python3 pipewire openrgb
```

### Installation

```bash
git clone https://github.com/kareemsasa3/aether.git
cd aether
python -m venv venv
source venv/bin/activate  # or `venv/bin/activate` on Windows
pip install -r requirements.txt  # if you create one
```

### Usage

**1. Start the audio daemon:**

```bash
./aether_daemon.py
```

**2. Launch the visualizer:**

```bash
./aether.py
```

**3. (Optional) Start RGB sync:**

```bash
./aether_rgb.py
```

## ⌨️ Controls

| Key   | Action                                       |
| ----- | -------------------------------------------- |
| `S`   | Switch visualization style                   |
| `D`   | Toggle design mode (oscilloscope ↔ spectrum) |
| `Q`   | Quit                                         |
| `↑/↓` | Navigate style menu                          |

## 🎨 Visualization Styles

Aether includes 15 unique visualization styles:

- **Aurora** - Northern lights effect with color waves
- **Classic Wave** - Clean oscilloscope aesthetic
- **Cyberpunk** - Neon-soaked future vibes
- **Data Stream** - Matrix-inspired data flow
- **Dense Fade** - Layered transparency effects
- **Fire** - Flame-like energy visualization
- **Geometric** - Sharp angles and patterns
- **Glitch Art** - Digital corruption aesthetic
- **Heartbeat** - Pulsing organic rhythm
- **Matrix Rain** - Falling code columns
- **Minimalist** - Clean and simple
- **Neon Pulse** - Electric glow effects
- **Pixel Art** - Retro 8-bit style
- **Rain Drops** - Liquid motion trails
- **Starfield** - Space-themed particles

Press `S` during playback to switch styles instantly!

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│  PipeWire Audio Capture                     │
├─────────────────────────────────────────────┤
│  FFT Analysis (7 frequency bands)           │
│  • Sub-bass  (20-60 Hz)                     │
│  • Bass      (60-250 Hz)                    │
│  • Low-mid   (250-500 Hz)                   │
│  • Mid       (500-1000 Hz)                  │
│  • High-mid  (1000-2000 Hz)                 │
│  • Treble    (2000-4000 Hz)                 │
│  • Sparkle   (4000-8000 Hz)                 │
├─────────────────────────────────────────────┤
│  Shared Memory IPC (lock-free)              │
│  ~20-100μs latency                          │
├─────────────────────────────────────────────┤
│  Curses TUI Visualizer (30 FPS)             │
│  Center-radiating waveform display          │
├─────────────────────────────────────────────┤
│  OpenRGB LED Controller (20 FPS)            │
│  Traveling wave effect across 311 LEDs      │
└─────────────────────────────────────────────┘
```

### Components

- **`aether_daemon.py`** - Audio capture and FFT analysis
- **`aether.py`** - Terminal visualizer with curses
- **`aether_rgb.py`** - RGB LED synchronization via OpenRGB
- **`aether_shm.py`** - Lock-free shared memory IPC
- **`styles/`** - Pluggable visualization style modules

## ⚙️ Configuration

### Audio Input

By default, Aether captures from the Razer Seiren X microphone. To change the audio source, edit `aether_daemon.py`:

```python
# Line ~XX
"--target", "YOUR_AUDIO_DEVICE_NAME_HERE",
```

Find your device name:

```bash
pactl list sources | grep -E "Name:|Description:"
```

### RGB LED Mapping

RGB sync assumes the following OpenRGB device layout:

- Device 0: Motherboard (300 LEDs)
- Device 1-2: RAM sticks (5 LEDs each)
- Device 3: Mouse logo (1 LED)

Edit `aether_rgb.py` to match your hardware configuration.

## 🎯 Performance

- **Latency**: ~92ms end-to-end (imperceptible)
  - Audio capture: ~42ms
  - Shared memory: ~0.05ms
  - RGB update: ~50ms
- **Frame rates**:
  - Visualizer: 30 FPS (stable)
  - RGB controller: 20 FPS
- **CPU usage**: ~5-10% on modern systems
- **Memory**: ~50MB total

## 🐛 Troubleshooting

### No audio visualization

1. Check that PipeWire is running:

   ```bash
   systemctl --user status pipewire
   ```

2. Verify audio device name in `aether_daemon.py`

3. Test audio capture manually:
   ```bash
   pw-record --target YOUR_DEVICE test.wav
   ```

### RGB LEDs not syncing

1. Ensure OpenRGB server is running:

   ```bash
   openrgb --server
   ```

2. Check device indices match your hardware:
   ```bash
   openrgb --list-devices
   ```

### Terminal rendering issues

- Use a modern terminal (Kitty, Alacritty, iTerm2)
- Ensure terminal supports 256 colors
- Increase terminal font size if characters overlap

## 🧪 Technical Details

### FFT Analysis

- **Sample rate**: 48 kHz
- **Chunk size**: 2048 samples (~42.7ms latency)
- **Windowing**: Hann window for spectral leakage reduction
- **Scaling**: Logarithmic energy mapping (0.0-1.0 normalized)

### Shared Memory IPC

- **Protocol**: Optimistic Concurrency Control (OCC)
- **Format**: `[MAGIC:4][VERSION:4][SEQUENCE:8][LENGTH:4][JSON]`
- **Location**: `/dev/shm/aether_audio_event` (tmpfs, RAM-backed)
- **Fallback**: Legacy file-based IPC at `/tmp/aether_last_event.json`

### Waveform Rendering

- **Style**: Center-radiation (dual deque system)
- **Decay rate**: 0.98 (trails persist ~1.6s)
- **Smoothing**: Exponential interpolation (factor: 0.3)
- **Visual frequencies**: 2-20 Hz (mapped from audio bands)

## 🤝 Contributing

Contributions welcome! To add a new visualization style:

1. Create `styles/your_style.py`
2. Implement the `render_waveform()` function:

   ```python
   STYLE_NAME = "Your Style"
   STYLE_DESCRIPTION = "Brief description"

   def render_waveform(i, amp, age, max_width, colors):
       """
       Args:
           i: Distance from center (0 = center)
           amp: Amplitude (-1.0 to 1.0)
           age: Age in frames (0 = newest)
           max_width: Half-width available
           colors: Dict of curses color pairs

       Returns:
           (char, color) tuple or None
       """
       # Your rendering logic here
       return char, color
   ```

3. Test with `./aether.py --style=your_style`
4. Submit a pull request!

## 📜 License

MIT License - see [LICENSE](LICENSE) for details

## 🙏 Acknowledgments

- Inspired by classic oscilloscopes and Milkdrop visualizations
- Built with [PipeWire](https://pipewire.org/) for audio capture
- RGB sync powered by [OpenRGB](https://openrgb.org/)
- FFT analysis via NumPy/SciPy

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=kareemsasa3/aether&type=Date)](https://star-history.com/#kareemsasa3/aether&Date)

---

**Built with 🎵 by Kareem (https://github.com/kareemsasa3)**

_"In the aether, sound and light become one."_
