from app.models.article import ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog


def _admin_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "admin@proair.com", "password": "password123", "name": "Admin", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_headers(client):
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


def test_news_usage_requires_auth(client):
    resp = client.get("/news-usage")
    assert resp.status_code == 401


def test_news_usage_requires_admin(client):
    headers = _user_headers(client)
    resp = client.get("/news-usage", headers=headers)
    assert resp.status_code == 403


def test_news_usage_reflects_defaults_when_empty(client):
    headers = _admin_headers(client)
    resp = client.get("/news-usage", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    by_source = {row["source"]: row for row in body["sources"]}
    assert by_source["newsapi"]["enabled"] is True
    assert by_source["newsapi"]["requests_today"] == 0
    assert by_source["google_news_rss"]["enabled"] is False
    assert by_source["newsdata"]["enabled"] is False


def test_news_usage_aggregates_logged_requests(client, db_session):
    headers = _admin_headers(client)
    db_session.add_all(
        [
            NewsSourceUsageLog(source=ArticleSource.NEWSAPI, call_type="latest", requests_used=3, articles_returned=5),
            NewsSourceUsageLog(source=ArticleSource.NEWSAPI, call_type="latest", requests_used=2, articles_returned=1),
        ]
    )
    db_session.commit()

    resp = client.get("/news-usage", headers=headers)
    body = resp.json()
    by_source = {row["source"]: row for row in body["sources"]}
    assert by_source["newsapi"]["requests_today"] == 5
    assert len(by_source["newsapi"]["recent"]) == 2


def test_news_usage_rate_limited_marker_rows_counted_separately(client, db_session):
    headers = _admin_headers(client)
    db_session.add(
        NewsSourceUsageLog(source=ArticleSource.NEWSDATA, call_type="rate_limited", requests_used=0)
    )
    db_session.commit()

    resp = client.get("/news-usage", headers=headers)
    body = resp.json()
    by_source = {row["source"]: row for row in body["sources"]}
    assert by_source["newsdata"]["rate_limited_last_24h"] == 1
    assert by_source["newsdata"]["requests_today"] == 0
