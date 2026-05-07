# Titan BattleBuddy full launcher
# Starts WSL web server + BattleBuddy backend + Edge UI
# Closes BattleBuddy services when the Edge window closes

$repoRoot = $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Set-Location $repoRoot

$uiUrl = "http://127.0.0.1:8000/ui/index.html"

# CHANGE THIS if your Ubuntu web server command is different
$wslDistro = "Ubuntu"
$wslWebCommand = "cd /mnt/c/users/mouse/dev/titan-core && source .venv/bin/activate && python -m searx.webapp"

Write-Host "Starting Titan BattleBuddy..." -ForegroundColor Cyan

# Start Ubuntu/WSL web server in its own window
Write-Host "Starting Ubuntu web server..." -ForegroundColor Cyan
$wslProcess = Start-Process powershell -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "wsl -d $wslDistro -- bash -lc `"$wslWebCommand`""
)

Start-Sleep -Seconds 2

# Check virtual environment
$venvPath = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvPath)) {
    Write-Host "BattleBuddy virtual environment not found at: $venvPath" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Start BattleBuddy backend in its own tracked PowerShell window
$backendCommand = @"
Set-Location '$repoRoot'
. '.\.venv\Scripts\Activate.ps1'
python -m uvicorn titan_battlebuddy.main:app --host 127.0.0.1 --port 8000 --reload
"@

Write-Host "Starting Titan BattleBuddy backend..." -ForegroundColor Cyan
$backendProcess = Start-Process powershell -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    $backendCommand
)

# Wait for BattleBuddy health endpoint
Write-Host "Waiting for Titan BattleBuddy backend..." -ForegroundColor Yellow

$online = $false
for ($i = 1; $i -le 20; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
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
    Read-Host "Press Enter to close"
    exit 1
}

# Open BattleBuddy UI and wait for that Edge process to close
Write-Host "Titan BattleBuddy is online. Opening browser..." -ForegroundColor Green
$browserProcess = Start-Process "msedge.exe" $uiUrl -PassThru

Write-Host "Close the Titan BattleBuddy browser window to shut down BattleBuddy." -ForegroundColor Yellow

try {
    Wait-Process -Id $browserProcess.Id
} catch {
    Write-Host "Browser process already closed." -ForegroundColor Yellow
}

# Shutdown
Write-Host "Browser closed. Shutting down Titan BattleBuddy..." -ForegroundColor Yellow

try {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force
    }
} catch {}

try {
    if ($wslProcess -and -not $wslProcess.HasExited) {
        Stop-Process -Id $wslProcess.Id -Force
    }
} catch {}

try {
    wsl --shutdown
} catch {}

Write-Host "Titan BattleBuddy closed." -ForegroundColor Green
Start-Sleep -Seconds 2

