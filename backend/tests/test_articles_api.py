from datetime import datetime, timezone

from app.models.article import Article
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.services.ingestion import ArticleNotEligibleError


def _signup(client, email="admin@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_skipped_article(db_session, *, skip_reason="triaged_out", triage_reason="not a buying trigger") -> Article:
    target_company = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title="Acme's softball team wins local league",
        url="https://example.com/acme-softball",
        description="desc",
        published_at=datetime.now(timezone.utc),
        skip_reason=skip_reason,
        triage_reason=triage_reason,
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    return article


def test_list_skipped_articles_requires_admin(client, db_session):
    _make_skipped_article(db_session)
    _signup(client, email="admin@proair.com")
    # second signup is not the first user in this workspace, so not an admin
    non_admin_headers = _signup(client, email="rep@proair.com")

    resp = client.get("/articles/skipped", headers=non_admin_headers)
    assert resp.status_code == 403


def test_list_skipped_articles_returns_triage_reason(client, db_session):
    admin_headers = _signup(client, email="admin@proair.com")
    _make_skipped_article(db_session)

    resp = client.get("/articles/skipped", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Acme's softball team wins local league"
    assert body[0]["skip_reason"] == "triaged_out"
    assert body[0]["triage_reason"] == "not a buying trigger"
    assert body[0]["target_company_name"] == "Acme Corp"


def test_list_skipped_articles_filters_by_reason(client, db_session):
    admin_headers = _signup(client, email="admin@proair.com")
    _make_skipped_article(db_session, skip_reason="duplicate", triage_reason=None)

    resp = client.get("/articles/skipped", headers=admin_headers)
    assert resp.json() == []

    resp = client.get("/articles/skipped?reason=duplicate", headers=admin_headers)
    assert len(resp.json()) == 1


def test_create_signal_from_skipped_article_promotes(client, db_session, monkeypatch):
    admin_headers = _signup(client, email="admin@proair.com")
    article = _make_skipped_article(db_session)

    def fake_promote(db, promoted_article):
        signal = Signal(
            article_id=promoted_article.id,
            summary="Promoted summary",
            business_relevance="Promoted relevance",
            outreach_snippet_email="Promoted outreach",
        )
        db.add(signal)
        promoted_article.skip_reason = None
        db.commit()
        db.refresh(signal)
        return signal

    monkeypatch.setattr("app.api.articles.promote_skipped_article", fake_promote)

    resp = client.post(f"/articles/{article.id}/create-signal", headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"] == "Promoted summary"
    assert body["target_company_name"] == "Acme Corp"

    db_session.refresh(article)
    assert article.skip_reason is None


def test_create_signal_from_skipped_article_rejects_ineligible(client, db_session, monkeypatch):
    admin_headers = _signup(client, email="admin@proair.com")
    article = _make_skipped_article(db_session, skip_reason="duplicate", triage_reason=None)

    def fake_promote(db, promoted_article):
        raise ArticleNotEligibleError("Article is not in the triaged-out state")

    monkeypatch.setattr("app.api.articles.promote_skipped_article", fake_promote)

    resp = client.post(f"/articles/{article.id}/create-signal", headers=admin_headers)
    assert resp.status_code == 409


def test_create_signal_from_skipped_article_404_for_unknown_article(client, db_session):
    admin_headers = _signup(client, email="admin@proair.com")
    resp = client.post(
        "/articles/00000000-0000-0000-0000-000000000000/create-signal", headers=admin_headers
    )
    assert resp.status_code == 404
