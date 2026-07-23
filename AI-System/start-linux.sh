#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "Run ./install-linux.sh first." >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
