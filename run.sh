#!/bin/bash
# Starts Atlas from any folder.
# Uses Claude if you've saved an API key (./add_key.sh), otherwise the free local model.
cd "$(dirname "$0")"
source .venv/bin/activate
[ -f .env ] && source .env

if [ -z "$ANTHROPIC_API_KEY" ] && ! curl -s localhost:11434/api/version >/dev/null; then
  echo "Starting Ollama..."
  open -a Ollama
  for _ in $(seq 1 20); do curl -s localhost:11434/api/version >/dev/null && break; sleep 1; done
fi

python main.py "$@"
