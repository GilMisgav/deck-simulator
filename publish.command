#!/bin/zsh
# Deck Room — publish the current app + database to the online copy.
# Double-click after any change (deck deletions, new generated decks, UI updates).
# Live at: https://gilmisgav.github.io/deck-room/
cd "$(dirname "$0")"
cp index.html data.js .site/
cd .site
git add -A
if git diff --cached --quiet; then
  echo "Nothing new to publish."
else
  git -c user.name=gmisgav -c user.email=145697630+gmisgav@users.noreply.github.com \
    commit -m "publish $(date '+%Y-%m-%d %H:%M')"
  git push
  echo "Published — live in ~1 minute at https://gilmisgav.github.io/deck-room/"
fi
read -k 1 "?Press any key to close…"
