def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "admin@proair.com", "password": "password123", "name": "Admin"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_settings_creates_default_row(client):
    headers = _auth_headers(client)
    resp = client.get("/settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == ""
    assert body["ingestion_interval_hours"] == 6


def test_update_settings(client):
    headers = _auth_headers(client)
    resp = client.put(
        "/settings",
        json={
            "company_name": "ProAir",
            "offering_description": "HVAC equipment and maintenance services.",
            "digest_send_time": "08:30",
            "ingestion_interval_hours": 4,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == "ProAir"
    assert body["digest_send_time"] == "08:30"
    assert body["ingestion_interval_hours"] == 4


def test_settings_require_auth(client):
    resp = client.get("/settings")
    assert resp.status_code == 401
