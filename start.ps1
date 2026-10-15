$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating Python 3.11 virtual environment..."
    py -3.11 -m venv .venv
}

Write-Host "Installing dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Starting mpp5 at http://127.0.0.1:8765"
& ".\.venv\Scripts\python.exe" server.py
