#!/bin/bash
# Starts SSC from any folder.
# Needs a Claude API key: run ./add_key.sh once to save it.
cd "$(dirname "$0")"
source .venv/bin/activate
[ -f .env ] && source .env

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "No Claude API key saved. Run ./add_key.sh first, then try again."
  exit 1
fi

python main.py "$@"
