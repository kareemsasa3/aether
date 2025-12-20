#!/bin/bash
# Install Aether OBS auto-ducking as user service

set -e

echo "🎙️  Installing OBS auto-ducking..."

# Check if obs-websocket-py is installed
if ! python3 -c "import obsws_python" 2>/dev/null; then
    echo "Installing obs-websocket-py..."
    pip install --user obs-websocket-py
fi

# Make script executable
chmod +x aether-obs-ducking.py

# Install user service
mkdir -p ~/.config/systemd/user
cp aether-obs.service ~/.config/systemd/user/

# Reload user daemon
systemctl --user daemon-reload

# Enable service
systemctl --user enable aether-obs

echo "✓ OBS auto-ducking installed"
echo ""
echo "Commands:"
echo "  systemctl --user start aether-obs    # Start now"
echo "  systemctl --user status aether-obs   # Check status"
echo "  systemctl --user stop aether-obs     # Stop"
echo "  journalctl --user -u aether-obs -f   # View logs"
echo ""
echo "Note: Configure OBS_PASSWORD in aether-obs-ducking.py"