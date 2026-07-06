def _signup(client, email, name="User"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": name, "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    return headers, user_id


def test_first_signup_is_promoted_to_admin(client):
    headers, _user_id = _signup(client, "first@proair.com")
    me = client.get("/auth/me", headers=headers).json()
    assert me["role"] == "admin"


def test_second_signup_is_regular_user(client):
    _signup(client, "first@proair.com")
    headers, _user_id = _signup(client, "second@proair.com")
    me = client.get("/auth/me", headers=headers).json()
    assert me["role"] == "user"


def test_admin_routes_require_admin(client):
    _signup(client, "admin@proair.com")
    user_headers, _ = _signup(client, "user@proair.com")

    assert client.get("/admin/users", headers=user_headers).status_code == 403
    assert (
        client.patch(
            "/admin/users/00000000-0000-0000-0000-000000000000/role",
            json={"role": "admin"},
            headers=user_headers,
        ).status_code
        == 403
    )


def test_admin_can_list_all_users(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    _signup(client, "user@proair.com")

    resp = client.get("/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    emails = {user["email"] for user in resp.json()}
    assert emails == {"admin@proair.com", "user@proair.com"}


def test_admin_can_promote_and_demote_user(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    _, user_id = _signup(client, "user@proair.com")

    promote_resp = client.patch(
        f"/admin/users/{user_id}/role", json={"role": "admin"}, headers=admin_headers
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["role"] == "admin"

    demote_resp = client.patch(
        f"/admin/users/{user_id}/role", json={"role": "user"}, headers=admin_headers
    )
    assert demote_resp.status_code == 200
    assert demote_resp.json()["role"] == "user"


def test_cannot_demote_last_remaining_admin(client):
    admin_headers, admin_id = _signup(client, "admin@proair.com")

    resp = client.patch(
        f"/admin/users/{admin_id}/role", json={"role": "user"}, headers=admin_headers
    )
    assert resp.status_code == 400


def test_can_demote_admin_when_another_admin_remains(client):
    admin_headers, admin_id = _signup(client, "admin@proair.com")
    _, second_id = _signup(client, "second@proair.com")
    client.patch(f"/admin/users/{second_id}/role", json={"role": "admin"}, headers=admin_headers)

    resp = client.patch(
        f"/admin/users/{admin_id}/role", json={"role": "user"}, headers=admin_headers
    )
    assert resp.status_code == 200


def test_role_update_requires_existing_user(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    resp = client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_admin_assigns_new_company_to_user(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    user_headers, user_id = _signup(client, "user@proair.com")

    resp = client.post(
        f"/admin/users/{user_id}/companies",
        json={"name": "Acme Corp", "keywords": ["acme"], "industry": "Manufacturing"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    company = resp.json()
    assert company["name"] == "Acme Corp"

    # The target user sees it in their own list without doing anything.
    user_companies = client.get("/target-companies", headers=user_headers).json()
    assert len(user_companies) == 1
    assert user_companies[0]["id"] == company["id"]


def test_admin_assign_dedupes_with_existing_company(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    user_headers, user_id = _signup(client, "user@proair.com")
    existing = client.post(
        "/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=user_headers
    ).json()

    resp = client.post(
        f"/admin/users/{user_id}/companies",
        json={"name": "acme corp", "keywords": []},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == existing["id"]
    # Following twice is a no-op, not a duplicate follow.
    assert resp.json()["follower_count"] == 1


def test_admin_assign_requires_existing_user(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    resp = client.post(
        "/admin/users/00000000-0000-0000-0000-000000000000/companies",
        json={"name": "Acme Corp", "keywords": []},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_admin_can_unassign_company_from_user(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    user_headers, user_id = _signup(client, "user@proair.com")
    company = client.post(
        "/target-companies", json={"name": "Acme Corp", "keywords": []}, headers=user_headers
    ).json()

    resp = client.delete(
        f"/admin/users/{user_id}/companies/{company['id']}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert client.get("/target-companies", headers=user_headers).json() == []


def test_unassign_requires_existing_follow(client):
    admin_headers, _ = _signup(client, "admin@proair.com")
    _, user_id = _signup(client, "user@proair.com")

    resp = client.delete(
        f"/admin/users/{user_id}/companies/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_admin_endpoints_require_auth(client):
    assert client.get("/admin/users").status_code == 401
