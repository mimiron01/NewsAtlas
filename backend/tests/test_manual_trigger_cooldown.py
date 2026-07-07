from unittest.mock import patch

from app.schemas.digest import DigestRunResult


def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "rep@proair.com",
            "password": "password123",
            "name": "Rep",
            "invite_code": "test-invite-code",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_ingestion_run_now_enforces_cooldown(client, monkeypatch):
    headers = _auth_headers(client)
    # The endpoint itself only needs to get past the cooldown check and hand off to the
    # background task — patch that hand-off so this test doesn't touch the real pipeline.
    monkeypatch.setattr("app.api.ingestion.execute_ingestion_run", lambda run_id: None)

    first = client.post("/ingestion/run-now", headers=headers)
    assert first.status_code == 202

    second = client.post("/ingestion/run-now", headers=headers)
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_digest_send_now_enforces_cooldown(client):
    headers = _auth_headers(client)
    fake_result = DigestRunResult(users_emailed=0, signals_included=0, errors=[])
    with patch("app.api.digest.send_daily_digest", return_value=fake_result):
        first = client.post("/digest/send-now", headers=headers)
        assert first.status_code == 200

        second = client.post("/digest/send-now", headers=headers)
        assert second.status_code == 429


def test_ingestion_and_digest_cooldowns_are_independent(client, monkeypatch):
    headers = _auth_headers(client)
    monkeypatch.setattr("app.api.ingestion.execute_ingestion_run", lambda run_id: None)
    assert client.post("/ingestion/run-now", headers=headers).status_code == 202

    fake_digest = DigestRunResult(users_emailed=0, signals_included=0, errors=[])
    with patch("app.api.digest.send_daily_digest", return_value=fake_digest):
        assert client.post("/digest/send-now", headers=headers).status_code == 200
