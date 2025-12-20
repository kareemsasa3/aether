# i3 Status Bar Integration

## Installation

1. Copy the script:

```bash
   mkdir -p ~/.config/i3/scripts
   cp aether-status.sh ~/.config/i3/scripts/
   chmod +x ~/.config/i3/scripts/aether-status.sh
```

2. Add to i3 config (`~/.config/i3/config`):

```bash
   bar {
       status_command while true; do
           echo "$(~/.config/i3/scripts/aether-status.sh) | $(date +'%Y-%m-%d %H:%M')"
           sleep 0.1
       done
   }
```

3. Reload i3: `$mod+Shift+r`

## Output

Status bar will show:

- `🔊0.73` - Heavy bass detected
- `🎵0.45` - Normal audio activity
- `🎵--` - Quiet/no audio
