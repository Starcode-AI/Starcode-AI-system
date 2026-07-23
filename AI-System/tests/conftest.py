import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="localai-tests-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{TEST_ROOT / 'test.db'}",
        "SECRET_KEY": "test-only-secret-key-with-more-than-32-characters",
        "UPLOAD_DIR": str(TEST_ROOT / "uploads"),
        "PROJECT_DIR": str(TEST_ROOT / "projects"),
        "BACKUP_DIR": str(TEST_ROOT / "backups"),
        "ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "TRUSTED_ORIGINS": "http://testserver",
    }
)

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        with SessionLocal() as db:
            if not db.get(User, "test-admin"):
                db.add(
                    User(
                        id="test-admin",
                        email="admin@example.com",
                        display_name="Test Admin",
                        password_hash=hash_password("correct-horse-battery-staple"),
                        role=Role.system_administrator,
                    )
                )
                db.commit()
        yield test_client


@pytest.fixture()
def authenticated(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("localai_csrf")

    class AuthClient:
        def __getattr__(self, name):
            return getattr(client, name)

        def request(self, method, url, **kwargs):
            headers = kwargs.pop("headers", {})
            if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                headers["X-CSRF-Token"] = csrf
            return client.request(method, url, headers=headers, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    return AuthClient()
