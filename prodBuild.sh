#!/usr/bin/env bash
# Run on the server after a `git pull`: rebuild frontend/dist and sync the venv
# with requirements.txt. Restart the service afterwards to pick up the changes.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/pip ]; then
  echo "No .venv with pip found. Create it first (see DEPLOY_NOTES.md; uv venvs need --seed)." >&2
  exit 1
fi

# npm ci installs exactly what package-lock.json says and never rewrites it,
# so the next pull won't trip over a modified lockfile.
(cd frontend && npm ci && npm run build)
.venv/bin/pip install -r requirements.txt

echo
echo "Build done. Restart to load it: sudo systemctl restart goldryn"
