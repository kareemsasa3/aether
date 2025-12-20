# Discord Rich Presence Integration

Shows live audio analysis in your Discord status.

## Setup

1. **Create Discord Application:**

   - Go to https://discord.com/developers/applications
   - Click "New Application"
   - Name it "Aether Visualizer"
   - Copy the "Application ID"

2. **Install pypresence:**

```bash
   pip install pypresence
```

3. **Configure:**
   Edit `aether-discord-rpc.py` and set your `CLIENT_ID`

4. **Run:**

```bash
   python3 aether-discord-rpc.py
```

## Discord Status Examples

- `🎧 Bass-Heavy` | Energy: ██████████ 0.85
- `🎸 Guitar-Driven` | Energy: ███████░░░ 0.67
- `🎹 Bright & Crisp` | Energy: █████░░░░░ 0.52

## Run as Service

To auto-start with system:

```bash
sudo cp discord/aether-discord.service /etc/systemd/system/
sudo systemctl enable aether-discord
sudo systemctl start aether-discord
```
