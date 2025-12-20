#!/bin/bash
# Install Aether client library and CLI tool
# Automatically detects Python version and site-packages

set -e

echo "🌊 Installing Aether Client Library..."

# Detect Python version dynamically
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Detected Python $PYTHON_VERSION"

# Get site-packages path
SITE_PACKAGES=$(python3 -c 'import site; print(site.getsitepackages()[0])')
echo "Installing to: $SITE_PACKAGES"

# Install both required files (client needs SHM implementation)
echo "Copying aether_shm.py..."
sudo cp aether_shm.py "$SITE_PACKAGES/"

echo "Copying aether_client.py..."
sudo cp aether_client.py "$SITE_PACKAGES/"

# Create CLI executable
echo "Creating /usr/local/bin/aether-query..."
sudo tee /usr/local/bin/aether-query > /dev/null << 'EOF'
#!/usr/bin/env python3
import sys
from aether_client import main

if __name__ == '__main__':
    main()
EOF

sudo chmod +x /usr/local/bin/aether-query

echo ""
echo "✓ Installed aether_shm.py to $SITE_PACKAGES"
echo "✓ Installed aether_client.py to $SITE_PACKAGES"
echo "✓ Created /usr/local/bin/aether-query"
echo ""
echo "Test it:"
echo "  aether-query --monitor    # Live display"
echo "  aether-query --band bass  # Get bass value"
echo "  aether-query --json       # JSON output"
echo ""
echo "If Aether daemon isn't running, start it with:"
echo "  ./aether-start.sh daemon"