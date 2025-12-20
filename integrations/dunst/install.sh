#!/bin/bash
# Install Aether Dunst notification pauser as user service

set -e

echo "🔕 Installing Dunst notification pauser..."

# Check if dunstctl exists
if ! command -v dunstctl &>/dev/null; then
    echo "Warning: dunstctl not found. Install dunst first:"
    echo "  sudo pacman -S dunst"
    exit 1
fi

# Make script executable
chmod +x aether-pause-daemon.py

# Install user service
mkdir -p ~/.config/systemd/user
cp aether-pause.service ~/.config/systemd/user/

# Reload user daemon
systemctl --user daemon-reload

# Enable service
systemctl --user enable aether-pause

echo "✓ Dunst notification pauser installed"
echo ""
echo "Commands:"
echo "  systemctl --user start aether-pause    # Start now"
echo "  systemctl --user status aether-pause   # Check status"
echo "  systemctl --user stop aether-pause     # Stop"
echo "  journalctl --user -u aether-pause -f   # View logs"