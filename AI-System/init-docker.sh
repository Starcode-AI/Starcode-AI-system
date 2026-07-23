#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
command -v docker >/dev/null 2>&1 || { echo "Docker is required." >&2; exit 1; }

if [[ ! -f .env ]]; then
  cp .env.example .env
  app_secret="$(openssl rand -hex 48)"
  search_secret="$(openssl rand -hex 48)"
  sed -i "s|replace-with-at-least-32-random-characters|$app_secret|" .env
  sed -i "s|replace-with-a-separate-random-secret|$search_secret|" .env
  chmod 600 .env
fi

docker compose up --detach --build
docker compose exec app python -m scripts.create_admin
docker compose exec ollama ollama pull qwen2.5-coder:7b
echo "Ready at https://localhost:8443"
echo "Trust the local Caddy CA certificate as explained in README.md if your browser shows a warning."
