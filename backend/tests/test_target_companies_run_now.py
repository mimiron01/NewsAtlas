import uuid

from app.models.ingestion_run import STATUS_COMPLETED, STATUS_RUNNING, IngestionRun

from tests.conftest import auth_headers, signup


# --- Per-company / multi-select manual fetch (POST /target-companies/{id}/run-now and
# POST /target-companies/run-now) ----------------------------------------------------


def _finish_runs(db_session):
    """Settles every in-flight run. The endpoint hands back an already-running run instead
    of starting a second one, so tests that are actually about the cooldown have to clear
    that earlier check out of the way first."""
    db_session.query(IngestionRun).filter(IngestionRun.status == STATUS_RUNNING).update(
        {"status": STATUS_COMPLETED}
    )
    db_session.commit()


def _create_company(client, headers, name="Acme Corp", **extra):
    resp = client.post("/target-companies", json={"name": name, **extra}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


def test_run_now_starts_a_run_scoped_to_this_company(client, monkeypatch):
    headers = auth_headers(client)
    company = _create_company(client, headers)
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/target-companies/{company['id']}/run-now", headers=headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    # Scoped to this company: no themes in the run's work, exactly one company.
    assert body["target_company_ids"] == [company["id"]]
    assert body["companies_total"] == 1
    assert body["themes_total"] == 0


def test_run_now_returns_the_in_flight_run_instead_of_starting_a_second(client, monkeypatch):
    headers = auth_headers(client)
    company = _create_company(client, headers)
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    first = client.post(f"/target-companies/{company['id']}/run-now", headers=headers)
    second = client.post(f"/target-companies/{company['id']}/run-now", headers=headers)

    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_run_now_shares_the_workspace_wide_cooldown_with_the_full_run(client, db_session, monkeypatch):
    """Unlike a theme's per-topic cooldown, a company-scoped run hits the same news
    providers a full run does, so it shares the full run's cooldown clock rather than
    getting its own — triggering one blocks the other for the cooldown window."""
    headers = auth_headers(client)
    company = _create_company(client, headers)
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)
    monkeypatch.setattr("app.api.ingestion.execute_ingestion_run", lambda run_id: None)

    assert client.post(f"/target-companies/{company['id']}/run-now", headers=headers).status_code == 202
    _finish_runs(db_session)

    second = client.post("/ingestion/run-now", headers=headers)
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_run_now_rejects_a_paused_company(client, monkeypatch):
    headers = auth_headers(client)
    company = _create_company(client, headers)
    client.patch(f"/target-companies/{company['id']}", json={"is_active": False}, headers=headers)
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/target-companies/{company['id']}/run-now", headers=headers)

    assert resp.status_code == 400
    assert "paused" in resp.json()["detail"].lower()


def test_run_now_requires_following_the_company(client, monkeypatch):
    owner_headers = auth_headers(client)
    company = _create_company(client, owner_headers)
    other_headers, _ = signup(client, email="other@proair.com")
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/target-companies/{company['id']}/run-now", headers=other_headers)

    assert resp.status_code == 403


def test_run_now_requires_auth(client):
    resp = client.post(f"/target-companies/{uuid.uuid4()}/run-now")
    assert resp.status_code == 401


def test_run_now_404s_for_unknown_company(client):
    headers = auth_headers(client)
    resp = client.post(f"/target-companies/{uuid.uuid4()}/run-now", headers=headers)
    assert resp.status_code == 404


# --- Bulk / multi-select variant -----------------------------------------------------


def test_bulk_run_now_starts_a_run_scoped_to_the_selected_companies(client, monkeypatch):
    headers = auth_headers(client)
    first = _create_company(client, headers, name="Acme Corp")
    second = _create_company(client, headers, name="Widgets Inc")
    _create_company(client, headers, name="Not Selected")
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    resp = client.post(
        "/target-companies/run-now",
        json={"target_company_ids": [first["id"], second["id"]]},
        headers=headers,
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["companies_total"] == 2
    assert body["themes_total"] == 0
    assert sorted(body["target_company_ids"]) == sorted([first["id"], second["id"]])


def test_bulk_run_now_silently_drops_ineligible_ids(client, monkeypatch):
    """A paused or not-found id in the selection doesn't fail the whole request — the
    frontend's selection is built from a list the caller already has open, and a stale row
    shouldn't block the rest of it (same tolerant style as POST /bulk-delete)."""
    headers = auth_headers(client)
    eligible = _create_company(client, headers, name="Acme Corp")
    paused = _create_company(client, headers, name="Paused Co")
    client.patch(f"/target-companies/{paused['id']}", json={"is_active": False}, headers=headers)
    monkeypatch.setattr("app.api.target_companies.execute_ingestion_run", lambda run_id: None)

    resp = client.post(
        "/target-companies/run-now",
        json={"target_company_ids": [eligible["id"], paused["id"], str(uuid.uuid4())]},
        headers=headers,
    )

    assert resp.status_code == 202
    assert resp.json()["target_company_ids"] == [eligible["id"]]


def test_bulk_run_now_rejects_when_nothing_is_eligible(client):
    headers = auth_headers(client)
    resp = client.post(
        "/target-companies/run-now",
        json={"target_company_ids": [str(uuid.uuid4())]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_bulk_run_now_requires_auth(client):
    resp = client.post("/target-companies/run-now", json={"target_company_ids": [str(uuid.uuid4())]})
    assert resp.status_code == 401


def test_bulk_run_now_rejects_empty_list(client):
    headers = auth_headers(client)
    resp = client.post("/target-companies/run-now", json={"target_company_ids": []}, headers=headers)
    assert resp.status_code == 422
