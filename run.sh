#!/bin/bash
# Starts Atlas from any folder. Asks for your API key the first time and saves it to .env.
cd "$(dirname "$0")"
source .venv/bin/activate

[ -f .env ] && source .env

if [[ "$ANTHROPIC_API_KEY" != sk-ant-* ]] || [[ "$ANTHROPIC_API_KEY" == "sk-ant-..." ]]; then
  echo "Paste your Anthropic API key (from console.anthropic.com -> API Keys)."
  echo "It won't show on screen while you paste. Press Enter when done."
  read -rs -p "API key: " ANTHROPIC_API_KEY
  echo
  if [[ "$ANTHROPIC_API_KEY" != sk-ant-* ]]; then
    echo "That doesn't look like a key (it should start with sk-ant-). Run this again."
    exit 1
  fi
  umask 077
  echo "export ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'" > .env
  echo "Saved. You won't be asked again."
fi

export ANTHROPIC_API_KEY
python main.py "$@"
