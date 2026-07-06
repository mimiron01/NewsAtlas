from app.services.workspace_settings import get_or_create_workspace_settings


def _admin_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "admin@proair.com", "password": "password123", "name": "Admin", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_headers(client):
    client.post(
        "/auth/signup",
        json={"email": "admin@proair.com", "password": "password123", "name": "Admin", "invite_code": "test-invite-code"},
    )
    resp = client.post(
        "/auth/signup",
        json={"email": "user@proair.com", "password": "password123", "name": "User", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _enable_backfill(db_session, **overrides):
    settings = get_or_create_workspace_settings(db_session)
    settings.newsdata_enabled = True
    settings.newsdata_backfill_days = 30
    for key, value in overrides.items():
        setattr(settings, key, value)
    db_session.commit()


def test_create_company_triggers_backfill_when_configured(client, db_session, monkeypatch):
    headers = _admin_headers(client)
    _enable_backfill(db_session)

    calls = []
    monkeypatch.setattr(
        "app.api.target_companies.run_backfill_for_company",
        lambda db, target_company_id, **kwargs: calls.append(target_company_id) or True,
    )

    resp = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    assert resp.status_code == 201
    assert len(calls) == 1


def test_create_company_does_not_trigger_backfill_when_disabled(client, db_session, monkeypatch):
    headers = _admin_headers(client)
    # newsdata_enabled defaults to False — no explicit setup needed.

    calls = []
    monkeypatch.setattr(
        "app.api.target_companies.run_backfill_for_company",
        lambda db, target_company_id, **kwargs: calls.append(target_company_id) or True,
    )

    resp = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    assert resp.status_code == 201
    assert calls == []


def test_manual_backfill_requires_admin(client, db_session):
    headers = _user_headers(client)
    create = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    company_id = create.json()["id"]

    resp = client.post(f"/target-companies/{company_id}/backfill", headers=headers)
    assert resp.status_code == 403


def test_manual_backfill_rejected_when_newsdata_disabled(client, db_session):
    headers = _admin_headers(client)
    create = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    company_id = create.json()["id"]

    resp = client.post(f"/target-companies/{company_id}/backfill", headers=headers)
    assert resp.status_code == 400
    assert "NewsData.io is not enabled" in resp.json()["detail"]


def test_manual_backfill_rejected_when_backfill_days_zero(client, db_session):
    headers = _admin_headers(client)
    settings = get_or_create_workspace_settings(db_session)
    settings.newsdata_enabled = True
    settings.newsdata_backfill_days = 0
    db_session.commit()

    create = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    company_id = create.json()["id"]

    resp = client.post(f"/target-companies/{company_id}/backfill", headers=headers)
    assert resp.status_code == 400
    assert "backfill window" in resp.json()["detail"]


def test_manual_backfill_schedules_when_eligible(client, db_session, monkeypatch):
    headers = _admin_headers(client)
    create = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    company_id = create.json()["id"]
    _enable_backfill(db_session)

    calls = []
    monkeypatch.setattr(
        "app.api.target_companies.run_backfill_for_company",
        lambda db, target_company_id, **kwargs: calls.append(target_company_id) or True,
    )

    resp = client.post(f"/target-companies/{company_id}/backfill", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheduled"] is True
    assert len(calls) == 1


def test_manual_backfill_rejected_when_already_backfilled(client, db_session, monkeypatch):
    headers = _admin_headers(client)
    create = client.post("/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers)
    company_id = create.json()["id"]
    _enable_backfill(db_session)

    from datetime import datetime, timezone

    from app.models.target_company import TargetCompany

    company = db_session.get(TargetCompany, company_id)
    company.backfilled_at = datetime.now(timezone.utc)
    db_session.commit()

    resp = client.post(f"/target-companies/{company_id}/backfill", headers=headers)
    assert resp.status_code == 400
    assert "already been backfilled" in resp.json()["detail"]
