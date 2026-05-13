# Titan BattleBuddy runtime-only launcher
# Starts the BattleBuddy runtime without opening a browser or binding shutdown to UI closure.
# Copyright (c) 2026 Ron Wiley
# All rights reserved.

$repoRoot = $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Set-Location $repoRoot

$wslDistro = "Ubuntu"
$wslWebCommand = "cd /mnt/c/users/mouse/dev/titan-core && source .venv/bin/activate && python -m searx.webapp"

Write-Host "Starting Titan BattleBuddy runtime only..." -ForegroundColor Cyan

$wslProcess = Start-Process powershell -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "wsl -d $wslDistro -- bash -lc `"$wslWebCommand`""
)

Start-Sleep -Seconds 2

$venvPath = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvPath)) {
    Write-Host "BattleBuddy virtual environment not found at: $venvPath" -ForegroundColor Red
    exit 1
}

$backendCommand = @"
Set-Location '$repoRoot'
. '.\.venv\Scripts\Activate.ps1'
python -m uvicorn titan_battlebuddy.main:app --host 127.0.0.1 --port 8001 --reload
"@

Write-Host "Starting Titan BattleBuddy backend..." -ForegroundColor Cyan
$backendProcess = Start-Process powershell -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    $backendCommand
)

Write-Host "Waiting for Titan BattleBuddy backend..." -ForegroundColor Yellow

$online = $false
for ($i = 1; $i -le 20; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/health" -UseBasicParsing -TimeoutSec 1
        if ($response.StatusCode -eq 200) {
            $online = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $online) {
    Write-Host "Titan BattleBuddy backend did not come online. Check the backend PowerShell window." -ForegroundColor Red
    exit 1
}

Write-Host "Titan BattleBuddy runtime is online." -ForegroundColor Green
Write-Host "WSL process PID: $($wslProcess.Id)" -ForegroundColor DarkCyan
Write-Host "Backend process PID: $($backendProcess.Id)" -ForegroundColor DarkCyan
