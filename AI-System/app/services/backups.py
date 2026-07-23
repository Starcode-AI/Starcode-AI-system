import base64
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings
from ..db import engine


settings = get_settings()


def database_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise RuntimeError("Built-in backup supports SQLite; use pg_dump for PostgreSQL")
    return Path(settings.database_url[len(prefix) :]).resolve()


def encryption_key() -> bytes:
    digest = hashlib.sha256((settings.secret_key + ":backup:v1").encode()).digest()
    return base64.urlsafe_b64encode(digest)


def create_backup() -> Path:
    source = database_path()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = settings.backup_dir / f"localai-{timestamp}.backup.enc"
    with tempfile.TemporaryDirectory(prefix="localai-backup-") as temp:
        snapshot = Path(temp) / "database.sqlite3"
        with sqlite3.connect(source) as src, sqlite3.connect(snapshot) as dst:
            src.backup(dst)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "database.sqlite3")
            archive.writestr(
                "metadata.json",
                json.dumps({"created_at": datetime.now(UTC).isoformat(), "format": 1}),
            )
        output.write_bytes(Fernet(encryption_key()).encrypt(buffer.getvalue()))
    return output


def restore_backup(encrypted_path: Path) -> None:
    try:
        data = Fernet(encryption_key()).decrypt(encrypted_path.read_bytes())
    except (InvalidToken, OSError) as exc:
        raise ValueError("Backup cannot be decrypted or is damaged") from exc
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        if names != {"database.sqlite3", "metadata.json"}:
            raise ValueError("Backup contains unexpected files")
        database = archive.read("database.sqlite3")
    destination = database_path()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False, suffix=".restore") as handle:
        handle.write(database)
        temporary = Path(handle.name)
    try:
        with sqlite3.connect(temporary) as check:
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"users", "conversations", "messages", "audit_logs"}
        if not required.issubset(tables):
            raise ValueError("Backup database does not have the expected schema")
        engine.dispose()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
