def test_conversation_lifecycle(authenticated):
    created = authenticated.post("/api/conversations", json={"title": "Security review"})
    assert created.status_code == 200
    item = created.json()
    fetched = authenticated.get(f"/api/conversations/{item['id']}")
    assert fetched.status_code == 200
    changed = authenticated.patch(
        f"/api/conversations/{item['id']}", json={"title": "Renamed", "archived": True}
    )
    assert changed.json()["title"] == "Renamed"
    removed = authenticated.delete(f"/api/conversations/{item['id']}")
    assert removed.status_code == 200


def test_access_control_hides_unknown_conversation(authenticated):
    assert authenticated.get("/api/conversations/not-a-real-id").status_code == 404
