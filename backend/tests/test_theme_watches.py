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


def test_theme_watch_dedupes_by_name_case_insensitive(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")

    resp_a = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    )
    resp_b = client.post(
        "/theme-watches", json={"name": "automotive", "query_terms": ["EV"]}, headers=headers_b
    )
    assert resp_a.json()["id"] == resp_b.json()["id"]
    assert resp_b.json()["follower_count"] == 2


def test_non_creator_follower_cannot_edit_shared_theme(client):
    creator_headers, _ = signup(client, email="creator@proair.com")
    other_headers, _ = signup(client, email="other@proair.com")
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
