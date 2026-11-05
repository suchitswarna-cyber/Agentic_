#!/bin/bash
# Save an API key in .env so ./run.sh and ./run_web.sh can use it.
# Google Gemini keys (free tier) start with AIza or AQ.; Claude keys start with sk-ant-.
cd "$(dirname "$0")"
echo "Paste your API key:"
echo "  - Google Gemini (free): aistudio.google.com -> Get API key"
echo "  - Claude (paid):        console.anthropic.com -> API Keys"
echo "It won't show on screen while you paste. Press Enter when done."
read -rs -p "API key: " KEY
echo
case "$KEY" in
  AIza*|AQ.*) VAR=GEMINI_API_KEY;  NAME="Google Gemini" ;;
  sk-ant-*) VAR=ANTHROPIC_API_KEY; NAME="Claude" ;;
  *) echo "That doesn't look like a Google key (AIza... or AQ....) or a Claude key (sk-ant-...). Nothing saved."
     exit 1 ;;
esac
umask 077
touch .env
grep -v "^export $VAR=" .env > .env.tmp; mv .env.tmp .env
echo "export $VAR='$KEY'" >> .env
echo "Saved your $NAME key."
