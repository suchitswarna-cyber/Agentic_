#!/bin/bash
# Starts SSC from any folder.
# Needs a Google Gemini or Claude API key: run ./add_key.sh once to save it.
cd "$(dirname "$0")"
source .venv/bin/activate
[ -f .env ] && source .env

if [ -z "$GEMINI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "No API key saved. Run ./add_key.sh first, then try again."
  exit 1
fi

python main.py "$@"
