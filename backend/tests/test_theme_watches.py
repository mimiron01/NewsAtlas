from app.services.workspace_settings import get_or_create_workspace_settings

from tests.conftest import admin_headers, auth_headers, signup


def test_create_list_update_delete_theme_watch(client):
    headers = auth_headers(client)

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
    headers = auth_headers(client)
    resp = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": []}, headers=headers
    )
    assert resp.status_code == 422


def test_theme_watch_duplicate_name_requires_confirmation(client):
    """See docs/topics-ux-improvements-planning.html §1.4: creating a topic whose name
    already exists (case-insensitive) no longer silently merges — it 409s with the
    existing topic's id/terms so the frontend can show an explicit choice."""
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")

    resp_a = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    )
    theme_a = resp_a.json()

    conflict_resp = client.post(
        "/theme-watches", json={"name": "automotive", "query_terms": ["EV"]}, headers=headers_b
    )
    assert conflict_resp.status_code == 409
    detail = conflict_resp.json()["detail"]
    assert detail["code"] == "duplicate_name"
    assert detail["existing_id"] == theme_a["id"]
    assert detail["existing_query_terms"] == ["EV"]


def test_theme_watch_dedupes_by_name_case_insensitive_with_confirm_merge(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")

    resp_a = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    )
    resp_b = client.post(
        "/theme-watches",
        json={"name": "automotive", "query_terms": ["EV"], "confirm_merge": True},
        headers=headers_b,
    )
    assert resp_b.status_code == 201
    assert resp_a.json()["id"] == resp_b.json()["id"]
    assert resp_b.json()["follower_count"] == 2


def test_non_creator_follower_cannot_edit_shared_theme(client):
    creator_headers, _ = signup(client, email="creator@proair.com")
    other_headers, _ = signup(client, email="other@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=creator_headers
    ).json()
    client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV"], "confirm_merge": True},
        headers=other_headers,
    )

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"name": "Renamed"}, headers=other_headers
    )
    assert patch_resp.status_code == 403

    mute_resp = client.post(f"/theme-watches/{theme['id']}/mute", headers=other_headers)
    assert mute_resp.status_code == 200


def test_admin_can_edit_theme_they_do_not_follow(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
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
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
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
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    ).json()

    resp = client.post(f"/theme-watches/{theme['id']}/mute", headers=headers_b)
    assert resp.status_code == 404


def test_admin_scope_all_lists_full_catalog(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=user_headers
    )

    resp = client.get("/theme-watches?scope=all", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["is_muted"] is None


def test_scope_all_is_admin_only(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")

    resp = client.get("/theme-watches?scope=all", headers=user_headers)
    assert resp.status_code == 403


def test_followers_endpoint_is_admin_only(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
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
    headers = auth_headers(client)
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
    headers = auth_headers(client)
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
    headers = auth_headers(client)
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



def test_theme_source_selection_round_trips(client):
    """news_sources distinguishes null (inherit the workspace default) from an explicit
    list, so both states have to survive create/update rather than collapsing."""
    headers = admin_headers(client)
    created = client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV battery"]},
        headers=headers,
    ).json()
    assert created["news_sources"] is None

    updated = client.patch(
        f"/theme-watches/{created['id']}",
        json={"news_sources": ["newsapi", "google_news_rss"]},
        headers=headers,
    ).json()
    assert updated["news_sources"] == ["newsapi", "google_news_rss"]

    reverted = client.patch(
        f"/theme-watches/{created['id']}", json={"news_sources": None}, headers=headers
    ).json()
    assert reverted["news_sources"] is None


def test_theme_rejects_an_unknown_news_source(client):
    resp = client.post(
        "/theme-watches",
        json={"name": "Bad", "query_terms": ["x"], "news_sources": ["bing_news"]},
        headers=admin_headers(client),
    )
    assert resp.status_code == 422


def test_theme_watch_round_trips_exclude_terms(client):
    headers = auth_headers(client)
    create_resp = client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV"], "exclude_terms": ["insurance"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    theme = create_resp.json()
    assert theme["exclude_terms"] == ["insurance"]

    patch_resp = client.patch(
        f"/theme-watches/{theme['id']}", json={"exclude_terms": ["insurance", "used car"]}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["exclude_terms"] == ["insurance", "used car"]


def test_theme_watch_exclude_terms_respects_term_cap(client):
    headers = auth_headers(client)
    resp = client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV"], "exclude_terms": [f"term{i}" for i in range(21)]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_theme_allowlist_distinguishes_inherit_from_unrestricted(client):
    headers = admin_headers(client)
    created = client.post(
        "/theme-watches",
        json={"name": "Automotive", "query_terms": ["EV battery"]},
        headers=headers,
    ).json()
    assert created["google_news_source_allowlist"] is None

    unrestricted = client.patch(
        f"/theme-watches/{created['id']}",
        json={"google_news_source_allowlist": []},
        headers=headers,
    ).json()
    assert unrestricted["google_news_source_allowlist"] == []


# --- Query preview (POST /theme-watches/preview) -----------------------------------


def _enable_google_news(db_session):
    settings = get_or_create_workspace_settings(db_session)
    settings.google_news_rss_enabled = True
    db_session.commit()
    return settings


def test_preview_theme_query_requires_google_news_enabled(client, db_session):
    headers = auth_headers(client)
    # Google News RSS now defaults to enabled for new workspaces (see F1 in
    # docs/platform-usability-onboarding-review.html), so disable it explicitly to hit
    # the validation path this test is actually about.
    settings = get_or_create_workspace_settings(db_session)
    settings.google_news_rss_enabled = False
    db_session.commit()

    resp = client.post(
        "/theme-watches/preview", json={"query_terms": ["Automotive"]}, headers=headers
    )
    assert resp.status_code == 400


def test_preview_theme_query_returns_sample_headlines(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)

    from app.services.news_client import FetchOutcome, NewsArticle

    fake_articles = [
        NewsArticle(
            title=f"Automotive headline {i}",
            url=f"https://example.com/{i}",
            source_name="Example",
            description="",
            published_at=None,
        )
        for i in range(3)
    ]
    # The client returns a FetchOutcome now, carrying the query it sent and the funnel
    # counters alongside the articles (see docs/google-news-quality-planning.html §5.1).
    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles",
        lambda self, **kwargs: FetchOutcome(
            articles=fake_articles, requests_used=1, articles_raw=len(fake_articles)
        ),
    )

    resp = client.post(
        "/theme-watches/preview",
        json={"query_terms": ["Automotive"], "exclude_terms": ["insurance"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["article_count"] == 3
    assert body["sample_headlines"] == [a.title for a in fake_articles]


def test_preview_theme_query_never_persists_anything(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_google_news(db_session)
    from app.services.news_client import FetchOutcome

    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles",
        lambda self, **kwargs: FetchOutcome(articles=[], requests_used=1),
    )

    client.post("/theme-watches/preview", json={"query_terms": ["Automotive"]}, headers=headers)

    assert client.get("/theme-watches", headers=headers).json() == []


# --- Digest opt-in toggle (§4.3) ----------------------------------------------------


def test_toggle_digest_inclusion_defaults_off_and_flips(client):
    headers = auth_headers(client)
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    ).json()
    assert theme["include_in_digest"] is False

    toggled = client.post(f"/theme-watches/{theme['id']}/digest", headers=headers)
    assert toggled.status_code == 200
    assert toggled.json()["include_in_digest"] is True

    toggled_again = client.post(f"/theme-watches/{theme['id']}/digest", headers=headers)
    assert toggled_again.json()["include_in_digest"] is False


def test_toggle_digest_inclusion_requires_following(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    ).json()

    resp = client.post(f"/theme-watches/{theme['id']}/digest", headers=headers_b)
    assert resp.status_code == 404


# --- Bulk delete (§4.4) --------------------------------------------------------------


def test_bulk_delete_removes_multiple_topics(client):
    headers = auth_headers(client)
    automotive = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    ).json()
    fintech = client.post(
        "/theme-watches", json={"name": "Fintech", "query_terms": ["payments"]}, headers=headers
    ).json()

    resp = client.post(
        "/theme-watches/bulk-delete",
        json={"theme_watch_ids": [automotive["id"], fintech["id"]]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2, "not_found": 0}
    assert client.get("/theme-watches", headers=headers).json() == []


def test_bulk_delete_counts_missing_ids_as_not_found(client):
    headers = auth_headers(client)
    automotive = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    ).json()

    resp = client.post(
        "/theme-watches/bulk-delete",
        json={"theme_watch_ids": [automotive["id"], "00000000-0000-0000-0000-000000000000"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1, "not_found": 1}


def test_bulk_delete_non_admin_only_removes_own_follow(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    ).json()

    resp = client.post(
        "/theme-watches/bulk-delete", json={"theme_watch_ids": [theme["id"]]}, headers=headers_b
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0, "not_found": 1}
    assert len(client.get("/theme-watches", headers=headers_a).json()) == 1


def test_bulk_delete_admin_hard_deletes_for_everyone(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    theme = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=user_headers
    ).json()

    resp = client.post(
        "/theme-watches/bulk-delete", json={"theme_watch_ids": [theme["id"]]}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1, "not_found": 0}
    assert client.get("/theme-watches", headers=user_headers).json() == []


def test_bulk_delete_requires_non_empty_list(client):
    headers = auth_headers(client)
    resp = client.post("/theme-watches/bulk-delete", json={"theme_watch_ids": []}, headers=headers)
    assert resp.status_code == 422


def test_preview_theme_query_counts_against_the_google_news_ceiling(client, db_session, monkeypatch):
    """The preview makes a real outbound request per call, so it has to be visible to the
    workspace's self-imposed Google News ceiling — otherwise N users previewing is N×30
    uncounted fetches/hour against a feed that has no official quota and can block us."""
    from app.models.article import ArticleSource
    from app.models.news_source_usage_log import NewsSourceUsageLog
    from app.services.news_client import FetchOutcome

    headers = auth_headers(client)
    _enable_google_news(db_session)
    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles",
        lambda self, **kwargs: FetchOutcome(articles=[], requests_used=1, query_text="Automotive"),
    )

    client.post("/theme-watches/preview", json={"query_terms": ["Automotive"]}, headers=headers)

    log = db_session.query(NewsSourceUsageLog).one()
    assert log.call_type == "preview"
    assert log.source == ArticleSource.GOOGLE_NEWS_RSS
    assert log.requests_used == 1


def test_preview_theme_query_is_refused_when_the_ceiling_is_reached(client, db_session, monkeypatch):
    from app.models.article import ArticleSource
    from app.services.news_usage import log_usage

    headers = auth_headers(client)
    settings = _enable_google_news(db_session)
    settings.google_news_rss_max_requests_per_minute = 1
    db_session.commit()
    log_usage(db_session, source=ArticleSource.GOOGLE_NEWS_RSS, target_company_id=None)

    def explode(self, **kwargs):
        raise AssertionError("no outbound request may be made once the ceiling is reached")

    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles", explode
    )

    resp = client.post(
        "/theme-watches/preview", json={"query_terms": ["Automotive"]}, headers=headers
    )
    assert resp.status_code == 429


def test_preview_theme_query_uses_override_allowlist_semantics(client, db_session, monkeypatch):
    """The preview must build the same query the saved topic will run, or it reports on a
    search nobody is going to perform. An explicitly empty allowlist means "search
    everything", not "fall back to the workspace list"."""
    from app.services.news_client import FetchOutcome

    headers = auth_headers(client)
    settings = _enable_google_news(db_session)
    settings.google_news_source_allowlist = ["reuters.com"]
    db_session.commit()

    captured: dict = {}

    def capture(self, **kwargs):
        captured.update(kwargs)
        return FetchOutcome(articles=[], requests_used=1)

    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles", capture
    )

    client.post(
        "/theme-watches/preview",
        json={"query_terms": ["Automotive"], "google_news_source_allowlist": []},
        headers=headers,
    )
    assert "site:" not in captured["query_override"]

    client.post(
        "/theme-watches/preview",
        json={"query_terms": ["Automotive"]},
        headers=headers,
    )
    assert "site:reuters.com" in captured["query_override"]


def test_preview_theme_query_includes_exclusions_and_the_freshness_operator(
    client, db_session, monkeypatch
):
    from app.services.news_client import FetchOutcome

    headers = auth_headers(client)
    _enable_google_news(db_session)
    captured: dict = {}

    def capture(self, **kwargs):
        captured.update(kwargs)
        return FetchOutcome(articles=[], requests_used=1)

    monkeypatch.setattr(
        "app.services.google_news_rss_client.GoogleNewsRSSClient.fetch_articles", capture
    )

    client.post(
        "/theme-watches/preview",
        json={
            "query_terms": ["Automotive"],
            "exclude_terms": ["insurance"],
            "google_news_source_denylist": ["msn.com"],
        },
        headers=headers,
    )

    assert "-insurance" in captured["query_override"]
    assert "-site:msn.com" in captured["query_override"]
    assert "when:" in captured["query_override"]
