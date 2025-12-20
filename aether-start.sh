#!/bin/bash
# aether-start.sh - Unified launcher for Aether audio visualizer
#
# Usage:
#   ./aether-start.sh           # Interactive mode
#   ./aether-start.sh all       # Start daemon + RGB (background), then visualizer
#   ./aether-start.sh daemon    # Start audio daemon (foreground with logs)
#   ./aether-start.sh viz       # Start visualizer (daemon must be running)
#   ./aether-start.sh rgb       # Start RGB controller (foreground with logs)
#   ./aether-start.sh stop      # Stop all Aether processes
#   ./aether-start.sh status    # Show running processes
#   ./aether-start.sh logs      # Tail background process logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Log directory
LOG_DIR="$SCRIPT_DIR/.aether_logs"
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "   ░▒▓ A E T H E R ▓▒░"
    echo -e "${NC}${CYAN}   Where sound becomes light${NC}"
    echo ""
}

check_deps() {
    local missing=()
    
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi
    
    if ! command -v pw-record &> /dev/null; then
        missing+=("pipewire (pw-record)")
    fi
    
    if [ "$1" = "rgb" ] || [ "$1" = "all" ]; then
        if ! pgrep -x "openrgb" > /dev/null; then
            echo -e "${YELLOW}⚠ OpenRGB server not running. Start it with: openrgb --server${NC}"
        fi
    fi
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}Missing dependencies: ${missing[*]}${NC}"
        exit 1
    fi
}

start_daemon_bg() {
    if pgrep -f "aether_daemon.py" > /dev/null; then
        echo -e "${YELLOW}⚠ Daemon already running${NC}"
        return
    fi
    echo -e "${GREEN}▶ Starting audio daemon (background)...${NC}"
    nohup python3 aether_daemon.py > "$LOG_DIR/daemon.log" 2>&1 &
    echo $! > "$LOG_DIR/daemon.pid"
    sleep 0.3
    if pgrep -f "aether_daemon.py" > /dev/null; then
        echo -e "  ${GREEN}✓${NC} PID: $(cat "$LOG_DIR/daemon.pid") → Logs: $LOG_DIR/daemon.log"
    else
        echo -e "  ${RED}✗ Failed to start. Check $LOG_DIR/daemon.log${NC}"
    fi
}

start_daemon_fg() {
    echo -e "${GREEN}▶ Starting audio daemon (foreground)...${NC}"
    echo -e "${YELLOW}  Press Ctrl+C to stop${NC}"
    echo ""
    python3 aether_daemon.py
}

start_visualizer() {
    # Check daemon is running
    if ! pgrep -f "aether_daemon.py" > /dev/null; then
        echo -e "${YELLOW}⚠ Audio daemon not running. Starting it first...${NC}"
        start_daemon_bg
        sleep 0.5
    fi
    python3 aether.py "$@"
}

start_rgb_bg() {
    if pgrep -f "aether_rgb.py" > /dev/null; then
        echo -e "${YELLOW}⚠ RGB controller already running${NC}"
        return
    fi
    echo -e "${GREEN}▶ Starting RGB controller (background)...${NC}"
    nohup python3 aether_rgb.py > "$LOG_DIR/rgb.log" 2>&1 &
    echo $! > "$LOG_DIR/rgb.pid"
    sleep 0.3
    if pgrep -f "aether_rgb.py" > /dev/null; then
        echo -e "  ${GREEN}✓${NC} PID: $(cat "$LOG_DIR/rgb.pid") → Logs: $LOG_DIR/rgb.log"
    else
        echo -e "  ${RED}✗ Failed to start. Check $LOG_DIR/rgb.log${NC}"
    fi
}

start_rgb_fg() {
    echo -e "${GREEN}▶ Starting RGB controller (foreground)...${NC}"
    echo -e "${YELLOW}  Press Ctrl+C to stop${NC}"
    echo ""
    python3 aether_rgb.py
}

stop_all() {
    echo -e "${YELLOW}Stopping all Aether processes...${NC}"
    pkill -f "aether_daemon.py" 2>/dev/null && echo -e "  ${GREEN}✓${NC} Daemon stopped" || echo -e "  ${CYAN}○${NC} Daemon wasn't running"
    pkill -f "aether_rgb.py" 2>/dev/null && echo -e "  ${GREEN}✓${NC} RGB stopped" || echo -e "  ${CYAN}○${NC} RGB wasn't running"
    pkill -f "python3.*aether.py" 2>/dev/null && echo -e "  ${GREEN}✓${NC} Visualizer stopped" || echo -e "  ${CYAN}○${NC} Visualizer wasn't running"
    rm -f "$LOG_DIR"/*.pid 2>/dev/null
    echo -e "${GREEN}Done${NC}"
}

show_status() {
    echo -e "${CYAN}${BOLD}Aether Process Status:${NC}"
    echo ""
    
    if pgrep -f "aether_daemon.py" > /dev/null; then
        local pid=$(pgrep -f "aether_daemon.py" | head -1)
        echo -e "  ${GREEN}●${NC} Audio Daemon    ${CYAN}PID $pid${NC}"
    else
        echo -e "  ${RED}○${NC} Audio Daemon    (stopped)"
    fi
    
    if pgrep -f "python3.*aether.py" > /dev/null; then
        local pid=$(pgrep -f "python3.*aether.py" | head -1)
        echo -e "  ${GREEN}●${NC} Visualizer      ${CYAN}PID $pid${NC}"
    else
        echo -e "  ${RED}○${NC} Visualizer      (stopped)"
    fi
    
    if pgrep -f "aether_rgb.py" > /dev/null; then
        local pid=$(pgrep -f "aether_rgb.py" | head -1)
        echo -e "  ${GREEN}●${NC} RGB Controller  ${CYAN}PID $pid${NC}"
    else
        echo -e "  ${RED}○${NC} RGB Controller  (stopped)"
    fi
    
    echo ""
    if pgrep -x "openrgb" > /dev/null; then
        echo -e "  ${GREEN}●${NC} OpenRGB Server  (external)"
    else
        echo -e "  ${YELLOW}○${NC} OpenRGB Server  (not running)"
    fi
}

show_logs() {
    echo -e "${CYAN}${BOLD}Recent Logs:${NC}"
    echo ""
    if [ -f "$LOG_DIR/daemon.log" ]; then
        echo -e "${YELLOW}── Daemon ──${NC}"
        tail -5 "$LOG_DIR/daemon.log" 2>/dev/null || echo "(empty)"
        echo ""
    fi
    if [ -f "$LOG_DIR/rgb.log" ]; then
        echo -e "${YELLOW}── RGB ──${NC}"
        tail -5 "$LOG_DIR/rgb.log" 2>/dev/null || echo "(empty)"
    fi
    echo ""
    echo -e "${CYAN}Full logs: $LOG_DIR/${NC}"
}

interactive_menu() {
    print_banner
    show_status
    echo ""
    echo -e "${BOLD}What would you like to do?${NC}"
    echo ""
    echo "  1) Start everything (recommended)"
    echo "  2) Start visualizer only"
    echo "  3) Start daemon only (foreground)"
    echo "  4) Start RGB only (foreground)"
    echo "  5) Stop all"
    echo "  6) View logs"
    echo "  7) Exit"
    echo ""
    read -p "Choice [1-7]: " choice
    
    case $choice in
        1) MODE="all" ;;
        2) MODE="viz" ;;
        3) MODE="daemon" ;;
        4) MODE="rgb" ;;
        5) MODE="stop" ;;
        6) MODE="logs" ;;
        7) exit 0 ;;
        *) echo "Invalid choice"; exit 1 ;;
    esac
}

# Parse arguments
MODE="${1:-}"
shift 2>/dev/null || true

if [ -z "$MODE" ]; then
    interactive_menu
fi

case "$MODE" in
    all)
        print_banner
        check_deps "$MODE"
        start_daemon_bg
        start_rgb_bg
        echo ""
        echo -e "${CYAN}Launching visualizer...${NC}"
        echo -e "${YELLOW}Press Q to quit (daemon & RGB continue in background)${NC}"
        sleep 1
        start_visualizer "$@"
        ;;
    daemon)
        print_banner
        check_deps "$MODE"
        start_daemon_fg
        ;;
    viz)
        print_banner
        check_deps "$MODE"
        start_visualizer "$@"
        ;;
    rgb)
        print_banner
        check_deps "$MODE"
        start_rgb_fg
        ;;
    stop)
        print_banner
        stop_all
        ;;
    status)
        print_banner
        show_status
        ;;
    logs)
        print_banner
        show_logs
        ;;
    *)
        echo "Usage: $0 [all|daemon|viz|rgb|stop|status|logs]"
        exit 1
        ;;
esac

