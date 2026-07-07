from datetime import datetime, timezone

from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal
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


def _make_signal(db_session, company_name="Acme Corp") -> Signal:
    target_company = TargetCompany(name=company_name, keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title="Acme raises $10M",
        url=f"https://example.com/{company_name.lower().replace(' ', '-')}",
        description="desc",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    signal = Signal(
        article_id=article.id,
        summary="Acme raised funding",
        business_relevance="They have budget now",
        outreach_snippet_email="Congrats on the raise...",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal


def _follow(db_session, user_id, target_company_id) -> None:
    db_session.add(CompanyFollow(user_id=user_id, target_company_id=target_company_id))
    db_session.commit()


def test_favorite_requires_auth(client, db_session):
    signal = _make_signal(db_session)
    resp = client.post(f"/signals/{signal.id}/favorite")
    assert resp.status_code == 401


def test_favorite_and_unfavorite_round_trip(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp = client.get("/signals", headers=headers)
    assert resp.json()[0]["is_favorited"] is False

    resp = client.post(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is True

    # Idempotent: favoriting twice doesn't error or duplicate.
    resp = client.post(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is True

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.json()["is_favorited"] is True

    resp = client.delete(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is False

    # Idempotent: unfavoriting when not favorited doesn't error.
    resp = client.delete(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is False


def test_favorite_inaccessible_signal_404s(client, db_session):
    headers, _user_id = _signup(client)
    signal = _make_signal(db_session)

    resp = client.post(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 404


def test_favorites_are_per_user(client, db_session):
    headers_a, user_a = _signup(client, email="a@proair.com")
    headers_b, user_b = _signup(client, email="b@proair.com")
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_a, article.target_company_id)
    _follow(db_session, user_b, article.target_company_id)

    client.post(f"/signals/{signal.id}/favorite", headers=headers_a)

    resp_a = client.get(f"/signals/{signal.id}", headers=headers_a)
    resp_b = client.get(f"/signals/{signal.id}", headers=headers_b)
    assert resp_a.json()["is_favorited"] is True
    assert resp_b.json()["is_favorited"] is False


def test_filter_signals_by_favorited(client, db_session):
    headers, user_id = _signup(client)
    favorited = _make_signal(db_session, company_name="Acme Corp")
    favorited_article = db_session.get(Article, favorited.article_id)
    _follow(db_session, user_id, favorited_article.target_company_id)
    other = _make_signal(db_session, company_name="Globex")
    other_article = db_session.get(Article, other.article_id)
    _follow(db_session, user_id, other_article.target_company_id)

    client.post(f"/signals/{favorited.id}/favorite", headers=headers)

    resp = client.get("/signals?favorited=true", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(favorited.id)

    resp_all = client.get("/signals", headers=headers)
    assert len(resp_all.json()) == 2
