from app.models.article import Article, ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.services.ai_client import AIClientError
from app.services.news_client import NewsClientError
from app.services.newsdata_backfill import run_backfill_for_company
from app.services.workspace_settings import get_or_create_workspace_settings
from tests.test_ingestion import USAGE, FakeAIClient, _article


class FakeArchiveClient:
    def __init__(self, articles=None, requests_used=1, error=False):
        self.articles = articles or []
        self.requests_used = requests_used
        self.error = error
        self.calls = 0

    def fetch_archive(self, *, name, keywords, since, until, full_content, use_native_dedupe):
        self.calls += 1
        if self.error:
            raise NewsClientError("archive boom")
        return self.articles, self.requests_used


def _make_company(db_session, **overrides) -> TargetCompany:
    tc = TargetCompany(name="Acme Corp", keywords=["Acme"], **overrides)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    return tc


def _enable_backfill(db_session, **overrides):
    settings = get_or_create_workspace_settings(db_session)
    settings.newsdata_enabled = True
    settings.newsdata_backfill_days = 30
    for key, value in overrides.items():
        setattr(settings, key, value)
    db_session.commit()
    return settings


def test_backfill_skipped_when_newsdata_disabled(db_session):
    tc = _make_company(db_session)
    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=FakeArchiveClient())
    assert ran is False


def test_backfill_skipped_when_backfill_days_zero(db_session):
    tc = _make_company(db_session)
    settings = get_or_create_workspace_settings(db_session)
    settings.newsdata_enabled = True
    settings.newsdata_backfill_days = 0
    db_session.commit()

    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=FakeArchiveClient())
    assert ran is False


def test_backfill_skipped_when_already_backfilled(db_session):
    from datetime import datetime, timezone

    tc = _make_company(db_session, backfilled_at=datetime.now(timezone.utc))
    _enable_backfill(db_session)
    client = FakeArchiveClient(articles=[_article("Old news", "https://example.com/a")])

    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=client)
    assert ran is False
    assert client.calls == 0


def test_backfill_skipped_and_logged_when_rate_limited(db_session):
    tc = _make_company(db_session)
    _enable_backfill(db_session, newsdata_max_requests_per_day=1, newsdata_max_requests_per_minute=1_000_000)
    db_session.add(NewsSourceUsageLog(source=ArticleSource.NEWSDATA, requests_used=1, target_company_id=tc.id))
    db_session.commit()

    client = FakeArchiveClient(articles=[_article("Old news", "https://example.com/a")])
    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=client)

    assert ran is False
    assert client.calls == 0
    db_session.refresh(tc)
    assert tc.backfilled_at is None
    assert (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.call_type == "rate_limited")
        .count()
        == 1
    )


def test_backfill_leaves_backfilled_at_unset_on_fetch_error(db_session):
    tc = _make_company(db_session)
    _enable_backfill(db_session)
    client = FakeArchiveClient(error=True)

    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=client)

    assert ran is False
    db_session.refresh(tc)
    assert tc.backfilled_at is None


def test_backfill_fetches_processes_and_marks_backfilled(db_session):
    tc = _make_company(db_session)
    _enable_backfill(db_session)
    client = FakeArchiveClient(
        articles=[_article("Acme old funding round", "https://example.com/old-funding")], requests_used=2
    )
    ai = FakeAIClient()

    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=client, ai_client=ai)

    assert ran is True
    db_session.refresh(tc)
    assert tc.backfilled_at is not None

    article = db_session.query(Article).filter(Article.url == "https://example.com/old-funding").first()
    assert article is not None
    assert article.source == ArticleSource.NEWSDATA

    signal = db_session.query(Signal).filter(Signal.article_id == article.id).first()
    assert signal is not None

    usage_log = (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.call_type == "archive")
        .first()
    )
    assert usage_log is not None
    assert usage_log.requests_used == 2


def test_backfill_dedupes_against_existing_article_url(db_session):
    tc = _make_company(db_session)
    _enable_backfill(db_session)
    existing = Article(
        target_company_id=tc.id,
        source=ArticleSource.NEWSAPI,
        source_name="Reuters",
        title="Acme already ingested",
        url="https://example.com/already-there",
    )
    db_session.add(existing)
    db_session.commit()

    client = FakeArchiveClient(
        articles=[_article("Acme already ingested", "https://example.com/already-there")]
    )
    ran = run_backfill_for_company(db_session, tc.id, newsdata_client=client, ai_client=FakeAIClient())

    assert ran is True
    assert db_session.query(Article).count() == 1
