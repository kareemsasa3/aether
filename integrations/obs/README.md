# OBS Studio Integration

Auto-duck microphone when music plays during streaming/recording.

## Setup

1. **Enable OBS WebSocket:**

   - Open OBS Studio
   - Go to: Tools → WebSocket Server Settings
   - Enable "Enable WebSocket server"
   - Set a password
   - Note the port (default: 4455)

2. **Install obs-websocket-py:**

```bash
   pip install obs-websocket-py
```

3. **Configure:**
   Edit `aether-obs-ducking.py`:

   - Set `OBS_PASSWORD`
   - Set `MIC_SOURCE` name (must match OBS exactly)
   - Adjust `MUSIC_THRESHOLD` and ducking levels

4. **Run:**

```bash
   python3 aether-obs-ducking.py
```

## How It Works

- Monitors total audio energy via Aether
- When energy > threshold → reduces mic volume by 12 dB
- When energy drops → restores mic to normal
- Prevents music from overpowering commentary

## Use Cases

- Streaming with background music
- Recording tutorials with demo audio
- Podcasting with intro/outro music
