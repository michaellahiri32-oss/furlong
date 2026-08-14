#!/usr/bin/env bash
# Remove the Furlong launchd schedule.
set -euo pipefail
AGENTS="$HOME/Library/LaunchAgents"
for job in daily retrain; do
  dst="$AGENTS/com.furlong.${job}.plist"
  [ -f "$dst" ] && launchctl unload "$dst" 2>/dev/null || true
  rm -f "$dst" && echo "removed $dst" || true
done
echo "Furlong schedule removed."
