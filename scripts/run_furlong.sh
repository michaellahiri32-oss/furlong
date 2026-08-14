#!/usr/bin/env bash
# Furlong daily wrapper — used by launchd/cron. Logs to logs/furlong.log.
#   ./scripts/run_furlong.sh            # predict today's card, refresh dashboard
#   ./scripts/run_furlong.sh retrain    # also rebuild data + retrain the models
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
mkdir -p logs
exec >> "logs/furlong.log" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') run ($*) ====="

# activate venv
source .venv/bin/activate

MODE="${1:-daily}"

if [[ "$MODE" == "retrain" ]]; then
  echo "[furlong] refreshing results dataset from rpscrape…"
  python -c "from furlong import ingest; ingest.build_results_dataset()" || \
    echo "[furlong] WARN: results refresh failed (check rpscrape); continuing"
  echo "[furlong] retraining models…"
  python scripts/train.py --no-backtest
fi

echo "[furlong] predicting today's card + publishing app…"
python scripts/run_daily.py --day today --publish || {
  echo "[furlong] ERROR: daily run failed"; exit 1;
}
echo "[furlong] done. app published to GitHub Pages; desktop copy at reports/index.html"
