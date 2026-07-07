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
    monkeypatch.setattr("app.services.ingestion_runs.run_ingestion", lambda db, progress=None: fake_result)

    resp = client.post("/ingestion/run-now", headers=headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    run_id = body["id"]

    # BackgroundTasks run synchronously within TestClient's request lifecycle, so the
    # pipeline has already finished (the fake, instantly) by the time the POST returns.
    status_resp = client.get("/ingestion/status", headers=headers)
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["id"] == run_id
    assert status_body["status"] == "completed"
    assert status_body["progress_percent"] == 100
    assert status_body["articles_fetched"] == 2
    assert status_body["articles_new"] == 1
    assert status_body["signals_created"] == 1


def test_run_now_returns_existing_run_instead_of_starting_a_duplicate(client, db_session, monkeypatch):
    headers = _auth_headers(client)

    # Patch execute_ingestion_run itself so the row is left "running" (as if the
    # background task were still mid-flight) rather than letting it finalize.
    monkeypatch.setattr("app.api.ingestion.execute_ingestion_run", lambda run_id: None)

    first = client.post("/ingestion/run-now", headers=headers)
    assert first.status_code == 202
    first_id = first.json()["id"]

    # Bypass the cooldown so the second call reaches the "a run is already in flight"
    # check instead of being rejected by the (unrelated) cooldown first.
    from app.models.workspace_settings import WorkspaceSettings

    settings_row = db_session.query(WorkspaceSettings).first()
    settings_row.last_manual_ingestion_at = None
    db_session.commit()

    second = client.post("/ingestion/run-now", headers=headers)
    assert second.status_code == 202
    assert second.json()["id"] == first_id


def test_status_is_null_when_no_run_has_ever_happened(client):
    headers = _auth_headers(client)
    resp = client.get("/ingestion/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


def test_runs_requires_admin(client):
    # The first-ever signup is auto-promoted to admin (see test_admin.py), so a second
    # signup is needed to get a non-admin token here.
    _auth_headers(client)
    resp = client.post(
        "/auth/signup",
        json={"email": "regular@proair.com", "password": "password123", "name": "Regular", "invite_code": "test-invite-code"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    resp = client.get("/ingestion/runs", headers=headers)
    assert resp.status_code == 403
