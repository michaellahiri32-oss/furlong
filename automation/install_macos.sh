#!/usr/bin/env bash
# Install the Furlong daily + weekly schedule on macOS (launchd).
# Run once from the project root:   bash automation/install_macos.sh
set -euo pipefail

FURLONG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$FURLONG_DIR/logs"
chmod +x "$FURLONG_DIR/scripts/run_furlong.sh"

for job in daily retrain; do
  src="$FURLONG_DIR/automation/com.furlong.${job}.plist.template"
  dst="$AGENTS/com.furlong.${job}.plist"
  sed "s#__FURLONG_DIR__#${FURLONG_DIR}#g" "$src" > "$dst"
  # reload if already present
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
  echo "installed + loaded: $dst"
done

echo
echo "Furlong is scheduled:"
echo "  • daily predictions  — every day 08:00"
echo "  • weekly retrain     — Sundays 06:00"
echo "Dashboard will appear at: $FURLONG_DIR/reports/index.html"
echo "Logs: $FURLONG_DIR/logs/furlong.log"
echo
echo "Test it now with:  bash scripts/run_furlong.sh daily"
