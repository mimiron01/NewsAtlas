from datetime import datetime, timezone

from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal, SignalStatus
from app.models.target_company import TargetCompany


def _signup(client, email="rep@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    return headers, user_id


def _make_signal(
    db_session, company_name="Acme Corp", relevance_score=None, status=SignalStatus.NEW
) -> Signal:
    target_company = TargetCompany(name=company_name, keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title=f"{company_name} news",
        url=f"https://example.com/{company_name.lower().replace(' ', '-')}-{relevance_score}-{status}",
        description="desc",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    signal = Signal(
        article_id=article.id,
        summary="summary",
        business_relevance="relevance",
        outreach_snippet_email="snippet",
        relevance_score=relevance_score,
        status=status,
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal


def _follow(db_session, user_id, target_company_id) -> None:
    db_session.add(CompanyFollow(user_id=user_id, target_company_id=target_company_id))
    db_session.commit()


def test_dashboard_requires_auth(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 401


def test_dashboard_empty_state(client, db_session):
    headers, _user_id = _signup(client)
    resp = client.get("/dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "top_signals": [],
        "new_signal_count": 0,
        "favorite_count": 0,
        "recent_favorites": [],
        "open_todo_count": 0,
        "open_todos": [],
        "dismissed_signal_count": 0,
        "skipped_article_count": 0,
    }


def test_dashboard_top_signals_ranked_by_relevance_then_recency(client, db_session):
    headers, user_id = _signup(client)
    low = _make_signal(db_session, company_name="LowCo", relevance_score=2)
    high = _make_signal(db_session, company_name="HighCo", relevance_score=5)
    unscored = _make_signal(db_session, company_name="UnscoredCo", relevance_score=None)
    for s in (low, high, unscored):
        article = db_session.get(Article, s.article_id)
        _follow(db_session, user_id, article.target_company_id)

    resp = client.get("/dashboard", headers=headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(high.id), str(low.id), str(unscored.id)]


def test_dashboard_excludes_archived_and_dismissed_from_top_signals(client, db_session):
    headers, user_id = _signup(client)
    new_signal = _make_signal(db_session, company_name="NewCo", status=SignalStatus.NEW)
    archived = _make_signal(db_session, company_name="ArchivedCo", status=SignalStatus.ARCHIVED)
    dismissed = _make_signal(db_session, company_name="DismissedCo", status=SignalStatus.DISMISSED)
    for s in (new_signal, archived, dismissed):
        article = db_session.get(Article, s.article_id)
        _follow(db_session, user_id, article.target_company_id)

    resp = client.get("/dashboard", headers=headers)
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(new_signal.id)]
    assert resp.json()["new_signal_count"] == 1


def test_dashboard_excludes_muted_companies(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    db_session.add(
        CompanyFollow(user_id=user_id, target_company_id=article.target_company_id, is_muted=True)
    )
    db_session.commit()

    resp = client.get("/dashboard", headers=headers)
    assert resp.json()["top_signals"] == []
    assert resp.json()["new_signal_count"] == 0


def test_dashboard_recent_favorites_and_favorite_count(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    client.post(f"/signals/{signal.id}/favorite", headers=headers)

    resp = client.get("/dashboard", headers=headers)
    body = resp.json()
    assert body["favorite_count"] == 1
    assert len(body["recent_favorites"]) == 1
    assert body["recent_favorites"][0]["id"] == str(signal.id)
    assert body["recent_favorites"][0]["is_favorited"] is True


def test_dashboard_open_todos_and_count(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp1 = client.post(f"/signals/{signal.id}/todos", json={"text": "open task"}, headers=headers)
    resp2 = client.post(f"/signals/{signal.id}/todos", json={"text": "done task"}, headers=headers)
    client.patch(f"/todos/{resp2.json()['id']}", json={"is_done": True}, headers=headers)

    resp = client.get("/dashboard", headers=headers)
    body = resp.json()
    assert body["open_todo_count"] == 1
    assert len(body["open_todos"]) == 1
    assert body["open_todos"][0]["id"] == resp1.json()["id"]
    assert body["open_todos"][0]["target_company_name"] == "Acme Corp"


def test_dashboard_scoped_to_followed_companies_only(client, db_session):
    headers, user_id = _signup(client)
    followed = _make_signal(db_session, company_name="Acme Corp")
    followed_article = db_session.get(Article, followed.article_id)
    _follow(db_session, user_id, followed_article.target_company_id)
    _make_signal(db_session, company_name="Globex")

    resp = client.get("/dashboard", headers=headers)
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(followed.id)]


def test_dashboard_dismissed_signal_count_scoped_to_follows(client, db_session):
    headers, user_id = _signup(client)
    dismissed = _make_signal(db_session, company_name="Acme Corp", status=SignalStatus.DISMISSED)
    dismissed_article = db_session.get(Article, dismissed.article_id)
    _follow(db_session, user_id, dismissed_article.target_company_id)
    # Not followed, so it shouldn't count for this user.
    _make_signal(db_session, company_name="Globex", status=SignalStatus.DISMISSED)

    resp = client.get("/dashboard", headers=headers)
    assert resp.json()["dismissed_signal_count"] == 1


def test_dashboard_skipped_article_count_admin_only(client, db_session):
    target_company = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)
    db_session.add(
        Article(
            target_company_id=target_company.id,
            source_name="Reuters",
            title="Low relevance story",
            url="https://example.com/low-relevance",
            skip_reason="triaged_out",
        )
    )
    db_session.commit()

    # First signup in a fresh workspace is auto-promoted to admin.
    admin_headers, _ = _signup(client, email="admin@proair.com")
    admin_resp = client.get("/dashboard", headers=admin_headers)
    assert admin_resp.json()["skipped_article_count"] == 1

    user_headers, _ = _signup(client, email="rep@proair.com")
    user_resp = client.get("/dashboard", headers=user_headers)
    assert user_resp.json()["skipped_article_count"] == 0
