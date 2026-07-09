import uuid


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


def test_create_list_update_delete_target_company(client):
    headers = _auth_headers(client)

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
    headers = _auth_headers(client)
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


def test_admin_can_edit_name_and_keywords_of_company_they_do_not_follow(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
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
    headers = _auth_headers(client)
    resp = client.patch(
        "/target-companies/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 404


def test_create_target_company_dedupes_by_name_case_insensitive(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")

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
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a)

    assert len(client.get("/target-companies", headers=headers_a).json()) == 1
    assert len(client.get("/target-companies", headers=headers_b).json()) == 0


def test_patch_and_delete_require_following(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
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
    _signup(client, email="bootstrap-admin@proair.com")
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
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
    headers = _auth_headers(client)
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers
    ).json()

    delete_resp = client.delete(f"/target-companies/{company['id']}", headers=headers)
    assert delete_resp.status_code == 204
    assert client.get("/target-companies", headers=headers).json() == []


def test_mute_toggle(client):
    headers = _auth_headers(client)
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers
    ).json()

    muted = client.post(f"/target-companies/{company['id']}/mute", headers=headers)
    assert muted.status_code == 200
    assert muted.json()["is_muted"] is True

    unmuted = client.post(f"/target-companies/{company['id']}/mute", headers=headers)
    assert unmuted.json()["is_muted"] is False


def test_mute_requires_following(client):
    headers_a, _ = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=headers_a
    ).json()

    resp = client.post(f"/target-companies/{company['id']}/mute", headers=headers_b)
    assert resp.status_code == 404


def test_admin_scope_all_lists_full_catalog(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
    client.post("/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers)

    resp = client.get("/target-companies?scope=all", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["is_muted"] is None


def test_scope_all_is_admin_only(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")

    resp = client.get("/target-companies?scope=all", headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_patch_and_delete_any_company(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
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


def test_followers_endpoint_is_admin_only(client):
    admin_headers, _ = _signup(client, email="admin@proair.com")
    user_headers, _ = _signup(client, email="rep@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme", "keywords": []}, headers=user_headers
    ).json()

    forbidden = client.get(f"/target-companies/{company['id']}/followers", headers=user_headers)
    assert forbidden.status_code == 403

    ok = client.get(f"/target-companies/{company['id']}/followers", headers=admin_headers)
    assert ok.status_code == 200
    assert len(ok.json()) == 1
    assert ok.json()[0]["email"] == "rep@proair.com"
