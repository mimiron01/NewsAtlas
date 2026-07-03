from datetime import datetime, timezone

from app.models.article import Article
from app.models.signal import Signal, SignalStatus
from app.models.target_company import TargetCompany


def _auth_headers(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "rep@proair.com", "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
        outreach_snippet="Congrats on the raise...",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal


def test_list_signals_requires_auth(client):
    resp = client.get("/signals")
    assert resp.status_code == 401


def test_list_signals_returns_joined_data(client, db_session):
    headers = _auth_headers(client)
    signal = _make_signal(db_session)

    resp = client.get("/signals", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(signal.id)
    assert body[0]["target_company_name"] == "Acme Corp"
    assert body[0]["article_title"] == "Acme raises $10M"
    assert body[0]["status"] == "new"


def test_filter_signals_by_company_and_status(client, db_session):
    headers = _auth_headers(client)
    _make_signal(db_session, company_name="Acme Corp")
    other_signal = _make_signal(db_session, company_name="Globex")
    other_article = db_session.get(Article, other_signal.article_id)

    resp = client.get(f"/signals?company_id={other_article.target_company_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["target_company_name"] == "Globex"

    resp_status = client.get("/signals?status=archived", headers=headers)
    assert resp_status.json() == []


def test_get_signal_detail_and_404(client, db_session):
    headers = _auth_headers(client)
    signal = _make_signal(db_session)

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.status_code == 200

    missing_resp = client.get(
        "/signals/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert missing_resp.status_code == 404


def test_update_signal_status(client, db_session):
    headers = _auth_headers(client)
    signal = _make_signal(db_session)

    resp = client.patch(
        f"/signals/{signal.id}", json={"status": "archived"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    db_session.refresh(signal)
    assert signal.status == SignalStatus.ARCHIVED
