#!/bin/bash
# Aether Integration Installer
# Handles both system and user services appropriately

set -e

show_menu() {
    clear
    echo ""
    echo "🌊 Aether Integration Installer"
    echo "================================"
    echo ""
    echo "Status:"
    systemctl --user is-active aether-daemon >/dev/null 2>&1 && echo "  ✓ Daemon running (user)" || echo "  ✗ Daemon not running"
    systemctl --user is-active aether-discord >/dev/null 2>&1 && echo "  ✓ Discord RPC (user)" || echo "  - Discord RPC not installed"
    systemctl --user is-active aether-pause >/dev/null 2>&1 && echo "  ✓ Dunst pauser (user)" || echo "  - Dunst pauser not installed"
    systemctl --user is-active aether-obs >/dev/null 2>&1 && echo "  ✓ OBS ducking (user)" || echo "  - OBS ducking not installed"
    systemctl --user is-active aether-hue >/dev/null 2>&1 && echo "  ✓ Hue sync (user)" || echo "  - Hue sync not installed"
    echo ""
    echo "Available integrations:"
    echo "  1) Systemd daemon (user service - required)"
    echo "  2) i3 status bar"
    echo "  3) Polybar spectrum"
    echo "  4) Discord Rich Presence (user service)"
    echo "  5) Dunst notification pauser (user service)"
    echo "  6) OBS auto-ducking (user service)"
    echo "  7) Philips Hue sync (user service)"
    echo "  8) Install ALL"
    echo "  9) Uninstall ALL"
    echo "  0) Exit"
    echo ""
}

install_systemd() {
    echo "📦 Installing systemd daemon (user service)..."
    cd systemd
    chmod +x install.sh
    ./install.sh
    cd ..
    echo ""
    read -p "Press Enter to continue..."
}

install_i3() {
    echo "📊 Installing i3 status bar..."
    mkdir -p ~/.config/i3/scripts
    cp i3/aether-status.sh ~/.config/i3/scripts/
    chmod +x ~/.config/i3/scripts/aether-status.sh
    echo "✓ Script installed to ~/.config/i3/scripts/aether-status.sh"
    echo ""
    echo "Add to ~/.config/i3/config:"
    echo '  bar {'
    echo '      status_command while true; do'
    echo '          echo "$(~/.config/i3/scripts/aether-status.sh) | $(date +"%H:%M")"'
    echo '          sleep 0.1'
    echo '      done'
    echo '  }'
    echo ""
    read -p "Press Enter to continue..."
}

install_polybar() {
    echo "📈 Installing Polybar module..."
    mkdir -p ~/.config/polybar/scripts
    cp polybar/aether-spectrum.py ~/.config/polybar/scripts/
    chmod +x ~/.config/polybar/scripts/aether-spectrum.py
    echo "✓ Script installed to ~/.config/polybar/scripts/aether-spectrum.py"
    echo ""
    echo "Add to ~/.config/polybar/config.ini:"
    echo "  [module/aether]"
    echo "  type = custom/script"
    echo "  exec = ~/.config/polybar/scripts/aether-spectrum.py"
    echo "  interval = 0.1"
    echo "  label = 🎵 %output%"
    echo "  format-foreground = #00FFFF"
    echo ""
    read -p "Press Enter to continue..."
}

install_discord() {
    echo "💬 Installing Discord Rich Presence (user service)..."
    cd discord
    chmod +x install.sh
    ./install.sh
    cd ..
    echo ""
    read -p "Press Enter to continue..."
}

install_dunst() {
    echo "🔕 Installing Dunst notification pauser (user service)..."
    cd dunst
    chmod +x install.sh
    ./install.sh
    cd ..
    echo ""
    read -p "Press Enter to continue..."
}

install_obs() {
    echo "🎙️  Installing OBS auto-ducking (user service)..."
    cd obs
    chmod +x install.sh
    ./install.sh
    cd ..
    echo ""
    read -p "Press Enter to continue..."
}

install_hue() {
    echo "💡 Installing Philips Hue sync (user service)..."
    cd hue
    chmod +x install.sh
    ./install.sh
    cd ..
    echo ""
    read -p "Press Enter to continue..."
}

uninstall_all() {
    echo "🗑️  Uninstalling all integrations..."
    
    # User services
    systemctl --user stop aether-daemon 2>/dev/null || true
    systemctl --user disable aether-daemon 2>/dev/null || true
    systemctl --user stop aether-discord 2>/dev/null || true
    systemctl --user disable aether-discord 2>/dev/null || true
    systemctl --user stop aether-pause 2>/dev/null || true
    systemctl --user disable aether-pause 2>/dev/null || true
    systemctl --user stop aether-obs 2>/dev/null || true
    systemctl --user disable aether-obs 2>/dev/null || true
    systemctl --user stop aether-hue 2>/dev/null || true
    systemctl --user disable aether-hue 2>/dev/null || true
    
    rm -f ~/.config/systemd/user/aether-*.service
    
    systemctl --user daemon-reload
    
    echo "✓ All services uninstalled"
    echo ""
    read -p "Press Enter to continue..."
}

while true; do
    show_menu
    read -p "Select option: " choice
    
    case $choice in
        1) install_systemd ;;
        2) install_i3 ;;
        3) install_polybar ;;
        4) install_discord ;;
        5) install_dunst ;;
        6) install_obs ;;
        7) install_hue ;;
        8)
            install_systemd
            install_i3
            install_polybar
            install_discord
            install_dunst
            install_obs
            install_hue
            echo ""
            echo "✓ All integrations installed!"
            echo ""
            read -p "Press Enter to continue..."
            ;;
        9) uninstall_all ;;
        0) 
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option"
            sleep 1
            ;;
    esac
done