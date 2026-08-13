from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import SignalStatus

from tests.conftest import follow_company, make_signal, signup


def test_list_signals_requires_auth(client):
    resp = client.get("/signals")
    assert resp.status_code == 401


def test_list_signals_returns_joined_data(client, db_session):
    headers, user_id = signup(client)
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

    resp = client.get("/signals", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(signal.id)
    assert body[0]["target_company_name"] == "Acme Corp"
    assert body[0]["article_title"] == "Acme raises $10M"
    assert body[0]["status"] == "new"


def test_list_signals_excludes_unfollowed_companies(client, db_session):
    headers, user_id = signup(client)
    followed = make_signal(db_session, company_name="Acme Corp")
    followed_article = db_session.get(Article, followed.article_id)
    follow_company(db_session, user_id, followed_article.target_company_id)
    make_signal(db_session, company_name="Globex")

    resp = client.get("/signals", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["target_company_name"] == "Acme Corp"


def test_list_signals_excludes_muted_companies(client, db_session):
    headers, user_id = signup(client)
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    db_session.add(
        CompanyFollow(user_id=user_id, target_company_id=article.target_company_id, is_muted=True)
    )
    db_session.commit()

    resp = client.get("/signals", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_signals_default_excludes_archived_and_dismissed(client, db_session):
    headers, user_id = signup(client)
    active = make_signal(db_session, company_name="Acme Corp")
    active_article = db_session.get(Article, active.article_id)
    follow_company(db_session, user_id, active_article.target_company_id)

    archived = make_signal(db_session, company_name="ArchivedCo")
    archived.status = SignalStatus.ARCHIVED
    archived_article = db_session.get(Article, archived.article_id)
    follow_company(db_session, user_id, archived_article.target_company_id)

    dismissed = make_signal(db_session, company_name="DismissedCo")
    dismissed.status = SignalStatus.DISMISSED
    dismissed_article = db_session.get(Article, dismissed.article_id)
    follow_company(db_session, user_id, dismissed_article.target_company_id)
    db_session.commit()

    resp = client.get("/signals", headers=headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert ids == [str(active.id)]

    archived_resp = client.get("/signals?status=archived", headers=headers)
    assert [s["id"] for s in archived_resp.json()] == [str(archived.id)]

    dismissed_resp = client.get("/signals?status=dismissed", headers=headers)
    assert [s["id"] for s in dismissed_resp.json()] == [str(dismissed.id)]


def test_filter_signals_by_company_and_status(client, db_session):
    headers, user_id = signup(client)
    acme = make_signal(db_session, company_name="Acme Corp")
    acme_article = db_session.get(Article, acme.article_id)
    follow_company(db_session, user_id, acme_article.target_company_id)
    other_signal = make_signal(db_session, company_name="Globex")
    other_article = db_session.get(Article, other_signal.article_id)
    follow_company(db_session, user_id, other_article.target_company_id)

    resp = client.get(f"/signals?company_id={other_article.target_company_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["target_company_name"] == "Globex"

    resp_status = client.get("/signals?status=archived", headers=headers)
    assert resp_status.json() == []


def test_get_signal_detail_and_404(client, db_session):
    headers, user_id = signup(client)
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.status_code == 200

    missing_resp = client.get(
        "/signals/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert missing_resp.status_code == 404


def test_get_signal_detail_404_when_not_following(client, db_session):
    headers, _user_id = signup(client)
    signal = make_signal(db_session)

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.status_code == 404


def test_update_signal_status(client, db_session):
    headers, user_id = signup(client)
    signal = make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

    resp = client.patch(
        f"/signals/{signal.id}", json={"status": "archived"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    db_session.refresh(signal)
    assert signal.status == SignalStatus.ARCHIVED


def test_admin_scope_all_sees_unfollowed_signals(client, db_session):
    admin_headers, _admin_id = signup(client, email="admin@proair.com")
    make_signal(db_session)

    resp = client.get("/signals?scope=all", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_scope_all_is_admin_only(client, db_session):
    admin_headers, _admin_id = signup(client, email="admin@proair.com")
    user_headers, _user_id = signup(client, email="rep2@proair.com")
    make_signal(db_session)

    resp = client.get("/signals?scope=all", headers=user_headers)
    assert resp.status_code == 403
