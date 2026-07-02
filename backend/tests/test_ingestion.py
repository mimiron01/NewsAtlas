from datetime import datetime, timezone

from app.models.article import Article
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.services.ai_client import AISummaryResult
from app.services.ingestion import run_ingestion
from app.services.news_client import NewsArticle


class FakeNewsClient:
    def __init__(self, articles_by_company: dict[str, list[NewsArticle]]):
        self.articles_by_company = articles_by_company
        self.calls: list[str] = []

    def fetch_articles(self, *, name, keywords, since):
        self.calls.append(name)
        return self.articles_by_company.get(name, [])


class FakeAIClient:
    def __init__(self, fail_for_urls: set[str] | None = None):
        self.fail_for_urls = fail_for_urls or set()
        self.calls: list[str] = []

    def summarize_article(self, *, company_name, offering_description, target_company_name,
                           article_title, article_description):
        self.calls.append(article_title)
        return AISummaryResult(
            summary=f"Summary of {article_title}",
            business_relevance="Relevant because reasons",
            outreach_snippet="Hi, saw your news...",
        )


def _make_target_company(db_session, name="Acme Corp", is_active=True) -> TargetCompany:
    tc = TargetCompany(name=name, keywords=["Acme"], is_active=is_active)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    return tc


def test_ingestion_creates_articles_and_signals(db_session):
    tc = _make_target_company(db_session)
    news = FakeNewsClient(
        {
            "Acme Corp": [
                NewsArticle(
                    source_name="Reuters",
                    title="Acme raises $10M",
                    url="https://example.com/acme-funding",
                    description="Acme raised a Series A",
                    published_at=datetime.now(timezone.utc),
                )
            ]
        }
    )
    ai = FakeAIClient()

    result = run_ingestion(db_session, news_client=news, ai_client=ai)

    assert result.target_companies_processed == 1
    assert result.articles_fetched == 1
    assert result.articles_new == 1
    assert result.signals_created == 1
    assert result.errors == []

    articles = db_session.query(Article).all()
    signals = db_session.query(Signal).all()
    assert len(articles) == 1
    assert len(signals) == 1
    assert signals[0].article_id == articles[0].id
    assert articles[0].target_company_id == tc.id


def test_ingestion_dedupes_existing_articles_by_url(db_session):
    _make_target_company(db_session)
    article_payload = {
        "Acme Corp": [
            NewsArticle(
                source_name="Reuters",
                title="Acme raises $10M",
                url="https://example.com/acme-funding",
                description="Acme raised a Series A",
                published_at=datetime.now(timezone.utc),
            )
        ]
    }

    run_ingestion(db_session, news_client=FakeNewsClient(article_payload), ai_client=FakeAIClient())
    second_result = run_ingestion(
        db_session, news_client=FakeNewsClient(article_payload), ai_client=FakeAIClient()
    )

    assert second_result.articles_fetched == 1
    assert second_result.articles_new == 0
    assert second_result.signals_created == 0
    assert db_session.query(Article).count() == 1
    assert db_session.query(Signal).count() == 1


def test_ingestion_skips_inactive_target_companies(db_session):
    _make_target_company(db_session, name="Inactive Co", is_active=False)
    news = FakeNewsClient({})

    result = run_ingestion(db_session, news_client=news, ai_client=FakeAIClient())

    assert result.target_companies_processed == 0
    assert news.calls == []


def test_ingestion_continues_after_news_fetch_error(db_session):
    _make_target_company(db_session, name="Broken Co")
    _make_target_company(db_session, name="Working Co")

    class FailingThenWorkingNewsClient:
        def fetch_articles(self, *, name, keywords, since):
            if name == "Broken Co":
                from app.services.news_client import NewsClientError

                raise NewsClientError("boom")
            return [
                NewsArticle(
                    source_name="Reuters",
                    title="Working Co news",
                    url="https://example.com/working-co",
                    description="desc",
                    published_at=datetime.now(timezone.utc),
                )
            ]

    result = run_ingestion(
        db_session, news_client=FailingThenWorkingNewsClient(), ai_client=FakeAIClient()
    )

    assert result.target_companies_processed == 2
    assert result.articles_new == 1
    assert len(result.errors) == 1
    assert "Broken Co" in result.errors[0]


def test_ingestion_continues_after_ai_failure(db_session):
    _make_target_company(db_session)
    news = FakeNewsClient(
        {
            "Acme Corp": [
                NewsArticle(
                    source_name="Reuters",
                    title="Acme raises $10M",
                    url="https://example.com/acme-funding",
                    description="desc",
                    published_at=datetime.now(timezone.utc),
                )
            ]
        }
    )

    class FailingAIClient:
        def summarize_article(self, **kwargs):
            from app.services.ai_client import AIClientError

            raise AIClientError("model unavailable")

    result = run_ingestion(db_session, news_client=news, ai_client=FailingAIClient())

    assert result.articles_new == 1
    assert result.signals_created == 0
    assert len(result.errors) == 1
    assert db_session.query(Article).count() == 1
    assert db_session.query(Signal).count() == 0
