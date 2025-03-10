#!/bin/bash
set -e

# Set daemon mode for Docker logs
export DAEMON_MODE=true

# Check if we should run in daemon mode (for automatic updates)
if [ "$1" = "daemon" ]; then
    echo "Starting in daemon mode with configured schedule"
    
    # Run the scheduler which handles all scheduling from config
    echo "Starting scheduler..."
    python /app/scheduler.py
else
    # Run the normal application with any arguments passed
    exec python /app/anime_trakt_manager.py "$@"
fi
