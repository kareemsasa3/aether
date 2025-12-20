# 🌊 Aether

> _Real-time audio attention infrastructure for Linux._

Aether is a high-performance audio analysis daemon that publishes live acoustic state to lock-free shared memory. It treats sound not as a stream to be watched, but as a **published contract** that any process can consume.

## 📡 The Core Concept: Numbers as Infrastructure

Aether is built on the philosophy of **ignorance as design**. The daemon captures audio via PipeWire, performs 7-band FFT analysis, and writes the results to a memory-mapped file. It has no knowledge of who is listening, and it never blocks for a consumer. This decoupling is an intentional constraint: any logic beyond audio analysis (triggers, webhooks, or processing) belongs at the edges, not in the core daemon.

The simplest way to interact with Aether isn't a GUI—it's a query:

```bash
$ aether-query --band bass
0.73

$ aether-query --json
{
  "sub_bass": 0.12,
  "bass": 0.73,
  "mid": 0.45,
  ...
  "total": 0.58
}
```

This makes audio state **composable**. Use it for status bars, smart home triggers, or custom visualizations. Note that while the CLI provides JSON for convenience, the true contract is the shared memory layout and its monotonic sequence semantics.

## 🏗️ Architecture: The Broadcast Model

Unlike traditional visualizers where processing and rendering are coupled, Aether separates **analysis** (The Daemon) from **action** (The Consumers).

```
   [ PipeWire ]
        ↓
   [ Aether Daemon ] ──→ [ Shared Memory ] ←── [ YOUR SCRIPT ]
                                ↓
                 ┌──────────────┴──────────────┐
                 ↓                             ↓
        [ Terminal TUI ]              [ OpenRGB Controller ]
        (Reference Viz)               (Physical Light Sync)
```

- **Publisher**: The Daemon writes to `/dev/shm/aether_audio_event` using Optimistic Concurrency Control (OCC).
- **Contract**: A lock-free shared memory region (~20-100μs latency). Consumers detach, lag, or crash without ever affecting the analysis pipeline.
- **Reference Consumers**:
  - **TUI**: A curses-based visualizer with 15+ styles.
  - **RGB**: A physical sync engine for 300+ LEDs via OpenRGB.

## 🚀 Deployment

Aether is designed to run as a **background infrastructure**.

### 1. Install

```bash
git clone https://github.com/kareemsasa3/aether.git
cd aether
./install-aether-client.sh  # Installs the CLI tool and library
```

### 2. Run as Infrastructure (Recommended)

Install the daemon as a long-lived user service:

```bash
cd integrations/systemd
./install.sh
systemctl --user start aether-daemon
```

### 3. Attach Consumers

Now that the audio state is being published, attach any consumer at any time:

```bash
./aether.py              # Launch the terminal visualizer
./aether_rgb.py          # Start the hardware RGB sync
aether-query --monitor   # Watch the raw data stream
```

## ✨ Reference Visualizer Styles

The provided TUI (`aether.py`) includes 15+ "Reference Styles" demonstrating how to transform the shared memory data:

- **Aurora** | **Matrix Rain** | **Cyberpunk** | **Glitch Art** | **Fire** | **Starfield**
- _Toggle with `S` during playback._

## 📊 Performance by Design

- **Latency**: ~92ms end-to-end (Audio capture: 42ms, IPC: 0.05ms, Update: 50ms).
- **Decoupled FPS**: The daemon processes at the audio chunk rate (~23Hz), while the TUI renders at 30 FPS and individual RGB zones update at 20 FPS.
- **Resilience**: If the visualizer lags, the daemon doesn't care. If the daemon crashes, consumers safely read stale data or exit gracefully.

## 🛠️ Integration & Extensions

Because the state is published to shared memory, you can tap into it with zero overhead:

- **Polybar/i3**: Show live bass levels in your status bar.
- **Dunst**: Auto-pause notifications during high-energy music drops.
- **OBS**: Auto-duck microphone volume when music energy peaks.
- **Smart Home**: Sync Philips Hue lights to the "sparkle" band for ambient air.

_See the `integrations/` directory for reference implementations._

## 🧪 Technical Details

### IPC Protocol (OCC)

- **Format**: `[MAGIC:4][VERSION:4][SEQUENCE:8][LENGTH:4][JSON]`
- **Location**: `/dev/shm/aether_audio_event` (RAM-backed tmpfs)
- **Read Logic**: Check sequence number → read data → re-check sequence. If changed, retry (typically < 1% collision rate).

### Analysis Pipeline

- **Sample Rate**: 48 kHz (Mono)
- **Windowing**: Hann window applied per 2048-sample chunk.
- **Spectrum**: 7-band logarithmic mapping (Sub-bass to Sparkle).

## ❌ Non-Goals

Aether intentionally does **not**:
- Manage consumer lifecycle (that's systemd's job)
- Provide beat detection (build it as a consumer)
- Store historical data (it's a real-time state publisher)
- Support multiple audio sources (configure PipeWire instead)

These aren't missing features—they're respected boundaries.

---

**Built with 🎵 for the Linux Desktop by Kareem**
_"In the aether, sound becomes a global variable."_
