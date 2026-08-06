#!/bin/zsh
# Deck Room — start the local server and open the app.
# Double-click this file in Finder (or run ./start.command) any time.
cd "$(dirname "$0")"
if ! lsof -nP -iTCP:8642 -sTCP:LISTEN >/dev/null 2>&1; then
  if command -v node >/dev/null 2>&1; then
    nohup node server.js >/dev/null 2>&1 &      # full app + save-to-database API
  else
    nohup python3 -m http.server 8642 >/dev/null 2>&1 &   # view-only fallback
  fi
  sleep 1
fi
open "http://localhost:8642/"
