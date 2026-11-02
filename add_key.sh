#!/bin/bash
# Optional: save a Claude API key so ./run.sh uses Claude instead of the free local model.
cd "$(dirname "$0")"
echo "Paste your Anthropic API key (from console.anthropic.com -> API Keys)."
echo "It won't show on screen while you paste. Press Enter when done."
read -rs -p "API key: " KEY
echo
if [[ "$KEY" != sk-ant-* ]]; then
  echo "That doesn't look like a key (it should start with sk-ant-). Nothing saved."
  exit 1
fi
umask 077
echo "export ANTHROPIC_API_KEY='$KEY'" > .env
echo "Saved. ./run.sh will now use Claude."
