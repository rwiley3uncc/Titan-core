# Titan full launcher
# Starts WSL web server + Titan backend + Edge UI
# Closes Titan services when the Edge window closes

$repoRoot = $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Set-Location $repoRoot

$uiUrl = "http://127.0.0.1:8000/ui/index.html?fresh=30"

# CHANGE THIS if your Ubuntu web server command is different
$wslDistro = "Ubuntu"
$wslWebCommand = "cd ~/Titan-core && python3 web_server.py"

Write-Host "Starting Titan..." -ForegroundColor Cyan

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
    Write-Host "Titan virtual environment not found at: $venvPath" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Start Titan backend in its own tracked PowerShell window
$backendCommand = @"
Set-Location '$repoRoot'
. '.\.venv\Scripts\Activate.ps1'
python -m uvicorn titan_core.main:app --host 127.0.0.1 --port 8000 --reload
"@

Write-Host "Starting Titan backend..." -ForegroundColor Cyan
$backendProcess = Start-Process powershell -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    $backendCommand
)

# Wait for Titan health endpoint
Write-Host "Waiting for Titan backend..." -ForegroundColor Yellow

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
    Write-Host "Titan backend did not come online. Check the backend PowerShell window." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Open Titan UI and wait for that Edge process to close
Write-Host "Titan is online. Opening browser..." -ForegroundColor Green
$browserProcess = Start-Process "msedge.exe" $uiUrl -PassThru

Write-Host "Close the Titan browser window to shut down Titan." -ForegroundColor Yellow

try {
    Wait-Process -Id $browserProcess.Id
} catch {
    Write-Host "Browser process already closed." -ForegroundColor Yellow
}

# Shutdown
Write-Host "Browser closed. Shutting down Titan..." -ForegroundColor Yellow

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

# This shuts down Ubuntu/WSL web server too
try {
    wsl --shutdown
} catch {}

Write-Host "Titan closed." -ForegroundColor Green
Start-Sleep -Seconds 2