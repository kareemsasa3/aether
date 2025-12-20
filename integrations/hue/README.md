# Philips Hue Integration

Sync your smart lights to system audio in real-time.

## Setup

1. **Find your Hue Bridge IP:**

   - Open Philips Hue app
   - Settings → Hue Bridges → i button
   - Note the IP address

2. **Install phue:**

```bash
   pip install phue
```

3. **First-time setup:**

```bash
   python3 aether-hue-sync.py
```

- When prompted, press the button on your Hue Bridge
- Script will save credentials

4. **Configure lights:**
   Edit `aether-hue-sync.py` → `LIGHT_MAP`:

```python
   LIGHT_MAP = {
       'Living Room': 'bass',    # Your light name → frequency band
       'Bedroom': 'total',
   }
```

## Color Mapping

- **Red** → Bass frequencies (kick drums, bass guitar)
- **Green** → Mid frequencies (vocals, guitars)
- **Blue** → Treble frequencies (cymbals, hi-hats)
- **Cyan** → Balanced spectrum

## Performance

- Runs at 20 FPS (50ms updates)
- Smooth transitions
- Minimum brightness prevents total darkness

## Example Setups

**Gaming Setup:**

```python
LIGHT_MAP = {
    'Monitor Backlight': 'total',  # React to all audio
    'Ceiling Strip': 'bass',       # Pulse with action
}
```

**Music Listening:**

```python
LIGHT_MAP = {
    'Left Speaker': 'bass',
    'Right Speaker': 'treble',
    'Center': 'mid',
}
```
