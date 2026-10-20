#!/usr/bin/env bash
# Build the image (frontend included) and serve it on http://127.0.0.1:8000.
# Run from the repo root (Git Bash on Windows, or any bash on Linux/macOS). Ctrl+C stops it.
set -euo pipefail
cd "$(dirname "$0")"

exec docker compose -f compose.dev.yaml up --build
