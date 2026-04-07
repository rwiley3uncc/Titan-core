# Titan launcher
# Starts Titan backend, waits a few seconds, then opens the live UI

Set-Location "C:\Users\mouse\dev\titancore"

# Activate virtual environment if it exists
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "Titan virtual environment not found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit
}

# Start backend in a new PowerShell window
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location 'C:\Users\mouse\dev\titancore'; .\.venv\Scripts\Activate.ps1; python -m uvicorn titan_core.main:app --reload"
)

# Give backend time to start
Start-Sleep -Seconds 3

# Open the live Titan UI
Start-Process "http://127.0.0.1:8000/ui/index.html?fresh=2"