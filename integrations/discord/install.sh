#!/bin/bash
# Install Aether Discord Rich Presence as user service

set -e

echo "💬 Installing Discord Rich Presence..."

# Check if pypresence is installed
if ! python3 -c "import pypresence" 2>/dev/null; then
    echo "Installing pypresence..."
    pip install --user pypresence
fi

# Install user service
mkdir -p ~/.config/systemd/user
cp aether-discord.service ~/.config/systemd/user/

# Reload user daemon
systemctl --user daemon-reload

# Enable service
systemctl --user enable aether-discord

echo "✓ Discord Rich Presence installed"
echo ""
echo "Commands:"
echo "  systemctl --user start aether-discord    # Start now"
echo "  systemctl --user status aether-discord   # Check status"
echo "  systemctl --user stop aether-discord     # Stop"
echo "  journalctl --user -u aether-discord -f   # View logs"
echo ""
echo "Note: Make sure to set your CLIENT_ID in aether-discord-rpc.py"