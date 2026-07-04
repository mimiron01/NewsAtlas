import pytest

from app.core.limiter import limiter


@pytest.fixture()
def rate_limiting_enabled():
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.enabled = False
    limiter.reset()


def test_login_is_rate_limited_per_ip(client, rate_limiting_enabled):
    payload = {"email": "nobody@proair.com", "password": "wrong-password"}
    responses = [client.post("/auth/login", json=payload) for _ in range(11)]

    assert all(r.status_code == 401 for r in responses[:10])
    assert responses[10].status_code == 429


def test_signup_is_rate_limited_per_ip(client, rate_limiting_enabled):
    def signup(n: int):
        return client.post(
            "/auth/signup",
            json={
                "email": f"ratelimit{n}@proair.com",
                "password": "password123",
                "name": "A",
                "invite_code": "wrong-code",  # rejected for a different reason, still counts
            },
        )

    responses = [signup(n) for n in range(6)]
    assert all(r.status_code == 403 for r in responses[:5])
    assert responses[5].status_code == 429
