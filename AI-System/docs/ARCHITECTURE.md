# Architecture

## Components

1. **Browser client** — a dependency-free HTML/CSS/JavaScript interface served by the backend. It stores only theme and language preferences in local storage.
2. **FastAPI service** — owns authentication, authorization, policy enforcement, chat orchestration, file inspection, research, knowledge, feedback, project generation and administration.
3. **Database** — SQLite by default. PostgreSQL can be selected with `DATABASE_URL` for a larger deployment.
4. **Ollama** — local model process. The application uses `/api/tags`, `/api/chat`, `/api/pull` and `/api/delete`.
5. **SearXNG** — local search broker. Search results are not trusted until the application independently validates and downloads their HTTPS URLs.
6. **Caddy** — TLS reverse proxy in Docker mode. Only Caddy is published to the host.
7. **Data roots** — separate upload, project and backup directories. User-supplied files are never placed in the application or system directories.

## Chat flow

1. Authenticate the revocable session and validate the CSRF token.
2. Apply request rate limits.
3. Run the deterministic request policy check.
4. Load a bounded conversation history and matching controlled-knowledge records.
5. If enabled, search through SearXNG, validate every URL, check robots.txt, download with limits and remove injection-like lines.
6. Construct the model request with untrusted data in explicit source boundaries.
7. Generate the complete answer locally through Ollama.
8. Run the response policy check while the answer is still server-side.
9. Store only the approved response or the standard block message.
10. Stream approved text to the browser and attach the exact sources.

## Trust boundaries

| Input | Trust | Treatment |
|---|---|---|
| Application safety policy | Highest | Fixed server code; cannot be replaced by chat text |
| Administrator model profile | High | Appended policy; cannot override base safety rules |
| Authenticated user request | Untrusted | Length, policy and permission checks |
| Knowledge records | Data | Category/confidence metadata; never instruction priority |
| Web and document text | Hostile data | Size/type checks, injection filtering, explicit boundaries |
| Model output | Untrusted | Held and reviewed before release |
| Generated files | Untrusted text artifacts | Safe relative paths, size/count limits, static review, no execution |

## Scaling path

- Move the database to PostgreSQL.
- Replace in-process project jobs with a Redis-backed worker.
- Store large artifacts in a dedicated object store with malware scanning and retention policies.
- Run separate application replicas behind a reverse proxy.
- Keep Ollama/model workers on private GPU hosts with authenticated network policy.

The version 1.0 background task manager is process-local. On restart, interrupted jobs are marked failed rather than silently resumed.
