#!/bin/sh
# ==============================================================================
# OmniArchiver-F2L Auto-Restart Watchdog
# Automatically checks if python -m bot is running and revives it if stopped.
# Add to crontab:
#   @reboot /bin/sh /usr/home/midnighthawk/OmniArchiver-F2L/scripts/watchdog.sh
#   */5 * * * * /bin/sh /usr/home/midnighthawk/OmniArchiver-F2L/scripts/watchdog.sh
# ==============================================================================

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR" || exit 1

# Check if the bot process is currently active
if ! pgrep -f "python -m bot" > /dev/null 2>&1; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] OmniArchiver bot process not found. Reviving..." >> "$PROJECT_DIR/watchdog.log"

    # Use venv python directly if available, otherwise fallback to system python3
    if [ -x "$PROJECT_DIR/venv/bin/python" ]; then
        PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
    else
        PYTHON_BIN="python3"
    fi

    # Start bot in background with nohup
    nohup "$PYTHON_BIN" -m bot >> "$PROJECT_DIR/bot.log" 2>&1 &
    NEW_PID=$!
    echo "[$TIMESTAMP] OmniArchiver successfully restarted with PID $NEW_PID." >> "$PROJECT_DIR/watchdog.log"
fi
