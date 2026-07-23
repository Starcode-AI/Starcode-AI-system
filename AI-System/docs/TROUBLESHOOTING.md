# Troubleshooting

## “Local model service is not reachable”

- Run `ollama list`.
- Start Ollama and verify `http://127.0.0.1:11434/api/tags` on the same machine.
- In Docker, run `docker compose ps` and `docker compose logs ollama`.
- Confirm `OLLAMA_URL` matches native or container mode.

## Model is installed but not found

The model name and tag must match exactly. Compare the administrator profile with `ollama list`, then activate the correct profile.

## Research says SearXNG is unavailable

Native installation does not install SearXNG automatically. Use the Docker setup or run a private SearXNG instance and set `SEARXNG_URL`. The JSON response format must be enabled.

## Browser rejects the Docker certificate

Copy and trust Caddy's local root certificate as described in the README. Do not disable TLS verification in application code. A public/network deployment should use a real domain and trusted certificate.

## Upload is rejected

Check `MAX_UPLOAD_GB`, reverse-proxy request limits, disk free space and file permissions. Archive-specific failures appear in the analysis result. Executables are quarantined by design.

## Too little RAM or VRAM

Select a smaller or more strongly quantized model, reduce context length and stop other GPU-heavy applications. A longer context can consume much more memory even with the same model.

## Database is locked

SQLite is intended for small installations. Avoid network filesystems, check filesystem permissions and move a busy multi-user deployment to PostgreSQL.

## Restore completed

Restart the application before accepting more requests. Keep the pre-restore backup until the restored system has been verified.
