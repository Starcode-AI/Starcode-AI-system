# LocalAI Control

LocalAI Control is a self-hosted text assistant for chat, source-based web research, document inspection, code review, controlled knowledge, and project generation. The language model runs through a local Ollama installation. No OpenAI, Anthropic, Gemini, Mistral Cloud, or other cloud-model API is required.

Version: **1.0.0**  
License: **AGPL-3.0-or-later**

## What is included

- Local model chat through Ollama, with configurable model profiles
- Server-sent response streaming only after the complete answer passed the output review
- German and English interface, dark/light themes, keyboard focus and responsive layouts
- Revocable server-side sessions, Argon2id passwords, CSRF checks, role-based permissions and login lockout
- Self-hosted SearXNG research with HTTPS-only page loading, SSRF protection, bounded redirects/downloads, robots.txt handling, source dates and trust labels
- File inspection for text, source code, PDF, DOCX, XLSX, ZIP, TAR/TAR.GZ and 7Z
- Archive traversal, symlink, file-count, expansion-size and compression-ratio checks
- Executable quarantine and optional ClamAV `INSTREAM` scanning
- Static code checks for syntax and common secret, injection, XSS, weak-hash, unsafe-evaluation and TLS mistakes
- Controlled knowledge records with source, confidence, category, version and administrator approval
- Feedback records that do not automatically modify model weights
- Complete project ZIP generation with path validation, checksums, manifest and security report
- Hardware/model status, audit logs, security events, user/model administration, maintenance mode and encrypted SQLite backups
- Docker Compose, native Windows/Linux scripts and automated tests

## Architecture

```mermaid
flowchart TD
    B[Browser] -->|HTTPS| C[Caddy]
    C --> A[FastAPI application]
    A --> D[(SQLite or PostgreSQL)]
    A --> O[Local Ollama]
    A --> S[Local SearXNG]
    S --> W[Public HTTPS sources]
    A --> F[Isolated data directories]
```

The application, model server and search broker are separate services. Internet text and uploaded documents are untrusted data and never gain instruction priority. Generated content is held on the server until the post-generation safety check finishes.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY.md](docs/SECURITY.md) for the detailed flow and trust boundaries.

## Recommended installation: Docker Compose

Prerequisites:

- Docker Desktop or Docker Engine with Compose
- About 8 GiB free RAM for a small 7B-class quantized model; more memory improves performance and model choice
- Enough storage for container images and model weights

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\init-docker.ps1
```

Linux:

```bash
chmod +x init-docker.sh
./init-docker.sh
```

Open `https://localhost:8443`. Caddy creates a private local certificate authority. If the browser warns, copy its root certificate and trust it for the current user:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./data/caddy-root.crt
```

On Windows, open `data\caddy-root.crt` and import it into the current user's **Trusted Root Certification Authorities** store. On Linux, import it into the browser or operating-system trust store. For a network-accessible installation, use a real domain and publicly trusted certificate instead of the local CA.

The Docker setup exposes only Caddy on `127.0.0.1:8443`; the application, Ollama, and SearXNG remain on the internal Compose network.

Official background material: [Ollama quickstart](https://docs.ollama.com/quickstart), [Ollama Docker](https://docs.ollama.com/docker), [SearXNG container installation](https://docs.searxng.org/admin/installation-docker.html), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).

## Native Windows installation

1. Install Python 3.12+.
2. Install [Ollama for Windows](https://docs.ollama.com/windows).
3. In PowerShell, open this project directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-windows.ps1
.\start-windows.ps1
```

This route binds only to `127.0.0.1:8000`. It is intended for one machine and uses loopback HTTP during development. For the complete HTTPS and web-research setup, use Docker Compose. Research remains unavailable until a local SearXNG instance is running and `SEARXNG_URL` points to it.

## Native Linux installation

Install Python 3.12+, `python3-venv`, OpenSSL and Ollama, then run:

```bash
chmod +x install-linux.sh start-linux.sh
./install-linux.sh
./start-linux.sh
```

Ollama's official Linux instructions are at [docs.ollama.com/linux](https://docs.ollama.com/linux). Native mode is also loopback-only by default. Put Caddy, nginx, or another correctly configured TLS reverse proxy in front before permitting network access.

## First model

The default profile uses `qwen2.5-coder:7b`, which is a practical starting point for text and programming on moderate hardware:

```bash
ollama pull qwen2.5-coder:7b
```

Use the administrator page to create and activate other profiles. A rough starting guide:

| Hardware | Starting class | Notes |
|---|---:|---|
| CPU-only or 8–16 GiB unified/system RAM | 3B–7B quantized | Slower, shorter context |
| 8–12 GiB VRAM, 16–32 GiB RAM | 7B–14B quantized | Good general local setup |
| 24 GiB+ VRAM, 64 GiB+ RAM | 14B–32B quantized | Better quality, higher power/storage use |

Actual memory use depends on quantization, model architecture and context length. Start with an 8k context and increase only after measuring RAM/VRAM.

## Configuration

Copy `.env.example` to `.env`. Never commit `.env`.

Important values:

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Session hashing and backup-key derivation | must be replaced |
| `DATABASE_URL` | SQLite or PostgreSQL connection | `sqlite:///data/localai.db` |
| `OLLAMA_URL` | Local Ollama endpoint | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Initial model profile | `qwen2.5-coder:7b` |
| `SEARXNG_URL` | Self-hosted search service | `http://127.0.0.1:8080` |
| `MAX_UPLOAD_GB` | Maximum single upload | `5` |
| `CLAMAV_HOST` | Optional ClamAV daemon | empty/disabled |
| `FORCE_HTTPS` | Require HTTPS from browser/reverse proxy | `false` in native development |

PostgreSQL is supported through SQLAlchemy. Example:

```dotenv
DATABASE_URL=postgresql+psycopg://localai:strong-password@postgres/localai
```

Apply database migrations in a production customization before changing model definitions. Version 1.0 creates its schema automatically for a fresh installation.

## Commands

```bash
# Create another administrator
python -m scripts.create_admin

# Maintenance mode
python -m scripts.set_maintenance on
python -m scripts.set_maintenance off

# Run tests
python -m pip install -r requirements-dev.txt
pytest -q

# Development server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Project generation and code execution

Generated projects are written as inert text files into a ZIP. They are not executed. This is deliberate: no host-code runner is exposed. If code execution is added later, use a disposable, network-disabled container or microVM with CPU, memory, process, storage and time limits; never call the host shell with model or user text.

## Backups

Administrators can create encrypted SQLite backups through the API. Encryption is derived from `SECRET_KEY`, so the backup cannot be restored if that key is lost. Keep the key and backups in separate protected locations. A restore replaces the database and requires an application restart.

## Important security reality

The system implements layered checks, but no keyword classifier, local model, archive parser, antivirus engine or prompt-injection detector is perfect. Do not expose it directly to the internet without TLS, firewall rules, monitoring, updates and a security review for your environment. Do not give the application access to personal folders, Docker control sockets, SSH keys, cloud credentials or administrator privileges.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security model](docs/SECURITY.md)
- [Operations](docs/OPERATIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Privacy](docs/PRIVACY.md)
- [Terms template](docs/TERMS.md)
- [Changelog](CHANGELOG.md)

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE). Third-party components and local models keep their own licenses; verify a model's license before public or commercial use.
