#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# start_teams_bot.sh  —  Dev launcher for the Teams Bot bridge service
#
# Usage:
#   ./scripts/start_teams_bot.sh
#
# Prerequisites:
#   - .env file populated (BOT_APP_ID, BOT_APP_PASSWORD, VALIDATOR_API_KEY, …)
#   - FastAPI API already running on port 8000 (scripts/bootstrap.sh)
#   - ngrok (or similar tunnel) exposing this port for Azure Bot Service
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
  source .venv/Scripts/activate
fi

# Load .env variables into the shell environment
if [ -f ".env" ]; then
  set -o allexport
  source .env
  set +o allexport
fi

echo "Starting Teams Bot on ${TEAMS_BOT_HOST:-0.0.0.0}:${TEAMS_BOT_PORT:-3975} ..."
echo "  BOT_APP_ID          = ${BOT_APP_ID}"
echo "  VALIDATOR_API_BASE  = ${VALIDATOR_API_BASE:-http://127.0.0.1:8000}"
echo ""

python -m teams_bot.app
