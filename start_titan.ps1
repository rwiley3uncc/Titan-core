# Titan launcher
# Starts Titan backend in a visible PowerShell process, waits a few seconds,
# then opens the current live UI in Microsoft Edge.

$repoRoot = $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Set-Location $repoRoot

# Activate virtual environment if it exists
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "Titan virtual environment not found at $repoRoot\.venv\Scripts\Activate.ps1" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Start backend in a visible PowerShell window
$backendCommand = "Set-Location '$repoRoot'; . .\.venv\Scripts\Activate.ps1; python -m uvicorn titan_core.main:app --reload"
Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", $backendCommand
)

# Give backend time to start
Start-Sleep -Seconds 3

# Open the live Titan UI in Edge with a fresh cache-busting value
$uiUrl = "http://127.0.0.1:8000/ui/index.html?fresh=10"
Start-Process "msedge.exe" $uiUrl