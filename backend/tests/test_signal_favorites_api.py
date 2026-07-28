from app.models.article import Article

from tests.conftest import follow_company, make_signal, signup


def test_favorite_requires_auth(client, db_session):
    signal = make_signal(db_session)
    resp = client.post(f"/signals/{signal.id}/favorite")
    assert resp.status_code == 401


def test_favorite_and_unfavorite_round_trip(client, db_session):
    headers, user_id = signup(client)
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

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
    headers, _user_id = signup(client)
    signal = make_signal(db_session)

    resp = client.post(f"/signals/{signal.id}/favorite", headers=headers)
    assert resp.status_code == 404


def test_favorites_are_per_user(client, db_session):
    headers_a, user_a = signup(client, email="a@proair.com")
    headers_b, user_b = signup(client, email="b@proair.com")
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_a, article.target_company_id)
    follow_company(db_session, user_b, article.target_company_id)

    client.post(f"/signals/{signal.id}/favorite", headers=headers_a)

    resp_a = client.get(f"/signals/{signal.id}", headers=headers_a)
    resp_b = client.get(f"/signals/{signal.id}", headers=headers_b)
    assert resp_a.json()["is_favorited"] is True
    assert resp_b.json()["is_favorited"] is False


def test_filter_signals_by_favorited(client, db_session):
    headers, user_id = signup(client)
    favorited = make_signal(db_session, company_name="Acme Corp")
    favorited_article = db_session.get(Article, favorited.article_id)
    follow_company(db_session, user_id, favorited_article.target_company_id)
    other = make_signal(db_session, company_name="Globex")
    other_article = db_session.get(Article, other.article_id)
    follow_company(db_session, user_id, other_article.target_company_id)

    client.post(f"/signals/{favorited.id}/favorite", headers=headers)

    resp = client.get("/signals?favorited=true", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(favorited.id)

    resp_all = client.get("/signals", headers=headers)
    assert len(resp_all.json()) == 2
