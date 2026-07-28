from app.schemas.digest import DigestRunResult

from tests.conftest import auth_headers


def test_send_now_requires_auth(client):
    resp = client.post("/digest/send-now")
    assert resp.status_code == 401


def test_send_now_invokes_digest_pipeline(client, monkeypatch):
    headers = auth_headers(client)

    fake_result = DigestRunResult(users_emailed=2, signals_included=3, errors=[])
    monkeypatch.setattr("app.api.digest.send_daily_digest", lambda db: fake_result)

    resp = client.post("/digest/send-now", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == fake_result.model_dump()
