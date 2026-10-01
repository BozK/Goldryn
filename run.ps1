# Build the frontend and serve it from the backend on http://127.0.0.1:8000.
# Run from the repo root (PowerShell on Windows).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (Test-Path .venv/Scripts/python.exe) {
    $Python = '.venv/Scripts/python.exe'
} else {
    $Python = '.venv/bin/python'
}

Push-Location frontend
try {
    npm install
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

& $Python backend/GoldrynBackend.py
