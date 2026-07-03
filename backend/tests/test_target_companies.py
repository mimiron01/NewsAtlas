def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "rep@proair.com", "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
