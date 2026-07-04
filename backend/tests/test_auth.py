VALID_INVITE = "test-invite-code"


def test_signup_login_me_flow(client):
    signup_resp = client.post(
        "/auth/signup",
        json={
            "email": "sales@proair.com",
            "password": "s3curePass!",
            "name": "Sales Rep",
            "invite_code": VALID_INVITE,
        },
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


def test_signup_rejects_missing_invite_code(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "noinvite@proair.com", "password": "password123", "name": "A"},
    )
    assert resp.status_code == 422  # invite_code is a required field


def test_signup_rejects_wrong_invite_code(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "wronginvite@proair.com",
            "password": "password123",
            "name": "A",
            "invite_code": "not-the-real-code",
        },
    )
    assert resp.status_code == 403


def test_signup_rejects_short_password(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "shortpw@proair.com",
            "password": "short1",
            "name": "A",
            "invite_code": VALID_INVITE,
        },
    )
    assert resp.status_code == 422


def test_duplicate_signup_rejected_generically(client):
    client.post(
        "/auth/signup",
        json={
            "email": "dup@proair.com",
            "password": "password123",
            "name": "A",
            "invite_code": VALID_INVITE,
        },
    )
    resp = client.post(
        "/auth/signup",
        json={
            "email": "dup@proair.com",
            "password": "password123",
            "name": "B",
            "invite_code": VALID_INVITE,
        },
    )
    assert resp.status_code == 409
    assert "already registered" not in resp.json()["detail"].lower()


def test_login_wrong_password_rejected(client):
    client.post(
        "/auth/signup",
        json={
            "email": "wrongpw@proair.com",
            "password": "correct-pw",
            "name": "A",
            "invite_code": VALID_INVITE,
        },
    )
    resp = client.post(
        "/auth/login", json={"email": "wrongpw@proair.com", "password": "incorrect"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_logout_revokes_existing_token(client):
    signup_resp = client.post(
        "/auth/signup",
        json={
            "email": "logout@proair.com",
            "password": "password123",
            "name": "A",
            "invite_code": VALID_INVITE,
        },
    )
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/auth/me", headers=headers).status_code == 200

    logout_resp = client.post("/auth/logout", headers=headers)
    assert logout_resp.status_code == 204

    after_logout = client.get("/auth/me", headers=headers)
    assert after_logout.status_code == 401


def test_login_immediately_after_logout_still_works(client):
    # Regression test: JWT "iat" only has whole-second precision, but a naive logout
    # implementation could set a microsecond-precision revocation cutoff — rejecting a
    # brand-new token issued in that same wall-clock second. Logout and login here
    # execute back-to-back (typically within the same second in a fast test run),
    # which is exactly the scenario that must not lock the user out of their own
    # fresh login.
    signup_resp = client.post(
        "/auth/signup",
        json={
            "email": "fastlogout@proair.com",
            "password": "password123",
            "name": "A",
            "invite_code": VALID_INVITE,
        },
    )
    first_token = signup_resp.json()["access_token"]
    client.post("/auth/logout", headers={"Authorization": f"Bearer {first_token}"})

    login_resp = client.post(
        "/auth/login", json={"email": "fastlogout@proair.com", "password": "password123"}
    )
    assert login_resp.status_code == 200
    new_token = login_resp.json()["access_token"]

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me_resp.status_code == 200
