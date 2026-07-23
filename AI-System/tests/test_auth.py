def test_login_rejects_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "definitely-wrong"},
    )
    assert response.status_code == 401


def test_login_session_and_csrf(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    assert response.cookies.get("localai_session")
    blocked = client.post("/api/conversations", json={"title": "No CSRF"})
    assert blocked.status_code == 403
    allowed = client.post(
        "/api/conversations",
        json={"title": "With CSRF"},
        headers={"X-CSRF-Token": client.cookies.get("localai_csrf")},
    )
    assert allowed.status_code == 200


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
