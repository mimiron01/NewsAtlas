from tests.conftest import admin_headers, user_headers


def _full_update_payload(**overrides):
    payload = {
        "company_name": "ProAir",
        "offering_description": "HVAC equipment and maintenance services.",
        "digest_send_time": "08:30",
        "max_articles_per_company_per_run": 10,
        "main_language": "en",
        "mistral_model": "mistral-large-latest",
        "mistral_triage_model": "mistral-small-latest",
        "mistral_embed_model": "mistral-embed",
        "mistral_triage_enabled": True,
        "mistral_dedupe_similarity_threshold": 0.9,
        "newsapi_enabled": True,
        "newsapi_max_requests_per_day": 100,
        "google_news_rss_enabled": False,
        "google_news_rss_country": "US",
        "google_news_rss_language": "en",
        "google_news_rss_max_requests_per_minute": 20,
        "newsdata_enabled": False,
        "newsdata_full_content_enabled": True,
        "newsdata_use_native_dedupe": True,
        "newsdata_backfill_days": 0,
        "newsdata_max_requests_per_day": 200,
        "newsdata_max_requests_per_minute": 30,
        "max_articles_per_theme_per_run": 10,
        "max_active_theme_watches": 10,
    }
    payload.update(overrides)
    return payload


def test_get_settings_creates_default_row(client):
    headers = admin_headers(client)
    resp = client.get("/settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == ""
    assert body["main_language"] == "en"
    assert body["mistral_model"] == "mistral-large-latest"
    assert body["mistral_triage_enabled"] is True
    assert body["mistral_dedupe_similarity_threshold"] == 0.9


def test_update_settings(client):
    headers = admin_headers(client)
    resp = client.put("/settings", json=_full_update_payload(), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == "ProAir"
    assert body["digest_send_time"] == "08:30"


def test_update_settings_changes_main_language(client):
    headers = admin_headers(client)
    resp = client.put(
        "/settings", json=_full_update_payload(main_language="de"), headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["main_language"] == "de"

    resp = client.get("/settings", headers=headers)
    assert resp.json()["main_language"] == "de"


def test_update_settings_rejects_unsupported_main_language(client):
    headers = admin_headers(client)
    resp = client.put(
        "/settings", json=_full_update_payload(main_language="fr"), headers=headers
    )
    assert resp.status_code == 422


def test_theme_match_min_relevance_score_defaults_to_three(client):
    headers = admin_headers(client)
    resp = client.get("/settings", headers=headers)
    assert resp.json()["theme_match_min_relevance_score"] == 3


def test_update_settings_changes_theme_match_min_relevance_score(client):
    headers = admin_headers(client)
    resp = client.put(
        "/settings",
        json=_full_update_payload(theme_match_min_relevance_score=1),
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["theme_match_min_relevance_score"] == 1

    resp = client.get("/settings", headers=headers)
    assert resp.json()["theme_match_min_relevance_score"] == 1


def test_update_settings_rejects_out_of_range_theme_match_min_relevance_score(client):
    headers = admin_headers(client)
    resp = client.put(
        "/settings",
        json=_full_update_payload(theme_match_min_relevance_score=6),
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_settings_changes_mistral_model_choices(client):
    headers = admin_headers(client)
    resp = client.put(
        "/settings",
        json=_full_update_payload(
            mistral_model="mistral-medium-latest",
            mistral_triage_enabled=False,
            mistral_dedupe_similarity_threshold=0.75,
        ),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mistral_model"] == "mistral-medium-latest"
    assert body["mistral_triage_enabled"] is False
    assert body["mistral_dedupe_similarity_threshold"] == 0.75


def test_mistral_api_key_unset_by_default_when_no_env_key(client, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = admin_headers(client)
    resp = client.get("/settings", headers=headers)
    body = resp.json()
    assert body["mistral_api_key_configured"] is False
    assert body["mistral_api_key_source"] == "unset"
    assert body["mistral_api_key_last4"] is None


def test_mistral_api_key_falls_back_to_env_when_no_override(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-configured-key-abcd")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = admin_headers(client)
    resp = client.get("/settings", headers=headers)
    body = resp.json()
    assert body["mistral_api_key_configured"] is True
    assert body["mistral_api_key_source"] == "environment"
    assert body["mistral_api_key_last4"] == "abcd"
    get_settings.cache_clear()


def test_mistral_api_key_override_takes_precedence_over_env(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-configured-key-abcd")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = admin_headers(client)
    client.put(
        "/settings",
        json=_full_update_payload(mistral_api_key="sk-in-app-override-wxyz"),
        headers=headers,
    )
    resp = client.get("/settings", headers=headers)
    body = resp.json()
    assert body["mistral_api_key_configured"] is True
    assert body["mistral_api_key_source"] == "workspace"
    assert body["mistral_api_key_last4"] == "wxyz"
    get_settings.cache_clear()


def test_mistral_api_key_omitted_from_payload_leaves_it_unchanged(client):
    headers = admin_headers(client)
    client.put(
        "/settings",
        json=_full_update_payload(mistral_api_key="sk-first-value-1111"),
        headers=headers,
    )
    resp = client.put("/settings", json=_full_update_payload(), headers=headers)
    body = resp.json()
    assert body["mistral_api_key_source"] == "workspace"
    assert body["mistral_api_key_last4"] == "1111"


def test_mistral_api_key_empty_string_clears_override(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-configured-key-abcd")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = admin_headers(client)
    client.put(
        "/settings",
        json=_full_update_payload(mistral_api_key="sk-in-app-override-wxyz"),
        headers=headers,
    )
    resp = client.put("/settings", json=_full_update_payload(mistral_api_key=""), headers=headers)
    body = resp.json()
    assert body["mistral_api_key_source"] == "environment"
    assert body["mistral_api_key_last4"] == "abcd"
    get_settings.cache_clear()


def test_mistral_api_key_stored_encrypted_at_rest(client, db_session):
    headers = admin_headers(client)
    client.put(
        "/settings",
        json=_full_update_payload(mistral_api_key="sk-super-secret-plaintext-value"),
        headers=headers,
    )
    from app.models.workspace_settings import WorkspaceSettings

    row = db_session.query(WorkspaceSettings).first()
    assert row.mistral_api_key != "sk-super-secret-plaintext-value"
    assert "sk-super-secret-plaintext-value" not in row.mistral_api_key


def test_newsdata_api_key_stored_encrypted_at_rest(client, db_session):
    headers = admin_headers(client)
    client.put(
        "/settings",
        json=_full_update_payload(newsdata_enabled=True, newsdata_api_key="nd-super-secret-plaintext"),
        headers=headers,
    )
    from app.models.workspace_settings import WorkspaceSettings

    row = db_session.query(WorkspaceSettings).first()
    assert row.newsdata_api_key != "nd-super-secret-plaintext"
    assert "nd-super-secret-plaintext" not in row.newsdata_api_key


def test_settings_require_auth(client):
    resp = client.get("/settings")
    assert resp.status_code == 401


def test_settings_require_admin(client):
    headers = user_headers(client)
    assert client.get("/settings", headers=headers).status_code == 403
    assert client.put("/settings", json=_full_update_payload(), headers=headers).status_code == 403


# --- GET /settings/public ----------------------------------------------------------


def test_public_settings_readable_by_non_admin(client):
    """The admin-only GET /settings left a non-admin with no way to learn that Google News
    RSS (the only source themes can use) is switched off — which is why their topics
    silently returned nothing."""
    # _user_headers signs the admin up first, so this covers both roles.
    member_headers = user_headers(client)

    assert client.get("/settings", headers=member_headers).status_code == 403

    resp = client.get("/settings/public", headers=member_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Google News RSS ships on (and NewsAPI/NewsData off) for new workspaces, so a fresh
    # install can fetch real results with zero source configuration (see F1 in
    # docs/platform-usability-onboarding-review.html).
    assert body["google_news_rss_enabled"] is True
    assert body["google_news_rss_country"] == "US"
    assert body["google_news_rss_language"] == "en"
    assert body["any_news_source_enabled"] is True
    # Nothing sensitive leaks through the non-admin door: no key status, no quotas, no AI
    # configuration.
    assert body["manual_trigger_cooldown_seconds"] > 0
    assert set(body) == {
        "google_news_rss_enabled",
        "google_news_rss_country",
        "google_news_rss_language",
        "any_news_source_enabled",
        "manual_trigger_cooldown_seconds",
    }


def test_public_settings_any_news_source_enabled_reflects_all_three_providers(client):
    """any_news_source_enabled has to OR across all three providers, not just Google News
    RSS — companies check every enabled provider, not only the one topics are restricted
    to (see F1 in docs/platform-usability-onboarding-review.html)."""
    admin = admin_headers(client)
    payload = _full_update_payload(
        newsapi_enabled=False, google_news_rss_enabled=False, newsdata_enabled=False
    )
    resp = client.put("/settings", json=payload, headers=admin)
    assert resp.status_code == 200

    body = client.get("/settings/public", headers=admin).json()
    assert body["any_news_source_enabled"] is False

    payload = _full_update_payload(
        newsapi_enabled=True, google_news_rss_enabled=False, newsdata_enabled=False
    )
    assert client.put("/settings", json=payload, headers=admin).status_code == 200
    body = client.get("/settings/public", headers=admin).json()
    assert body["any_news_source_enabled"] is True


def test_public_settings_requires_auth(client):
    assert client.get("/settings/public").status_code == 401
