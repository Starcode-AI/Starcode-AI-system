# Verification report

Date: 2026-07-23  
Version: 1.0.0

## Automated tests

Command: `python -m pytest -q`

Result: **23 passed**

Covered areas:

- valid/invalid login behavior
- revocable session cookie and CSRF enforcement
- security response headers and CSP
- conversation create/read/update/delete and ownership checks
- prompt-injection detection and untrusted-text filtering
- harmful-request blocking and defensive-context allowance
- filename normalization and archive traversal blocking
- document injection detection and SHA-256 generation
- SSRF rejection for HTTP, loopback, private IPv4/IPv6, credentials and nonstandard ports
- generated-project JSON parsing and path traversal rejection

One non-failing deprecation warning came from the installed FastAPI/Starlette test-client compatibility layer.

## Static validation

- Python compilation: passed
- JavaScript syntax check with Node: passed
- German/English JSON parsing: passed
- Docker Compose YAML parsing: passed
- SearXNG YAML parsing: passed
- forbidden placeholder scan: passed

## Live smoke test

The FastAPI service started successfully on a loopback test port. `/api/health` returned version `1.0.0`, the main HTML application loaded, and the response contained the expected CSP, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY` headers.

Ollama inference and live SearXNG internet results require those local services and a downloaded model; they were not available inside the build environment and are covered by explicit unavailable-service error handling.
