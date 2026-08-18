from app.models.ingestion_run import STATUS_COMPLETED, STATUS_RUNNING, IngestionRun
from app.services.workspace_settings import get_or_create_workspace_settings

from tests.conftest import auth_headers, signup


# --- Bulk "fetch all my Themen" (POST /theme-watches/run-now) — the Themen page's
# "Alle Themen-Signale abrufen" button. ---


def _enable_google_news(db_session):
    settings = get_or_create_workspace_settings(db_session)
    settings.google_news_rss_enabled = True
    db_session.commit()
    return settings


def _finish_runs(db_session):
    db_session.query(IngestionRun).filter(IngestionRun.status == STATUS_RUNNING).update(
        {"status": STATUS_COMPLETED}
    )
    db_session.commit()


def _create_theme(client, headers, name="Startups DE", **extra):
    resp = client.post(
        "/theme-watches",
        json={"name": name, "query_terms": ["Startup"], **extra},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_bulk_run_now_scopes_to_every_followed_active_theme(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    first = _create_theme(client, headers, name="Startups DE")
    second = _create_theme(client, headers, name="Fintech")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post("/theme-watches/run-now", headers=headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    assert body["theme_watch_id"] is None
    assert sorted(body["theme_watch_ids"]) == sorted([first["id"], second["id"]])
    assert body["companies_total"] == 0
    assert body["themes_total"] == 2


def test_bulk_run_now_excludes_muted_and_unfollowed_themes(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    followed = _create_theme(client, headers, name="Startups DE")
    muted = _create_theme(client, headers, name="Fintech")
    assert client.post(f"/theme-watches/{muted['id']}/mute", headers=headers).status_code == 200
    # A theme this user doesn't follow at all — created by a different user.
    other_headers, _ = signup(client, email="other@proair.com")
    _create_theme(client, other_headers, name="Not mine")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post("/theme-watches/run-now", headers=headers)

    assert resp.status_code == 202
    assert resp.json()["theme_watch_ids"] == [followed["id"]]


def test_bulk_run_now_excludes_paused_themes(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    active = _create_theme(client, headers, name="Startups DE")
    paused = _create_theme(client, headers, name="Fintech")
    client.patch(f"/theme-watches/{paused['id']}", json={"is_active": False}, headers=headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post("/theme-watches/run-now", headers=headers)

    assert resp.status_code == 202
    assert resp.json()["theme_watch_ids"] == [active["id"]]


def test_bulk_run_now_rejects_when_nothing_is_eligible(client, db_session):
    headers = auth_headers(client)
    _enable_google_news(db_session)

    resp = client.post("/theme-watches/run-now", headers=headers)

    assert resp.status_code == 400
    assert "Themen" in resp.json()["detail"]


def test_bulk_run_now_rejects_when_google_news_rss_is_disabled(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _create_theme(client, headers)
    settings = get_or_create_workspace_settings(db_session)
    settings.google_news_rss_enabled = False
    db_session.commit()
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post("/theme-watches/run-now", headers=headers)

    assert resp.status_code == 400
    assert "Google News RSS" in resp.json()["detail"]


def test_bulk_run_now_returns_the_in_flight_run_instead_of_starting_a_second(
    client, db_session, monkeypatch
):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    first = client.post("/theme-watches/run-now", headers=headers)
    second = client.post("/theme-watches/run-now", headers=headers)

    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_bulk_run_now_uses_the_workspace_wide_cooldown(client, db_session, monkeypatch):
    """Unlike the per-theme button, this fetches every one of the caller's themes at
    once, so it's throttled like the other workspace-wide triggers, not per-theme."""
    headers = auth_headers(client)
    _enable_google_news(db_session)
    _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    assert client.post("/theme-watches/run-now", headers=headers).status_code == 202
    _finish_runs(db_session)

    second = client.post("/theme-watches/run-now", headers=headers)
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_bulk_run_now_requires_auth(client):
    resp = client.post("/theme-watches/run-now")
    assert resp.status_code == 401
