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

- **Publisher**: The Daemon writes to `/dev/shm/aether_audio_event` using a **seqlock** (a sequence-versioned, lock-free protocol).
- **Contract**: A lock-free shared memory region (~20-100μs latency). Consumers detach, lag, or crash without ever affecting the analysis pipeline.
- **Reference Consumers**:
  - **TUI**: A curses-based visualizer with 17 styles.
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

The provided TUI (`aether.py`) includes 17 "Reference Styles" demonstrating how to transform the shared memory data. Styles come in two tiers:

- **Frame styles** own the whole waveform region every frame (`render_frame(ctx, canvas)`) and compose full scenes — persistent motion, beat pulses, layered backgrounds, and ambient "resting" visuals during silence:
  - **Neon Wave** (★ default/showcase) — mirrored gradient wave, beat flashes, falling peak trails
  - **Spectra** — full-width mirrored spectrum bars with falling peak caps
  - **Matrix Rain** — cascading digital rain; energy spawns drops, bass speeds them
  - **Aurora** — full-height light curtains with drifting colors
  - **Starfield** — parallax stars that jump to warp speed on the bass
  - **Rain Drops** — rainfall onto a rippling water surface with splashes
  - **Cyberpunk** — neon signal over a city skyline with glitch scanlines
  - **Classic Wave** — CRT oscilloscope with a continuous trace and phosphor decay
  - **Minimalist** — a single high-resolution braille curve
- **Cell styles** (Fire, Glitch Art, Heartbeat, Neon Pulse, Pixel Art, Geometric, Data Stream, Dense Fade) plot one glyph per waveform sample via `render_waveform(...)`.
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

### IPC Protocol (Seqlock)

- **Format**: `[MAGIC:4][VERSION:4][SEQUENCE:8][LENGTH:4][JSON]`
- **Location**: `/dev/shm/aether_audio_event` (RAM-backed tmpfs)
- **Write Logic**: Bump sequence to odd (write-in-progress) → write payload + length → bump to even (commit). Committed sequences are even; an odd value marks an in-flight write.
- **Read Logic**: Read sequence (`seq1`) → read data → re-read sequence (`seq2`). The frame is consistent only if `seq1 == seq2` and `seq1` is even; otherwise skip and catch the next frame (typically < 1% collision rate).
- **Atomicity**: The sequence field is 8-byte aligned, so the commit lands as a single aligned 64-bit store — atomic on x86-64. Correctness does **not** rest on that alone: the reader's seqlock retry (the `seq1 == seq2` check plus the odd-sequence skip) detects and rejects torn reads regardless of platform store semantics, so the guarantee does not depend on any cross-platform atomicity promise from Python's `mmap.write()`.

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
