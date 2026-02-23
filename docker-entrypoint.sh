#!/bin/bash
set -e

export DAEMON_MODE=true

if [ "$1" = "daemon" ]; then
    echo "Starting DAKOSYS in daemon mode..."

    echo "Starting scheduler..."
    python /app/scheduler.py &
    
    echo "Starting web server on port 8000..."
    exec uvicorn web_server:app --host 0.0.0.0 --port 8000

else
    exec python /app/anime_trakt_manager.py "$@"
fi
