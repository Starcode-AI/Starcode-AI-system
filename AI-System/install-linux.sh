#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"

python_bin="${PYTHON_BIN:-python3}"
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or newer is required"'

if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --requirement requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  app_secret="$(openssl rand -base64 48 | tr -d '\n')"
  search_secret="$(openssl rand -base64 48 | tr -d '\n')"
  sed -i "s|replace-with-at-least-32-random-characters|$app_secret|" .env
  sed -i "s|replace-with-a-separate-random-secret|$search_secret|" .env
  chmod 600 .env
fi

mkdir -p data/uploads data/projects data/backups
chmod 700 data data/uploads data/projects data/backups

echo "Create the first administrator account."
.venv/bin/python -m scripts.create_admin

if command -v ollama >/dev/null 2>&1; then
  read -r -p "Install qwen2.5-coder:7b now? [Y/n] " answer
  if [[ ! "$answer" =~ ^[Nn] ]]; then ollama pull qwen2.5-coder:7b; fi
else
  echo "Ollama is not installed. See https://docs.ollama.com/linux"
fi

echo "Installation complete. Run ./start-linux.sh"
