from app.schemas.digest import DigestRunResult


def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "rep@proair.com", "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_send_now_requires_auth(client):
    resp = client.post("/digest/send-now")
    assert resp.status_code == 401


def test_send_now_invokes_digest_pipeline(client, monkeypatch):
    headers = _auth_headers(client)

    fake_result = DigestRunResult(users_emailed=2, signals_included=3, errors=[])
    monkeypatch.setattr("app.api.digest.send_daily_digest", lambda db: fake_result)

    resp = client.post("/digest/send-now", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == fake_result.model_dump()
