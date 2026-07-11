from datetime import datetime, timezone

from app.models.article import Article, ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.target_company import TargetCompany
from app.models.workspace_settings import WorkspaceSettings
from app.services.ingestion import run_ingestion
from app.services.news_client import NewsArticle, NewsClientError
from app.services.workspace_settings import get_or_create_workspace_settings
from tests.test_ingestion import USAGE, FakeAIClient, FakeNewsClient, _article, _make_target_company
from tests.test_ingestion_progress import _RecordingProgress


class FakeGoogleClient:
    def __init__(self, articles_by_company: dict[str, list[NewsArticle]], error_for: set[str] | None = None):
        self.articles_by_company = articles_by_company
        self.error_for = error_for or set()
        self.calls: list[str] = []

    def fetch_articles(self, *, name, keywords, since):
        self.calls.append(name)
        if name in self.error_for:
            raise NewsClientError("google news boom")
        return self.articles_by_company.get(name, [])


class FakeNewsDataClient:
    def __init__(self, articles_by_company: dict[str, list], requests_used: int = 1):
        self.articles_by_company = articles_by_company
        self.requests_used = requests_used
        self.calls: list[str] = []

    def fetch_articles(self, *, name, keywords, since, full_content, use_native_dedupe):
        self.calls.append(name)
        return self.articles_by_company.get(name, []), self.requests_used


def _enable_sources(db_session, **flags) -> WorkspaceSettings:
    settings = get_or_create_workspace_settings(db_session)
    for key, value in flags.items():
        setattr(settings, key, value)
    db_session.commit()
    return settings


def test_ingestion_merges_articles_from_multiple_enabled_sources(db_session):
    _make_target_company(db_session)
    _enable_sources(db_session, google_news_rss_enabled=True, newsdata_enabled=True)

    news = FakeNewsClient({"Acme Corp": [_article("Acme NewsAPI story", "https://example.com/newsapi")]})
    google = FakeGoogleClient({"Acme Corp": [_article("Acme Google story", "https://example.com/google")]})
    newsdata = FakeNewsDataClient({"Acme Corp": [_article("Acme NewsData story", "https://example.com/newsdata")]})

    result = run_ingestion(
        db_session,
        news_client=news,
        ai_client=FakeAIClient(),
        google_news_client=google,
        newsdata_client=newsdata,
    )

    assert result.articles_new == 3
    assert result.by_source == {"newsapi": 1, "google_news_rss": 1, "newsdata": 1}

    sources = {a.source for a in db_session.query(Article).all()}
    assert sources == {ArticleSource.NEWSAPI, ArticleSource.GOOGLE_NEWS_RSS, ArticleSource.NEWSDATA}


def test_ingestion_cross_source_dedupe_collapses_same_url(db_session):
    _make_target_company(db_session)
    _enable_sources(db_session, google_news_rss_enabled=True)

    shared_url = "https://example.com/shared-story"
    news = FakeNewsClient({"Acme Corp": [_article("Acme Same story", shared_url)]})
    google = FakeGoogleClient({"Acme Corp": [_article("Acme Same story", shared_url)]})

    result = run_ingestion(
        db_session, news_client=news, ai_client=FakeAIClient(), google_news_client=google
    )

    assert result.articles_fetched == 2
    assert result.articles_new == 1
    assert db_session.query(Article).count() == 1


def test_ingestion_isolates_one_source_failure_from_others(db_session):
    _make_target_company(db_session)
    _enable_sources(db_session, google_news_rss_enabled=True, newsdata_enabled=True)

    news = FakeNewsClient({"Acme Corp": [_article("Acme NewsAPI story", "https://example.com/newsapi")]})
    google = FakeGoogleClient({}, error_for={"Acme Corp"})
    newsdata = FakeNewsDataClient({"Acme Corp": [_article("Acme NewsData story", "https://example.com/newsdata")]})

    result = run_ingestion(
        db_session,
        news_client=news,
        ai_client=FakeAIClient(),
        google_news_client=google,
        newsdata_client=newsdata,
    )

    assert result.articles_new == 2
    assert len(result.errors) == 1
    assert "google_news_rss" in result.errors[0]


def test_ingestion_skips_source_once_its_rate_limit_is_reached(db_session):
    tc = _make_target_company(db_session)
    _enable_sources(
        db_session,
        newsdata_enabled=True,
        newsdata_max_requests_per_day=2,
        newsdata_max_requests_per_minute=1_000_000,
    )
    # Pre-fill the daily quota so the upcoming run has no headroom left for newsdata.
    db_session.add(NewsSourceUsageLog(source=ArticleSource.NEWSDATA, requests_used=2, target_company_id=tc.id))
    db_session.commit()

    news = FakeNewsClient({"Acme Corp": [_article("Acme NewsAPI story", "https://example.com/newsapi")]})
    newsdata = FakeNewsDataClient({"Acme Corp": [_article("Acme NewsData story", "https://example.com/newsdata")]})

    result = run_ingestion(
        db_session, news_client=news, ai_client=FakeAIClient(), newsdata_client=newsdata
    )

    assert newsdata.calls == []
    assert result.rate_limited == {"newsdata": 1}
    assert result.articles_new == 1
    assert not db_session.query(Article).filter(Article.source == ArticleSource.NEWSDATA).all()

    rate_limited_logs = (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.call_type == "rate_limited")
        .all()
    )
    assert len(rate_limited_logs) == 1


def test_ingestion_waits_out_a_per_minute_rate_limit_instead_of_skipping_the_company(
    db_session, monkeypatch
):
    """A per-minute ceiling (unlike a per-day one) frees up on its own within 60s, so
    the company should still get its Google News coverage this run instead of being
    permanently dropped from that source (see services/news_rate_limiter.py)."""
    tc = _make_target_company(db_session)
    _enable_sources(
        db_session, google_news_rss_enabled=True, google_news_rss_max_requests_per_minute=1
    )
    db_session.add(
        NewsSourceUsageLog(source=ArticleSource.GOOGLE_NEWS_RSS, requests_used=1, target_company_id=tc.id)
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.services.ingestion.wait_for_minute_headroom", lambda *args, **kwargs: True
    )

    news = FakeNewsClient({})
    google = FakeGoogleClient({"Acme Corp": [_article("Acme Google story", "https://example.com/google")]})

    result = run_ingestion(
        db_session, news_client=news, ai_client=FakeAIClient(), google_news_client=google
    )

    assert google.calls == ["Acme Corp"]
    assert result.rate_limited == {}
    assert result.articles_new == 1


def test_ingestion_still_skips_source_if_the_wait_times_out(db_session, monkeypatch):
    """Falls back to the old skip-and-log behavior on the rare case the wait itself
    gives up (its own safety cap, not a cancellation) — see
    wait_for_minute_headroom's max_wait_seconds."""
    tc = _make_target_company(db_session)
    _enable_sources(
        db_session, google_news_rss_enabled=True, google_news_rss_max_requests_per_minute=1
    )
    db_session.add(
        NewsSourceUsageLog(source=ArticleSource.GOOGLE_NEWS_RSS, requests_used=1, target_company_id=tc.id)
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.services.ingestion.wait_for_minute_headroom", lambda *args, **kwargs: False
    )

    news = FakeNewsClient({})
    google = FakeGoogleClient({"Acme Corp": [_article("Acme Google story", "https://example.com/google")]})

    result = run_ingestion(
        db_session, news_client=news, ai_client=FakeAIClient(), google_news_client=google
    )

    assert google.calls == []
    assert result.rate_limited == {"google_news_rss": 1}


def test_ingestion_stops_cleanly_if_cancelled_while_waiting_for_rate_limit(db_session, monkeypatch):
    tc = _make_target_company(db_session)
    _enable_sources(
        db_session, google_news_rss_enabled=True, google_news_rss_max_requests_per_minute=1
    )
    db_session.add(
        NewsSourceUsageLog(source=ArticleSource.GOOGLE_NEWS_RSS, requests_used=1, target_company_id=tc.id)
    )
    db_session.commit()

    # Simulates should_cancel() firing while wait_for_minute_headroom is blocked —
    # the wait gives up (returns False) and the pipeline notices the cancellation right
    # after, rather than logging a rate-limited skip for a run that's stopping anyway.
    monkeypatch.setattr(
        "app.services.ingestion.wait_for_minute_headroom", lambda *args, **kwargs: False
    )
    progress = _RecordingProgress(cancel_after=1)

    news = FakeNewsClient({})
    google = FakeGoogleClient({"Acme Corp": [_article("Acme Google story", "https://example.com/google")]})

    result = run_ingestion(
        db_session,
        news_client=news,
        ai_client=FakeAIClient(),
        google_news_client=google,
        progress=progress,
    )

    assert google.calls == []
    assert result.cancelled is True
    assert result.rate_limited == {}


def test_ingestion_logs_news_source_usage_per_call(db_session):
    _make_target_company(db_session)
    _enable_sources(db_session, newsdata_enabled=True)
    news = FakeNewsClient({"Acme Corp": [_article("Acme NewsAPI story", "https://example.com/newsapi")]})
    newsdata = FakeNewsDataClient(
        {"Acme Corp": [_article("Acme NewsData story", "https://example.com/newsdata")]}, requests_used=2
    )

    run_ingestion(db_session, news_client=news, ai_client=FakeAIClient(), newsdata_client=newsdata)

    logs = db_session.query(NewsSourceUsageLog).filter(NewsSourceUsageLog.call_type == "latest").all()
    by_source = {log.source: log.requests_used for log in logs}
    assert by_source[ArticleSource.NEWSAPI] == 1
    assert by_source[ArticleSource.NEWSDATA] == 2


def test_ingestion_grounds_summarization_in_full_content_when_present(db_session):
    _make_target_company(db_session)
    _enable_sources(db_session, newsdata_enabled=True)

    long_body = "Full article body. " * 20
    newsdata_article = NewsArticle(
        source_name="Reuters",
        title="Acme raises $10M",
        url="https://example.com/newsdata-full",
        description="short snippet",
        published_at=datetime.now(timezone.utc),
    )
    # NewsDataArticle-shaped duck type: ingestion reads full_content via getattr, so a
    # plain object with the attribute set is enough without importing NewsDataArticle.
    newsdata_article.full_content = long_body  # type: ignore[attr-defined]

    class SingleArticleNewsDataClient:
        def fetch_articles(self, *, name, keywords, since, full_content, use_native_dedupe):
            return [newsdata_article], 1

    ai = FakeAIClient()
    run_ingestion(
        db_session,
        news_client=FakeNewsClient({}),
        ai_client=ai,
        newsdata_client=SingleArticleNewsDataClient(),
    )

    assert ai.summarize_calls == ["Acme raises $10M"]
    assert ai.last_article_description == long_body
    stored = db_session.query(Article).filter(Article.url == "https://example.com/newsdata-full").first()
    assert stored.full_content == long_body
