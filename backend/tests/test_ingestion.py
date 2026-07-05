import zlib
from datetime import datetime, timezone

from app.models.article import Article
from app.models.ai_usage_log import AIUsageLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.services.ai_client import AISummaryResult, MistralUsage, TriageResult
from app.services.ingestion import run_ingestion
from app.services.news_client import NewsArticle

USAGE = MistralUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)


def _default_vector(title: str) -> list[float]:
    """Deterministic, title-derived one-hot vector so unrelated fake articles don't
    accidentally collide as semantic duplicates (only explicit overrides should)."""
    idx = zlib.crc32(title.encode()) % 64
    vector = [0.0] * 64
    vector[idx] = 1.0
    return vector


class FakeNewsClient:
    def __init__(self, articles_by_company: dict[str, list[NewsArticle]]):
        self.articles_by_company = articles_by_company
        self.calls: list[str] = []

    def fetch_articles(self, *, name, keywords, since):
        self.calls.append(name)
        return self.articles_by_company.get(name, [])


class FakeAIClient:
    model = "mistral-large-latest"
    triage_model = "mistral-small-latest"
    embed_model = "mistral-embed"

    def __init__(
        self,
        fail_for_urls: set[str] | None = None,
        embeddings_by_title: dict[str, list[float]] | None = None,
        not_relevant_titles: set[str] | None = None,
    ):
        self.fail_for_urls = fail_for_urls or set()
        self.embeddings_by_title = embeddings_by_title or {}
        self.not_relevant_titles = not_relevant_titles or set()
        self.summarize_calls: list[str] = []
        self.triage_calls: list[str] = []
        self.embed_calls: list[list[str]] = []

    def embed_texts(self, texts):
        self.embed_calls.append(texts)
        vectors = []
        for text in texts:
            title = text.split("\n", 1)[0]
            vectors.append(self.embeddings_by_title.get(title, _default_vector(title)))
        return vectors, USAGE

    def triage_article(self, *, company_name, offering_description, target_company_name,
                        article_title, article_description):
        self.triage_calls.append(article_title)
        relevant = article_title not in self.not_relevant_titles
        return TriageResult(relevant=relevant, reason="test"), USAGE

    def summarize_article(self, *, company_name, offering_description, target_company_name,
                           article_title, article_description, industry=None,
                           recent_signals=None, feedback_note=None):
        self.summarize_calls.append(article_title)
        self.last_recent_signals = recent_signals
        self.last_industry = industry
        self.last_feedback_note = feedback_note
        return (
            AISummaryResult(
                summary=f"Summary of {article_title}",
                business_relevance="Relevant because reasons",
                outreach_snippet_email="Hi, saw your news...",
                outreach_snippet_linkedin="Saw your news...",
                outreach_call_opener="Hey, saw your news...",
                relevance_score=4,
                signal_type="funding",
                confidence="high",
                entities={},
            ),
            USAGE,
        )


class FailingAIClient:
    model = "mistral-large-latest"
    triage_model = "mistral-small-latest"
    embed_model = "mistral-embed"

    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts], USAGE

    def triage_article(self, **kwargs):
        return TriageResult(relevant=True, reason="test"), USAGE

    def summarize_article(self, **kwargs):
        from app.services.ai_client import AIClientError

        raise AIClientError("model unavailable")


def _make_target_company(db_session, name="Acme Corp", is_active=True, industry=None) -> TargetCompany:
    tc = TargetCompany(name=name, keywords=["Acme"], is_active=is_active, industry=industry)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    return tc


def _article(title, url, description="desc"):
    return NewsArticle(
        source_name="Reuters",
        title=title,
        url=url,
        description=description,
        published_at=datetime.now(timezone.utc),
    )


def test_ingestion_creates_articles_and_signals(db_session):
    tc = _make_target_company(db_session)
    news = FakeNewsClient(
        {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]}
    )
    ai = FakeAIClient()

    result = run_ingestion(db_session, news_client=news, ai_client=ai)

    assert result.target_companies_processed == 1
    assert result.articles_fetched == 1
    assert result.articles_new == 1
    assert result.signals_created == 1
    assert result.duplicates_skipped == 0
    assert result.triaged_out == 0
    assert result.errors == []

    articles = db_session.query(Article).all()
    signals = db_session.query(Signal).all()
    assert len(articles) == 1
    assert len(signals) == 1
    assert signals[0].article_id == articles[0].id
    assert articles[0].target_company_id == tc.id
    assert signals[0].relevance_score == 4
    assert signals[0].signal_type == "funding"
    assert signals[0].prompt_tokens == 100
    assert signals[0].total_tokens == 150


def test_ingestion_dedupes_existing_articles_by_url(db_session):
    _make_target_company(db_session)
    article_payload = {
        "Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]
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


def test_ingestion_skips_semantic_duplicate_without_summarizing(db_session):
    _make_target_company(db_session)
    same_vector = [1.0, 0.0, 0.0]
    ai = FakeAIClient(
        embeddings_by_title={
            "Acme raises $10M": same_vector,
            "Acme raises ten million dollars": same_vector,
        }
    )
    news = FakeNewsClient(
        {
            "Acme Corp": [
                _article("Acme raises $10M", "https://example.com/acme-funding-a"),
                _article("Acme raises ten million dollars", "https://example.com/acme-funding-b"),
            ]
        }
    )

    result = run_ingestion(db_session, news_client=news, ai_client=ai)

    assert result.articles_new == 2
    assert result.signals_created == 1
    assert result.duplicates_skipped == 1
    # The duplicate never reached the (expensive) summarization call.
    assert ai.summarize_calls == ["Acme raises $10M"]

    duplicate_article = (
        db_session.query(Article).filter(Article.url == "https://example.com/acme-funding-b").first()
    )
    assert duplicate_article.skip_reason == "duplicate"
    assert duplicate_article.duplicate_of_article_id is not None


def test_ingestion_dedupes_same_url_within_single_fetch_response(db_session):
    """A single NewsAPI response containing the same URL twice must not crash the
    batched insert (Article.url is unique) — regression test for the batching refactor
    that moved from a per-article commit to a single commit per fetch batch."""
    _make_target_company(db_session)
    news = FakeNewsClient(
        {
            "Acme Corp": [
                _article("Acme raises $10M", "https://example.com/acme-funding"),
                _article("Acme raises $10M", "https://example.com/acme-funding"),
            ]
        }
    )

    result = run_ingestion(db_session, news_client=news, ai_client=FakeAIClient())

    assert result.articles_fetched == 2
    assert result.articles_new == 1
    assert result.signals_created == 1
    assert db_session.query(Article).count() == 1


def test_ingestion_does_not_dedupe_against_a_failed_article(db_session):
    """An article that failed summarization (ai_error) must not become a dedupe anchor —
    otherwise a later near-duplicate of the same story would be silently marked
    'duplicate' and dropped even after the transient failure clears."""
    _make_target_company(db_session)
    same_vector = [1.0, 0.0, 0.0]

    run_ingestion(
        db_session,
        news_client=FakeNewsClient(
            {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding-a")]}
        ),
        ai_client=FailingAIClient(),
    )
    failed_article = db_session.query(Article).filter(Article.url == "https://example.com/acme-funding-a").first()
    assert failed_article.skip_reason == "ai_error"
    assert failed_article.embedding is not None

    ai = FakeAIClient(
        embeddings_by_title={"Acme raises ten million dollars": same_vector}
    )
    result = run_ingestion(
        db_session,
        news_client=FakeNewsClient(
            {
                "Acme Corp": [
                    _article(
                        "Acme raises ten million dollars", "https://example.com/acme-funding-b"
                    )
                ]
            }
        ),
        ai_client=ai,
    )

    assert result.duplicates_skipped == 0
    assert result.signals_created == 1
    assert ai.summarize_calls == ["Acme raises ten million dollars"]


def test_ingestion_skips_triaged_out_article_without_summarizing(db_session):
    _make_target_company(db_session)
    ai = FakeAIClient(not_relevant_titles={"Acme's softball team wins local league"})
    news = FakeNewsClient(
        {
            "Acme Corp": [
                _article(
                    "Acme's softball team wins local league",
                    "https://example.com/acme-softball",
                )
            ]
        }
    )

    result = run_ingestion(db_session, news_client=news, ai_client=ai)

    assert result.articles_new == 1
    assert result.signals_created == 0
    assert result.triaged_out == 1
    assert ai.summarize_calls == []

    article = db_session.query(Article).first()
    assert article.skip_reason == "triaged_out"


def test_ingestion_passes_industry_and_recent_signal_context(db_session):
    _make_target_company(db_session, industry="Manufacturing")
    ai = FakeAIClient()
    news = FakeNewsClient(
        {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]}
    )

    run_ingestion(db_session, news_client=news, ai_client=ai)
    assert ai.last_industry == "Manufacturing"
    assert ai.last_recent_signals == []

    news_2 = FakeNewsClient(
        {"Acme Corp": [_article("Acme hires new CFO", "https://example.com/acme-cfo")]}
    )
    run_ingestion(db_session, news_client=news_2, ai_client=ai)
    assert ai.last_recent_signals == ["Summary of Acme raises $10M"]


def test_ingestion_logs_token_usage(db_session):
    _make_target_company(db_session)
    ai = FakeAIClient()
    news = FakeNewsClient(
        {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]}
    )

    run_ingestion(db_session, news_client=news, ai_client=ai)

    logs = db_session.query(AIUsageLog).all()
    call_types = {log.call_type for log in logs}
    assert call_types == {"embedding", "triage", "summarize"}
    assert all(log.total_tokens == 150 for log in logs)


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
            return [_article("Working Co news", "https://example.com/working-co")]

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
        {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]}
    )

    result = run_ingestion(db_session, news_client=news, ai_client=FailingAIClient())

    assert result.articles_new == 1
    assert result.signals_created == 0
    assert len(result.errors) == 1
    assert db_session.query(Article).count() == 1
    assert db_session.query(Signal).count() == 0

    article = db_session.query(Article).first()
    assert article.skip_reason == "ai_error"
