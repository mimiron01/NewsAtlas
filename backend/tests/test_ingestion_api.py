from app.schemas.ingestion import IngestionRunResult


def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "rep@proair.com", "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_run_now_requires_auth(client):
    resp = client.post("/ingestion/run-now")
    assert resp.status_code == 401


def test_run_now_invokes_ingestion_pipeline(client, monkeypatch):
    headers = _auth_headers(client)

    fake_result = IngestionRunResult(
        target_companies_processed=1,
        articles_fetched=2,
        articles_new=1,
        signals_created=1,
        errors=[],
    )
    monkeypatch.setattr("app.api.ingestion.run_ingestion", lambda db: fake_result)

    resp = client.post("/ingestion/run-now", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == fake_result.model_dump()
