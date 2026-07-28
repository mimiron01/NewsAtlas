import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.ingestion_run import STATUS_COMPLETED, STATUS_RUNNING, IngestionRun
from app.services.workspace_settings import get_or_create_workspace_settings

from tests.conftest import auth_headers, signup


# --- Per-theme manual fetch (POST /theme-watches/{id}/run-now) ---------------------


def _enable_google_news(db_session):
    settings = get_or_create_workspace_settings(db_session)
    settings.google_news_rss_enabled = True
    db_session.commit()
    return settings


def _finish_runs(db_session):
    """Settles every in-flight run. The endpoint hands back an already-running run instead
    of starting a second one, so tests that are actually about the cooldown have to clear
    that earlier check out of the way first."""
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


def test_run_now_starts_a_run_scoped_to_this_theme(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    # Scoped to this theme: no companies in the run's work, exactly one theme.
    assert body["theme_watch_id"] == theme["id"]
    assert body["companies_total"] == 0
    assert body["themes_total"] == 1


def test_run_now_enforces_a_per_theme_cooldown(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    assert client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers).status_code == 202
    # The first run is still marked running, so a second click returns that run rather
    # than 429 — finish it so the cooldown is what's actually under test.
    _finish_runs(db_session)

    second = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)
    assert second.status_code == 429
    # Rendered verbatim as a countdown in the UI, so it must be present and positive.
    assert int(second.headers["Retry-After"]) > 0


def test_each_theme_has_its_own_cooldown_clock(client, db_session, monkeypatch):
    """One theme's fetch must not lock out another's — the whole point of not sharing the
    workspace-wide manual-trigger cooldown."""
    headers = auth_headers(client)
    _enable_google_news(db_session)
    first = _create_theme(client, headers, name="Startups DE")
    second = _create_theme(client, headers, name="Fintech")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    assert client.post(f"/theme-watches/{first['id']}/run-now", headers=headers).status_code == 202
    _finish_runs(db_session)

    assert client.post(f"/theme-watches/{second['id']}/run-now", headers=headers).status_code == 202


def test_theme_run_does_not_consume_the_workspace_wide_cooldown(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)
    monkeypatch.setattr("app.api.ingestion.execute_ingestion_run", lambda run_id: None)

    assert client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers).status_code == 202
    _finish_runs(db_session)

    # The full-run button still works right afterwards.
    assert client.post("/ingestion/run-now", headers=headers).status_code == 202


def test_run_now_returns_the_in_flight_run_instead_of_starting_a_second(
    client, db_session, monkeypatch
):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    first = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)
    second = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_run_now_rejects_when_google_news_rss_is_disabled(client, monkeypatch):
    headers = auth_headers(client)
    theme = _create_theme(client, headers)  # google_news_rss_enabled defaults to False
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert resp.status_code == 400
    assert "Google News RSS" in resp.json()["detail"]


def test_run_now_rejects_a_paused_theme(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    client.patch(f"/theme-watches/{theme['id']}", json={"is_active": False}, headers=headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert resp.status_code == 400
    assert "paused" in resp.json()["detail"].lower()


def test_run_now_requires_following_the_theme(client, db_session, monkeypatch):
    owner_headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, owner_headers)
    other_headers, _ = signup(client, email="other@proair.com")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=other_headers)

    assert resp.status_code == 403


def test_run_now_requires_auth(client):
    resp = client.post(f"/theme-watches/{uuid.uuid4()}/run-now")
    assert resp.status_code == 401


def test_run_now_404s_for_unknown_theme(client, db_session):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    resp = client.post(f"/theme-watches/{uuid.uuid4()}/run-now", headers=headers)
    assert resp.status_code == 404


# --- Per-theme Google News edition -------------------------------------------------


def test_theme_locale_override_is_normalized(client):
    headers = auth_headers(client)
    theme = _create_theme(
        client, headers, google_news_country="de", google_news_language="DE"
    )
    assert theme["google_news_country"] == "DE"
    assert theme["google_news_language"] == "de"


def test_theme_locale_defaults_to_inheriting_the_workspace_edition(client):
    headers = auth_headers(client)
    theme = _create_theme(client, headers)
    assert theme["google_news_country"] is None
    assert theme["google_news_language"] is None


def test_blank_theme_locale_is_stored_as_inherit(client):
    """The frontend's "workspace default" option submits an empty string; it must land as
    NULL so it can't drift from a never-set value."""
    headers = auth_headers(client)
    theme = _create_theme(client, headers, google_news_country="", google_news_language="")
    assert theme["google_news_country"] is None
    assert theme["google_news_language"] is None


def test_theme_locale_rejects_nonsense_values(client):
    headers = auth_headers(client)
    resp = client.post(
        "/theme-watches",
        json={"name": "Bad", "query_terms": ["x"], "google_news_country": "D3!"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_theme_locale_can_be_updated_and_cleared(client):
    headers = auth_headers(client)
    theme = _create_theme(client, headers, google_news_country="DE", google_news_language="de")

    cleared = client.patch(
        f"/theme-watches/{theme['id']}",
        json={"google_news_country": "", "google_news_language": ""},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["google_news_country"] is None


def test_run_now_end_to_end_produces_matches_for_the_theme(client, db_session, monkeypatch):
    """Exercises the real wiring the other tests stub out: endpoint -> background task ->
    execute_ingestion_run -> run_ingestion -> ThemeMatch rows. Only the two external
    services (Google News' feed and Mistral) are faked."""
    from tests.test_theme_ingestion import FakeThemeAIClient

    headers = auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers, google_news_country="DE", google_news_language="de")

    requested_urls: list[str] = []

    def fake_parse(url):
        requested_urls.append(url)
        return SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "link": "https://example.com/de-startup-series-b",
                    "title": "Berliner Startup sammelt 20 Mio. ein - Handelsblatt",
                    "summary": "Ein Berliner Startup hat eine Series B abgeschlossen.",
                    "published_parsed": datetime.now(timezone.utc).timetuple(),
                }
            ],
        )

    monkeypatch.setattr("app.services.google_news_rss_client.feedparser.parse", fake_parse)
    monkeypatch.setattr("app.services.ingestion.AIClient", lambda **kwargs: FakeThemeAIClient())
    # execute_ingestion_run opens its own session; point it at the test session so the
    # rows it writes are visible here.
    monkeypatch.setattr("app.services.ingestion_runs.SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)
    assert resp.status_code == 202

    # TestClient runs BackgroundTasks synchronously once the response is sent, so the run
    # has already completed by here.
    run = db_session.get(IngestionRun, uuid.UUID(resp.json()["id"]))
    db_session.refresh(run)
    assert run.status == STATUS_COMPLETED, run.fatal_error or run.errors
    assert run.theme_matches_created == 1
    assert run.themes_processed == 1

    matches = client.get("/theme-matches", headers=headers).json()
    assert len(matches) == 1
    assert matches[0]["theme_watch_name"] == "Startups DE"
    # The per-theme edition actually reached the request, not the workspace US/en default.
    assert "gl=DE" in requested_urls[0]
    assert "hl=de" in requested_urls[0]
