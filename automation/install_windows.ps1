# Furlong — install the daily + weekly schedule on Windows (Task Scheduler).
# Run this from the project root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File automation\install_windows.ps1
#
# Creates:
#   "Furlong Daily"   - every day 08:00  -> predict today+tomorrow, publish
#   "Furlong Retrain" - Sundays 06:00    -> refresh data from rpscrape + retrain

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..").Path
$bat  = Join-Path $root "scripts\run_furlong.bat"

if (-not (Test-Path $bat)) { throw "run_furlong.bat not found at $bat" }

Write-Host "Project: $root"
Write-Host "Runner : $bat"

# Daily 08:00
$aDaily = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
$tDaily = New-ScheduledTaskTrigger -Daily -At 8:00am
Register-ScheduledTask -TaskName "Furlong Daily" -Action $aDaily -Trigger $tDaily `
  -Description "Furlong: publish today's + tomorrow's racing predictions" -Force | Out-Null
Write-Host "installed: 'Furlong Daily'  (every day 08:00)"

# Weekly retrain Sundays 06:00
$aRe = New-ScheduledTaskAction -Execute $bat -Argument "retrain" -WorkingDirectory $root
$tRe = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 6:00am
Register-ScheduledTask -TaskName "Furlong Retrain" -Action $aRe -Trigger $tRe `
  -Description "Furlong: refresh data from rpscrape and retrain models" -Force | Out-Null
Write-Host "installed: 'Furlong Retrain' (Sundays 06:00)"

Write-Host ""
Write-Host "Done. Test now with:  scripts\run_furlong.bat"
Write-Host "Remove later with:    Unregister-ScheduledTask -TaskName 'Furlong Daily','Furlong Retrain' -Confirm:`$false"
