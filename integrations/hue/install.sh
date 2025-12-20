#!/bin/bash
# Install Aether Hue sync as user service

set -e

echo "💡 Installing Philips Hue sync..."

# Check if phue is installed
if ! python3 -c "import phue" 2>/dev/null; then
    echo "Installing phue..."
    pip install --user phue
fi

# Make script executable
chmod +x aether-hue-sync.py

# Install user service
mkdir -p ~/.config/systemd/user
cp aether-hue.service ~/.config/systemd/user/

# Reload user daemon
systemctl --user daemon-reload

# Enable service
systemctl --user enable aether-hue

echo "✓ Philips Hue sync installed"
echo ""
echo "Commands:"
echo "  systemctl --user start aether-hue    # Start now"
echo "  systemctl --user status aether-hue   # Check status"
echo "  systemctl --user stop aether-hue     # Stop"
echo "  journalctl --user -u aether-hue -f   # View logs"
echo ""
echo "Note: Configure BRIDGE_IP in aether-hue-sync.py"