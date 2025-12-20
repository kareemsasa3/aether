# Polybar Spectrum Module

## Installation

1. Copy the script:

```bash
   mkdir -p ~/.config/polybar/scripts
   cp aether-spectrum.py ~/.config/polybar/scripts/
   chmod +x ~/.config/polybar/scripts/aether-spectrum.py
```

2. Add to Polybar config (`~/.config/polybar/config.ini`):

```ini
   [module/aether]
   type = custom/script
   exec = ~/.config/polybar/scripts/aether-spectrum.py
   interval = 0.1
   label = 🎵 %output%
   format-foreground = #00FFFF
```

3. Add module to your bar:

```ini
   [bar/mybar]
   modules-right = aether date
```

4. Reload Polybar: `polybar-msg cmd restart`

## Output

Shows live spectrum: `🎵 ▁▄▆█▇▅▂`
