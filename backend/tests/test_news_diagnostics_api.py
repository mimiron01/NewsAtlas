from datetime import datetime, timedelta, timezone

from app.models.article import Article, ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.signal import Signal, SignalStatus
from app.models.target_company import TargetCompany
from app.services import google_news_rss_client
from app.services.news_client import FetchOutcome, NewsArticle

from tests.conftest import admin_headers, user_headers


def _outcome(articles=None, query="Acme when:1d"):
    return FetchOutcome(
        articles=articles or [],
        requests_used=1,
        query_text=query,
        articles_raw=len(articles or []),
        drop_counts={"stale": 3},
    )


def _stub_fetch(monkeypatch, outcome=None, error=None):
    def fake_fetch(self, **kwargs):
        if error:
            raise error
        return outcome if outcome is not None else _outcome()

    monkeypatch.setattr(
        google_news_rss_client.GoogleNewsRSSClient, "fetch_articles", fake_fetch
    )


def test_preview_requires_admin(client, monkeypatch):
    _stub_fetch(monkeypatch)
    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme"},
        headers=user_headers(client),
    )
    assert resp.status_code == 403


def test_preview_returns_the_query_and_per_entry_outcomes(client, monkeypatch):
    _stub_fetch(
        monkeypatch,
        _outcome(
            [
                NewsArticle(
                    source_name="Reuters",
                    title="Acme Corp raises $10M",
                    url="https://reuters.com/a",
                    description="desc",
                    published_at=datetime.now(timezone.utc),
                ),
                NewsArticle(
                    source_name="Other",
                    title="Unrelated story",
                    url="https://other.example/b",
                    description="desc",
                    published_at=datetime.now(timezone.utc),
                ),
            ]
        ),
    )

    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme Corp", "context_terms": ["Motorsport"]},
        headers=admin_headers(client),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert '"Acme Corp"' in body["query_text"]
    assert "Motorsport" in body["query_text"]
    assert body["drop_counts"]["stale"] == 3
    # Grounding is reported per entry rather than applied — seeing what *would* be dropped
    # is the point of a preview.
    assert [entry["outcome"] for entry in body["entries"]] == ["kept", "not_grounded"]


def test_preview_writes_no_articles_and_makes_no_ai_call(client, db_session, monkeypatch):
    _stub_fetch(
        monkeypatch,
        _outcome(
            [
                NewsArticle(
                    source_name="Reuters",
                    title="Acme Corp raises $10M",
                    url="https://reuters.com/a",
                    description="desc",
                    published_at=datetime.now(timezone.utc),
                )
            ]
        ),
    )

    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme Corp"},
        headers=admin_headers(client),
    )

    assert resp.status_code == 200
    assert db_session.query(Article).count() == 0


def test_preview_counts_against_the_rate_limiter(client, db_session, monkeypatch):
    """It triggers a real outbound request, so it must not be a way around the ceiling."""
    _stub_fetch(monkeypatch)

    client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme"},
        headers=admin_headers(client),
    )

    log = db_session.query(NewsSourceUsageLog).one()
    assert log.call_type == "preview"
    assert log.source == ArticleSource.GOOGLE_NEWS_RSS
    assert log.requests_used == 1


def test_preview_reports_a_theme_shaped_query(client, monkeypatch):
    _stub_fetch(monkeypatch)

    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"query_terms": ["EV battery", "Series B"], "exclude_terms": ["Formel 1"]},
        headers=admin_headers(client),
    )

    body = resp.json()
    assert '"EV battery"' in body["query_text"]
    assert '-"Formel 1"' in body["query_text"]
    # No identity to ground against, so nothing is reported as not_grounded.
    assert all(e["outcome"] == "kept" for e in body["entries"])


def test_preview_surfaces_a_throttled_upstream_as_a_gateway_error(client, monkeypatch):
    from app.services.news_client import NewsClientError

    _stub_fetch(monkeypatch, error=NewsClientError("Google News RSS returned HTTP 429"))

    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme"},
        headers=admin_headers(client),
    )

    assert resp.status_code == 502
    assert "429" in resp.json()["detail"]


def test_preview_reports_truncation(client, monkeypatch):
    _stub_fetch(monkeypatch)

    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme", "context_terms": [f"term{i}" for i in range(20)]},
        headers=admin_headers(client),
    )

    body = resp.json()
    assert body["truncated"] is True
    assert body["word_count"] <= body["max_words"]


def test_preview_rejects_an_invalid_domain(client):
    resp = client.post(
        "/news-diagnostics/google-news/preview",
        json={"name": "Acme", "source_denylist": ["https://msn.com/path"]},
        headers=admin_headers(client),
    )
    assert resp.status_code == 422


def test_source_precision_requires_admin(client):
    resp = client.get("/news-diagnostics/source-precision", headers=user_headers(client))
    assert resp.status_code == 403


def test_source_precision_flags_a_wasteful_publisher(client, db_session):
    company = TargetCompany(name="Acme Corp", keywords=[], aliases=[], context_terms=[])
    db_session.add(company)
    db_session.commit()

    now = datetime.now(timezone.utc)
    for i in range(6):
        db_session.add(
            Article(
                target_company_id=company.id,
                source=ArticleSource.GOOGLE_NEWS_RSS,
                source_name="Spam Aggregator",
                title=f"junk {i}",
                url=f"https://spam.example/{i}",
                fetched_at=now - timedelta(days=1),
                skip_reason="triaged_out",
            )
        )
    good = Article(
        target_company_id=company.id,
        source=ArticleSource.GOOGLE_NEWS_RSS,
        source_name="Reuters",
        title="real story",
        url="https://reuters.com/1",
        fetched_at=now - timedelta(days=1),
    )
    db_session.add(good)
    db_session.commit()
    db_session.add(Signal(
            article_id=good.id,
            summary="s",
            business_relevance="r",
            outreach_snippet_email="e",
            status=SignalStatus.NEW,
        ))
    db_session.commit()

    resp = client.get("/news-diagnostics/source-precision", headers=admin_headers(client))

    assert resp.status_code == 200
    by_source = {row["source_name"]: row for row in resp.json()}
    assert by_source["Spam Aggregator"]["denylist_suggested"] is True
    assert by_source["Reuters"]["denylist_suggested"] is False
    assert by_source["Reuters"]["signals_kept"] == 1
