def _admin_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "admin@proair.com", "password": "password123", "name": "Admin", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_headers(client):
    # First signup becomes admin automatically, so the second one is a regular user.
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


def _full_update_payload(**overrides):
    payload = {
        "company_name": "ProAir",
        "offering_description": "HVAC equipment and maintenance services.",
        "digest_send_time": "08:30",
        "ingestion_interval_hours": 4,
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
    }
    payload.update(overrides)
    return payload


def test_get_settings_creates_default_row(client):
    headers = _admin_headers(client)
    resp = client.get("/settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == ""
    assert body["ingestion_interval_hours"] == 6
    assert body["mistral_model"] == "mistral-large-latest"
    assert body["mistral_triage_enabled"] is True
    assert body["mistral_dedupe_similarity_threshold"] == 0.9


def test_update_settings(client):
    headers = _admin_headers(client)
    resp = client.put("/settings", json=_full_update_payload(), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == "ProAir"
    assert body["digest_send_time"] == "08:30"
    assert body["ingestion_interval_hours"] == 4


def test_update_settings_changes_mistral_model_choices(client):
    headers = _admin_headers(client)
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
    headers = _admin_headers(client)
    resp = client.get("/settings", headers=headers)
    body = resp.json()
    assert body["mistral_api_key_configured"] is False
    assert body["mistral_api_key_source"] == "unset"
    assert body["mistral_api_key_last4"] is None


def test_mistral_api_key_falls_back_to_env_when_no_override(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-configured-key-abcd")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = _admin_headers(client)
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
    headers = _admin_headers(client)
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
    headers = _admin_headers(client)
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
    headers = _admin_headers(client)
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


def test_settings_require_auth(client):
    resp = client.get("/settings")
    assert resp.status_code == 401


def test_settings_require_admin(client):
    headers = _user_headers(client)
    assert client.get("/settings", headers=headers).status_code == 403
    assert client.put("/settings", json=_full_update_payload(), headers=headers).status_code == 403
