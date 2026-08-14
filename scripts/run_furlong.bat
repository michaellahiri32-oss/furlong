@echo off
REM Furlong daily runner for Windows (used by Task Scheduler).
REM   run_furlong.bat           -> predict today+tomorrow, publish to GitHub Pages
REM   run_furlong.bat retrain   -> also refresh data from rpscrape and retrain
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs

call ".venv\Scripts\activate.bat"

echo ===== %DATE% %TIME% run (%1) ===== >> logs\furlong.log

if /I "%1"=="retrain" (
  echo [furlong] refreshing results + retraining... >> logs\furlong.log
  python -c "from furlong import ingest; ingest.build_results_dataset()" >> logs\furlong.log 2>&1
  python scripts\train.py --no-backtest >> logs\furlong.log 2>&1
)

echo [furlong] predicting + publishing... >> logs\furlong.log
python scripts\run_daily.py --publish >> logs\furlong.log 2>&1

echo [furlong] done. >> logs\furlong.log
endlocal
