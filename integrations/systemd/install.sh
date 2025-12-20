#!/bin/bash
# Install Aether daemon as systemd USER service
set -e

echo "📦 Installing Aether daemon USER service..."

# Create user systemd directory if it doesn't exist
mkdir -p ~/.config/systemd/user/

# Copy service file
cp aether-daemon.service ~/.config/systemd/user/

# Reload systemd user instance
systemctl --user daemon-reload

# Enable on boot (user session boot)
systemctl --user enable aether-daemon

echo "✓ User service installed and enabled"
echo ""
echo "Commands:"
echo "  systemctl --user start aether-daemon    # Start now"
echo "  systemctl --user status aether-daemon   # Check status"
echo "  systemctl --user stop aether-daemon     # Stop"
echo "  journalctl --user -u aether-daemon -f   # View logs"