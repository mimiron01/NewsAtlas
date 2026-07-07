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


def test_create_and_list_todos_requires_auth(client, db_session):
    signal = _make_signal(db_session)
    resp = client.get(f"/signals/{signal.id}/todos")
    assert resp.status_code == 401


def test_create_list_and_complete_todo(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp = client.post(f"/signals/{signal.id}/todos", json={"text": "Call back Monday"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["text"] == "Call back Monday"
    assert body["is_done"] is False
    assert body["completed_at"] is None
    todo_id = body["id"]

    resp = client.get(f"/signals/{signal.id}/todos", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.json()["open_todo_count"] == 1

    resp = client.patch(f"/todos/{todo_id}", json={"is_done": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_done"] is True
    assert resp.json()["completed_at"] is not None

    resp = client.get(f"/signals/{signal.id}", headers=headers)
    assert resp.json()["open_todo_count"] == 0

    resp = client.patch(f"/todos/{todo_id}", json={"is_done": False}, headers=headers)
    assert resp.json()["is_done"] is False
    assert resp.json()["completed_at"] is None


def test_todo_text_cannot_be_blank(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp = client.post(f"/signals/{signal.id}/todos", json={"text": "   "}, headers=headers)
    assert resp.status_code == 422


def test_cannot_add_todo_to_inaccessible_signal(client, db_session):
    headers, _user_id = _signup(client)
    signal = _make_signal(db_session)

    resp = client.post(f"/signals/{signal.id}/todos", json={"text": "hi"}, headers=headers)
    assert resp.status_code == 404


def test_todos_are_private_per_user(client, db_session):
    headers_a, user_a = _signup(client, email="a@proair.com")
    headers_b, user_b = _signup(client, email="b@proair.com")
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_a, article.target_company_id)
    _follow(db_session, user_b, article.target_company_id)

    resp = client.post(f"/signals/{signal.id}/todos", json={"text": "A's task"}, headers=headers_a)
    todo_id = resp.json()["id"]

    resp_b_list = client.get(f"/signals/{signal.id}/todos", headers=headers_b)
    assert resp_b_list.json() == []

    resp_b_patch = client.patch(f"/todos/{todo_id}", json={"is_done": True}, headers=headers_b)
    assert resp_b_patch.status_code == 404

    resp_b_delete = client.delete(f"/todos/{todo_id}", headers=headers_b)
    assert resp_b_delete.status_code == 404


def test_delete_todo(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp = client.post(f"/signals/{signal.id}/todos", json={"text": "delete me"}, headers=headers)
    todo_id = resp.json()["id"]

    resp = client.delete(f"/todos/{todo_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.get(f"/signals/{signal.id}/todos", headers=headers)
    assert resp.json() == []


def test_my_todos_endpoint_filters_open(client, db_session):
    headers, user_id = _signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    _follow(db_session, user_id, article.target_company_id)

    resp1 = client.post(f"/signals/{signal.id}/todos", json={"text": "open task"}, headers=headers)
    resp2 = client.post(f"/signals/{signal.id}/todos", json={"text": "done task"}, headers=headers)
    client.patch(f"/todos/{resp2.json()['id']}", json={"is_done": True}, headers=headers)

    resp = client.get("/todos?open=true", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == resp1.json()["id"]
    assert body[0]["article_title"] == "Acme raises $10M"
    assert body[0]["target_company_name"] == "Acme Corp"

    resp_all = client.get("/todos", headers=headers)
    assert len(resp_all.json()) == 2
