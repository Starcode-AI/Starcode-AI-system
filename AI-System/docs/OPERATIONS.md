# Operations

## Daily checks

- Confirm the application, Ollama and SearXNG health states.
- Review critical/high security events and repeated login failures.
- Check disk use in `data/uploads`, `data/projects`, backups and Ollama model storage.
- Confirm that the active model profile matches available RAM/VRAM.
- Remove old files according to the deployment's retention policy.

## Updates

1. Create and download an encrypted backup.
2. Record the current application, image and model versions.
3. Review dependency and container release notes.
4. Test the update on a copy of the data.
5. Apply the update during maintenance mode.
6. Run tests and verify login, chat, research, uploads and authorization.
7. Disable maintenance mode and monitor logs.

Do not use floating container tags for a high-assurance production deployment. Replace `latest` with digests or tested versions in your own deployment lock file.

## Retention

The application exposes deletion controls but does not silently delete user data by default. Configure an operating-system job or worker policy appropriate for your legal and operational requirements. Never delete the only valid backup.

## PostgreSQL

Set a `postgresql+psycopg://` URL and create a least-privilege database user. Use `pg_dump`/`pg_restore` for production PostgreSQL backup rather than the built-in SQLite backup endpoint.

## Logs

Uvicorn logs go to the process supervisor or container logs. Audit and security events are in the database. Keep application logs free of request bodies unless a reviewed redaction layer is added.
