# Run the backend locally on Windows (PowerShell)
try {
    python --version | Out-Null
} catch {
    Write-Error "Python not found on PATH. Install Python 3.10+ and retry."
    exit 1
}

if (-Not (Test-Path ".venv")) {
    python -m venv .venv
}

Write-Output "Activating virtualenv..."
& .\.venv\Scripts\Activate.ps1

Write-Output "Upgrading pip and installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

if (Test-Path ".env.example" -and -Not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Output "Copied .env.example to .env — edit .env with your secrets before starting."
}

Write-Output "Starting server (uvicorn) on http://localhost:8000"
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
