def test_signup_login_me_flow(client):
    signup_resp = client.post(
        "/auth/signup",
        json={"email": "sales@proair.com", "password": "s3curePass!", "name": "Sales Rep"},
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["access_token"]

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "sales@proair.com"

    login_resp = client.post(
        "/auth/login", json={"email": "sales@proair.com", "password": "s3curePass!"}
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_duplicate_signup_rejected(client):
    client.post(
        "/auth/signup",
        json={"email": "dup@proair.com", "password": "password123", "name": "A"},
    )
    resp = client.post(
        "/auth/signup",
        json={"email": "dup@proair.com", "password": "password123", "name": "B"},
    )
    assert resp.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post(
        "/auth/signup",
        json={"email": "wrongpw@proair.com", "password": "correct-pw", "name": "A"},
    )
    resp = client.post(
        "/auth/login", json={"email": "wrongpw@proair.com", "password": "incorrect"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
