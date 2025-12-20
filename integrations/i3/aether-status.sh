#!/bin/bash
# i3 status bar audio indicator

if ! command -v aether-query &> /dev/null; then
    echo "🎵--"
    exit 0
fi

BASS=$(aether-query --band bass 2>/dev/null || echo "0")
TOTAL=$(aether-query --band total 2>/dev/null || echo "0")

# Use awk for floating point comparison
if (( $(echo "$BASS > 0.7" | bc -l 2>/dev/null || echo 0) )); then
    printf "🔊%.2f" "$BASS"
elif (( $(echo "$TOTAL > 0.2" | bc -l 2>/dev/null || echo 0) )); then
    printf "🎵%.2f" "$TOTAL"
else
    printf "🎵--"
fi