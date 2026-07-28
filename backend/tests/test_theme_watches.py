import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.ingestion_run import STATUS_COMPLETED, STATUS_RUNNING, IngestionRun
from app.models.theme_watch import ThemeWatch
from app.services.workspace_settings import get_or_create_workspace_settings


def _signup(client, email="rep@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    return headers, uuid.UUID(user_id)


def _auth_headers(client):
    headers, _user_id = _signup(client)
    return headers


def test_create_list_update_delete_theme_watch(client):
    headers = _auth_headers(client)

    create_resp = client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV battery", "Series B"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    theme = create_resp.json()
    assert theme["name"] == "Automotive"
    assert theme["is_active"] is True
    assert theme["is_muted"] is False
    assert theme["follower_count"] == 1

    list_resp = client.get("/theme-watches", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"is_active": False}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    delete_resp = client.delete(f"/theme-watches/{theme['id']}", headers=headers)
    assert delete_resp.status_code == 204
    assert client.get("/theme-watches", headers=headers).json() == []


def test_theme_watch_requires_at_least_one_query_term(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": []}, headers=headers
    )
    assert resp.status_code == 422


def test_theme_watch_dedupes_by_name_case_insensitive(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")

    resp_a = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    )
    resp_b = client.post(
        "/theme-watches", json={"name": "automotive", "query_terms": ["EV"]}, headers=headers_b
    )
    assert resp_a.json()["id"] == resp_b.json()["id"]
    assert resp_b.json()["follower_count"] == 2


def test_non_creator_follower_cannot_edit_shared_theme(client):
    creator_headers, _ = _signup(client, email="creator@proair.com")
    other_headers, _ = _signup(client, email="other@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=creator_headers
    ).json()
    client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=other_headers
    )

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"name": "Renamed"}, headers=other_headers
    )
    assert patch_resp.status_code == 403

    mute_resp = client.post(f"/theme-watches/{theme['id']}/mute", headers=other_headers)
    assert mute_resp.status_code == 200


def test_admin_can_edit_theme_they_do_not_follow(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=user_headers
    ).json()

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"name": "Renamed"}, headers=admin_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed"


def test_theme_watches_require_auth(client):
    resp = client.get("/theme-watches")
    assert resp.status_code == 401


def test_patch_and_delete_require_following(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    ).json()

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"is_active": False}, headers=headers_b
    )
    assert patch_resp.status_code == 403

    delete_resp = client.delete(f"/theme-watches/{theme['id']}", headers=headers_b)
    assert delete_resp.status_code == 403


def test_mute_requires_following(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    ).json()

    resp = client.post(f"/theme-watches/{theme['id']}/mute", headers=headers_b)
    assert resp.status_code == 404


def test_admin_scope_all_lists_full_catalog(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
    client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=user_headers
    )

    resp = client.get("/theme-watches?scope=all", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["is_muted"] is None


def test_scope_all_is_admin_only(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")

    resp = client.get("/theme-watches?scope=all", headers=user_headers)
    assert resp.status_code == 403


def test_followers_endpoint_is_admin_only(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=user_headers
    ).json()

    forbidden = client.get(f"/theme-watches/{theme['id']}/followers", headers=user_headers)
    assert forbidden.status_code == 403

    ok = client.get(f"/theme-watches/{theme['id']}/followers", headers=admin_headers)
    assert ok.status_code == 200
    assert len(ok.json()) == 1
    assert ok.json()[0]["email"] == "rep@proair.com"


def test_create_theme_watch_rejects_when_active_ceiling_reached(client, db_session):
    headers = _auth_headers(client)
    workspace_settings = get_or_create_workspace_settings(db_session)
    workspace_settings.max_active_theme_watches = 1
    db_session.commit()

    first = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    )
    assert first.status_code == 201

    second = client.post(
        "/theme-watches", json={"name": "Fintech", "query_terms": ["Series B"]}, headers=headers
    )
    assert second.status_code == 400


def test_reactivating_a_paused_theme_respects_ceiling(client, db_session):
    headers = _auth_headers(client)
    workspace_settings = get_or_create_workspace_settings(db_session)
    workspace_settings.max_active_theme_watches = 1
    db_session.commit()

    first = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    ).json()
    client.patch(f"/theme-watches/{first['id']}", json={"is_active": False}, headers=headers)
    client.post(
        "/theme-watches", json={"name": "Fintech", "query_terms": ["Series B"]}, headers=headers
    )

    resp = client.patch(f"/theme-watches/{first['id']}", json={"is_active": True}, headers=headers)
    assert resp.status_code == 400


def test_google_news_source_allowlist_rejects_non_hostname(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/theme-watches",
        json={
            "name": "Automotive",
            "query_terms": ["EV"],
            "google_news_source_allowlist": ["https://reuters.com"],
        },
        headers=headers,
    )
    assert resp.status_code == 422


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
    headers = _auth_headers(client)
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
    headers = _auth_headers(client)
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
    headers = _auth_headers(client)
    _enable_google_news(db_session)
    first = _create_theme(client, headers, name="Startups DE")
    second = _create_theme(client, headers, name="Fintech")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    assert client.post(f"/theme-watches/{first['id']}/run-now", headers=headers).status_code == 202
    _finish_runs(db_session)

    assert client.post(f"/theme-watches/{second['id']}/run-now", headers=headers).status_code == 202


def test_theme_run_does_not_consume_the_workspace_wide_cooldown(client, db_session, monkeypatch):
    headers = _auth_headers(client)
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
    headers = _auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    first = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)
    second = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_run_now_rejects_when_google_news_rss_is_disabled(client, monkeypatch):
    headers = _auth_headers(client)
    theme = _create_theme(client, headers)  # google_news_rss_enabled defaults to False
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert resp.status_code == 400
    assert "Google News RSS" in resp.json()["detail"]


def test_run_now_rejects_a_paused_theme(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, headers)
    client.patch(f"/theme-watches/{theme['id']}", json={"is_active": False}, headers=headers)
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=headers)

    assert resp.status_code == 400
    assert "paused" in resp.json()["detail"].lower()


def test_run_now_requires_following_the_theme(client, db_session, monkeypatch):
    owner_headers = _auth_headers(client)
    _enable_google_news(db_session)
    theme = _create_theme(client, owner_headers)
    other_headers, _ = _signup(client, email="other@proair.com")
    monkeypatch.setattr("app.api.theme_watches.execute_ingestion_run", lambda run_id: None)

    resp = client.post(f"/theme-watches/{theme['id']}/run-now", headers=other_headers)

    assert resp.status_code == 403


def test_run_now_requires_auth(client):
    resp = client.post(f"/theme-watches/{uuid.uuid4()}/run-now")
    assert resp.status_code == 401


def test_run_now_404s_for_unknown_theme(client, db_session):
    headers = _auth_headers(client)
    _enable_google_news(db_session)
    resp = client.post(f"/theme-watches/{uuid.uuid4()}/run-now", headers=headers)
    assert resp.status_code == 404


# --- Per-theme Google News edition -------------------------------------------------


def test_theme_locale_override_is_normalized(client):
    headers = _auth_headers(client)
    theme = _create_theme(
        client, headers, google_news_country="de", google_news_language="DE"
    )
    assert theme["google_news_country"] == "DE"
    assert theme["google_news_language"] == "de"


def test_theme_locale_defaults_to_inheriting_the_workspace_edition(client):
    headers = _auth_headers(client)
    theme = _create_theme(client, headers)
    assert theme["google_news_country"] is None
    assert theme["google_news_language"] is None


def test_blank_theme_locale_is_stored_as_inherit(client):
    """The frontend's "workspace default" option submits an empty string; it must land as
    NULL so it can't drift from a never-set value."""
    headers = _auth_headers(client)
    theme = _create_theme(client, headers, google_news_country="", google_news_language="")
    assert theme["google_news_country"] is None
    assert theme["google_news_language"] is None


def test_theme_locale_rejects_nonsense_values(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/theme-watches",
        json={"name": "Bad", "query_terms": ["x"], "google_news_country": "D3!"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_theme_locale_can_be_updated_and_cleared(client):
    headers = _auth_headers(client)
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

    headers = _auth_headers(client)
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
