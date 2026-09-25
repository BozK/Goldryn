#!/usr/bin/env bash
# Build the frontend and serve it from the backend on http://127.0.0.1:8000.
# Run from the repo root (Git Bash on Windows, or any bash on Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")"

if [ -x .venv/Scripts/python ]; then
  PYTHON=.venv/Scripts/python
else
  PYTHON=.venv/bin/python
fi

(cd frontend && npm run build)
exec "$PYTHON" backend/GoldrynBackend.py
