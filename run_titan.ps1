cd C:\Users\mouse\dev\titancore

.\.venv\Scripts\Activate.ps1

Start-Process powershell -ArgumentList "-NoExit","-Command","cd C:\Users\mouse\dev\titancore; .\.venv\Scripts\Activate.ps1; uvicorn titan_core.main:app --reload"

Start-Sleep -Seconds 3

Start-Process "http://127.0.0.1:8000/ui/index.html?fresh=2"