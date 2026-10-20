# Build the image (frontend included) and serve it on http://127.0.0.1:8000.
# Run from the repo root (PowerShell on Windows). Ctrl+C stops it.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

docker compose -f compose.dev.yaml up --build
