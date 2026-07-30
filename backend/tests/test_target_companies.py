from tests.conftest import auth_headers, signup


def test_create_list_update_delete_target_company(client):
    headers = auth_headers(client)

    create_resp = client.post(
        "/target-companies",
        json={"name": "Acme Corp", "keywords": ["Acme", "acme.com"], "industry": "Manufacturing"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    company = create_resp.json()
    assert company["name"] == "Acme Corp"
    assert company["is_active"] is True
    assert company["is_muted"] is False
    assert company["follower_count"] == 1

    list_resp = client.get("/target-companies", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    patch_resp = client.patch(
        f"/target-companies/{company['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp_after = client.get("/target-companies", headers=headers)
    assert list_resp_after.json() == []


def test_follower_can_edit_name_and_keywords(client):
    headers = auth_headers(client)
    company = client.post(
        "/target-companies",
        json={"name": "Acme Corp", "keywords": ["Acme"], "industry": "Manufacturing"},
        headers=headers,
    ).json()

    patch_resp = client.patch(
        f"/target-companies/{company['id']}",
        json={"name": "Acme Corporation", "keywords": ["Acme", "acme.com"], "industry": "Industrial"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "Acme Corporation"
    assert updated["keywords"] == ["Acme", "acme.com"]
    assert updated["industry"] == "Industrial"


def test_non_creator_follower_cannot_edit_shared_company(client):
    creator_headers, _ = signup(client, email="creator@proair.com")
    other_headers, _ = signup(client, email="other@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=creator_headers
    ).json()
    # Dedupes by name, so this follows the same company created above rather than
    # creating a second one.
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=other_headers)

    patch_resp = client.patch(
        f"/target-companies/{company['id']}", json={"name": "Renamed"}, headers=other_headers
    )
    assert patch_resp.status_code == 403

    # The non-creator follower can still mute/unfollow their own follow, just not
    # rewrite the shared company itself.
    mute_resp = client.post(f"/target-companies/{company['id']}/mute", headers=other_headers)
    assert mute_resp.status_code == 200


def test_keywords_over_max_count_rejected(client):
    headers = auth_headers(client)
    resp = client.post(
        "/target-companies",
        json={"name": "Acme", "keywords": [f"kw{i}" for i in range(21)]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_keyword_over_max_length_rejected(client):
    headers = auth_headers(client)
    resp = client.post(
        "/target-companies",
        json={"name": "Acme", "keywords": ["x" * 101]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_google_news_source_allowlist_rejects_non_hostname(client):
    headers = auth_headers(client)
    resp = client.post(
        "/target-companies",
        json={"name": "Acme", "keywords": [], "google_news_source_allowlist": ["https://reuters.com"]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_google_news_source_allowlist_accepts_bare_hostname(client):
    headers = auth_headers(client)
    resp = client.post(
        "/target-companies",
        json={"name": "Acme", "keywords": [], "google_news_source_allowlist": ["Reuters.com"]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["google_news_source_allowlist"] == ["reuters.com"]


def test_admin_can_edit_name_and_keywords_of_company_they_do_not_follow(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers
    ).json()

    patch_resp = client.patch(
        f"/target-companies/{company['id']}",
        json={"name": "Acme Renamed", "keywords": ["Acme", "Renamed"]},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "Acme Renamed"
    assert updated["keywords"] == ["Acme", "Renamed"]

    # The renamed company is still visible to the following user under its new name.
    listed = client.get("/target-companies", headers=user_headers).json()
    assert listed[0]["name"] == "Acme Renamed"


def test_target_companies_require_auth(client):
    resp = client.get("/target-companies")
    assert resp.status_code == 401


def test_update_missing_target_company_404(client):
    headers = auth_headers(client)
    resp = client.patch(
        "/target-companies/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 404


def test_create_target_company_dedupes_by_name_case_insensitive(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")

    resp_a = client.post(
        "/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=headers_a
    )
    resp_b = client.post(
        "/target-companies", json={"name": "acme corp", "keywords": []}, headers=headers_b
    )
    assert resp_a.json()["id"] == resp_b.json()["id"]
    assert resp_b.json()["follower_count"] == 2

    # Each user only sees it once in their own scoped list, not duplicated.
    assert len(client.get("/target-companies", headers=headers_a).json()) == 1
    assert len(client.get("/target-companies", headers=headers_b).json()) == 1


def test_list_only_shows_own_follows(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a)

    assert len(client.get("/target-companies", headers=headers_a).json()) == 1
    assert len(client.get("/target-companies", headers=headers_b).json()) == 0


def test_patch_and_delete_require_following(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a
    ).json()

    patch_resp = client.patch(
        f"/target-companies/{company['id']}", json={"is_active": False}, headers=headers_b
    )
    assert patch_resp.status_code == 403

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=headers_b)
    assert delete_resp.status_code == 403


def test_unfollow_keeps_company_when_other_followers_remain(client):
    # The first signup in a fresh workspace is auto-promoted to admin, whose delete is
    # always a hard-delete — sign up a throwaway admin first so a/b are regular users.
    signup(client, email="bootstrap-admin@proair.com")
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a
    ).json()
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_b)

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=headers_a)
    assert delete_resp.status_code == 204

    assert client.get("/target-companies", headers=headers_a).json() == []
    remaining = client.get("/target-companies", headers=headers_b).json()
    assert len(remaining) == 1
    assert remaining[0]["follower_count"] == 1


def test_unfollow_as_sole_follower_hard_deletes_company(client):
    headers = auth_headers(client)
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers
    ).json()

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=headers)
    assert delete_resp.status_code == 204
    assert client.get("/target-companies", headers=headers).json() == []


def test_mute_toggle(client):
    headers = auth_headers(client)
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers
    ).json()

    muted = client.post(f"/target-companies/{company['id']}/mute", headers=headers)
    assert muted.status_code == 200
    assert muted.json()["is_muted"] is True

    unmuted = client.post(f"/target-companies/{company['id']}/mute", headers=headers)
    assert unmuted.json()["is_muted"] is False


def test_mute_requires_following(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a
    ).json()

    resp = client.post(f"/target-companies/{company['id']}/mute", headers=headers_b)
    assert resp.status_code == 404


def test_admin_scope_all_lists_full_catalog(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers)

    resp = client.get("/target-companies?scope=all", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["is_muted"] is None


def test_scope_all_is_admin_only(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")

    resp = client.get("/target-companies?scope=all", headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_patch_and_delete_any_company(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers
    ).json()

    patch_resp = client.patch(
        f"/target-companies/{company['id']}", json={"industry": "SaaS"}, headers=admin_headers
    )
    assert patch_resp.status_code == 200

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=admin_headers)
    assert delete_resp.status_code == 204
    # Admin hard-delete removes it for every follower, not just the admin.
    assert client.get("/target-companies", headers=user_headers).json() == []


def test_bulk_delete_removes_multiple_companies(client):
    headers = auth_headers(client)
    acme = client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=headers).json()
    globex = client.post("/target-companies", json={"name": "Globex", "keywords": []}, headers=headers).json()

    resp = client.post(
        "/target-companies/bulk-delete",
        json={"target_company_ids": [acme["id"], globex["id"]]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2, "not_found": 0}
    assert client.get("/target-companies", headers=headers).json() == []


def test_bulk_delete_counts_missing_ids_as_not_found(client):
    headers = auth_headers(client)
    acme = client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=headers).json()

    resp = client.post(
        "/target-companies/bulk-delete",
        json={"target_company_ids": [acme["id"], "00000000-0000-0000-0000-000000000000"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1, "not_found": 1}


def test_bulk_delete_non_admin_only_removes_own_follow(client):
    headers_a, _ = signup(client, email="a@proair.com")
    headers_b, _ = signup(client, email="b@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a
    ).json()

    resp = client.post(
        "/target-companies/bulk-delete",
        json={"target_company_ids": [company["id"]]},
        headers=headers_b,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0, "not_found": 1}
    assert len(client.get("/target-companies", headers=headers_a).json()) == 1


def test_bulk_delete_admin_hard_deletes_for_everyone(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers
    ).json()

    resp = client.post(
        "/target-companies/bulk-delete",
        json={"target_company_ids": [company["id"]]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1, "not_found": 0}
    assert client.get("/target-companies", headers=user_headers).json() == []


def test_bulk_delete_requires_non_empty_list(client):
    headers = auth_headers(client)
    resp = client.post("/target-companies/bulk-delete", json={"target_company_ids": []}, headers=headers)
    assert resp.status_code == 422


def test_followers_endpoint_is_admin_only(client):
    admin_headers, _ = signup(client, email="admin@proair.com")
    user_headers, _ = signup(client, email="rep@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers
    ).json()

    forbidden = client.get(f"/target-companies/{company['id']}/followers", headers=user_headers)
    assert forbidden.status_code == 403

    ok = client.get(f"/target-companies/{company['id']}/followers", headers=admin_headers)
    assert ok.status_code == 200
    assert len(ok.json()) == 1
    assert ok.json()[0]["email"] == "rep@proair.com"


def test_company_terms_split_round_trips_and_derives_keywords(client):
    """keywords stays in the response as a derived field, so existing clients and the CSV
    export keep working while the split fields are the source of truth."""
    headers = auth_headers(client)
    created = client.post(
        "/target-companies",
        json={
            "name": "Acme Corp",
            "aliases": ["Acme"],
            "context_terms": ["Motorsport"],
            "exclusion_terms": ["Aktie"],
        },
        headers=headers,
    ).json()

    assert created["aliases"] == ["Acme"]
    assert created["context_terms"] == ["Motorsport"]
    assert created["exclusion_terms"] == ["Aktie"]
    # Derived: aliases first, then context terms. Exclusions are deliberately absent —
    # they'd otherwise broaden the provider query and steer the AI toward the very
    # subject the user asked to avoid.
    assert created["keywords"] == ["Acme", "Motorsport"]


def test_legacy_keywords_payload_still_works_and_lands_in_context_terms(client):
    """Older clients still PATCH `keywords`; it maps to the role keywords actually played
    in the query rather than overwriting the derived column."""
    headers = auth_headers(client)
    created = client.post(
        "/target-companies", json={"name": "Acme Corp", "keywords": ["Motorsport"]}, headers=headers
    ).json()

    assert created["context_terms"] == ["Motorsport"]
    assert created["aliases"] == []
    assert created["keywords"] == ["Motorsport"]


def test_company_allowlist_has_three_distinct_states(client):
    headers = auth_headers(client)
    created = client.post("/target-companies", json={"name": "Acme"}, headers=headers).json()
    assert created["google_news_source_allowlist"] is None

    unrestricted = client.patch(
        f"/target-companies/{created['id']}",
        json={"google_news_source_allowlist": []},
        headers=headers,
    ).json()
    assert unrestricted["google_news_source_allowlist"] == []

    custom = client.patch(
        f"/target-companies/{created['id']}",
        json={"google_news_source_allowlist": ["heise.de"]},
        headers=headers,
    ).json()
    assert custom["google_news_source_allowlist"] == ["heise.de"]

    # An omitted field must not disturb it — only an explicit null reverts to inheriting.
    untouched = client.patch(
        f"/target-companies/{created['id']}", json={"industry": "Manufacturing"}, headers=headers
    ).json()
    assert untouched["google_news_source_allowlist"] == ["heise.de"]

    reverted = client.patch(
        f"/target-companies/{created['id']}",
        json={"google_news_source_allowlist": None},
        headers=headers,
    ).json()
    assert reverted["google_news_source_allowlist"] is None


def test_company_edition_override_round_trips(client):
    headers = auth_headers(client)
    created = client.post(
        "/target-companies",
        json={"name": "Acme", "google_news_country": "de", "google_news_language": "DE"},
        headers=headers,
    ).json()

    # Normalized to Google's expected casing regardless of how they were typed.
    assert created["google_news_country"] == "DE"
    assert created["google_news_language"] == "de"


def test_company_edition_rejects_a_malformed_country(client):
    resp = client.post(
        "/target-companies",
        json={"name": "Acme", "google_news_country": "D3!"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422
