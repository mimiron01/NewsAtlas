from app.models.article import Article
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.services.ai_client import MistralUsage, ThemeArticleResult, TriageResult
from app.services.ingestion import run_ingestion
from app.services.news_client import NewsClientError
from tests.test_ingestion import USAGE, _article
from tests.test_ingestion_multi_source import _enable_sources


class FakeGoogleClient:
    """Theme-aware fake: fetch_articles() is called with query_override + since only
    (no name/keywords) for the theme path, and with name/keywords for the company path
    — this fake supports both call shapes."""

    def __init__(self, articles=None, articles_by_company=None, error=False):
        self.articles = articles or []
        self.articles_by_company = articles_by_company or {}
        self.error = error
        self.calls: list[dict] = []

    def fetch_articles(self, *, name=None, keywords=None, since, sources=None, query_override=None):
        self.calls.append({"name": name, "query_override": query_override, "sources": sources})
        if self.error:
            raise NewsClientError("google news boom")
        if query_override is not None:
            return self.articles
        return self.articles_by_company.get(name, [])


class FakeThemeAIClient:
    model = "mistral-large-latest"
    triage_model = "mistral-small-latest"
    embed_model = "mistral-embed"

    def __init__(
        self,
        extracted_company_by_title: dict[str, str | None] | None = None,
        not_relevant_titles: set[str] | None = None,
        embeddings_by_title: dict[str, list[float]] | None = None,
        fail_summarize_titles: set[str] | None = None,
    ):
        self.extracted_company_by_title = extracted_company_by_title or {}
        self.not_relevant_titles = not_relevant_titles or set()
        self.embeddings_by_title = embeddings_by_title or {}
        self.fail_summarize_titles = fail_summarize_titles or set()
        self.triage_calls: list[str] = []
        self.summarize_calls: list[str] = []

    def embed_texts(self, texts):
        import zlib

        vectors = []
        for text in texts:
            title = text.split("\n", 1)[0]
            if title in self.embeddings_by_title:
                vectors.append(self.embeddings_by_title[title])
                continue
            idx = zlib.crc32(title.encode()) % 64
            vector = [0.0] * 64
            vector[idx] = 1.0
            vectors.append(vector)
        return vectors, USAGE

    def triage_theme_article(self, *, offering_description, theme_name, query_terms,
                              article_title, article_description, industry=None, headline_only=False):
        self.triage_calls.append(article_title)
        relevant = article_title not in self.not_relevant_titles
        return TriageResult(relevant=relevant, reason="test"), USAGE

    def summarize_theme_article(self, *, company_name, offering_description, theme_name, query_terms,
                                 article_title, article_description, industry=None,
                                 output_language="en", headline_only=False):
        self.summarize_calls.append(article_title)
        if article_title in self.fail_summarize_titles:
            from app.services.ai_client import AIClientError

            raise AIClientError("model unavailable")
        return (
            ThemeArticleResult(
                extracted_company_name=self.extracted_company_by_title.get(article_title),
                summary=f"Summary of {article_title}",
                business_relevance="Relevant because reasons",
                relevance_score=4,
                signal_type="funding",
                confidence="high",
                entities={},
            ),
            USAGE,
        )


def _make_theme(db_session, name="Automotive", query_terms=None, is_active=True) -> ThemeWatch:
    theme = ThemeWatch(name=name, query_terms=query_terms or ["EV battery"], is_active=is_active)
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def test_theme_ingestion_creates_matches_with_extracted_company(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Acme Corp raises $10M for EV batteries", "https://example.com/acme-ev")]
    )
    ai = FakeThemeAIClient(
        extracted_company_by_title={"Acme Corp raises $10M for EV batteries": "Acme Corp"}
    )

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1
    assert result.themes_processed == 1
    match = db_session.query(ThemeMatch).one()
    assert match.extracted_company_name == "Acme Corp"
    assert match.summary == "Summary of Acme Corp raises $10M for EV batteries"
    assert match.matched_target_company_id is None  # not an already-tracked company


def test_theme_ingestion_keeps_company_less_matches(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("EV sales up 20% industry-wide", "https://example.com/ev-trend")]
    )
    ai = FakeThemeAIClient(extracted_company_by_title={"EV sales up 20% industry-wide": None})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1
    match = db_session.query(ThemeMatch).one()
    assert match.extracted_company_name is None


def test_theme_ingestion_auto_links_existing_target_company(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    tc = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)

    google = FakeGoogleClient(
        articles=[_article("Acme Corp raises $10M for EV batteries", "https://example.com/acme-ev")]
    )
    ai = FakeThemeAIClient(
        extracted_company_by_title={"Acme Corp raises $10M for EV batteries": "acme corp"}
    )

    run_ingestion(db_session, ai_client=ai, google_news_client=google)

    match = db_session.query(ThemeMatch).one()
    assert match.matched_target_company_id == tc.id


def test_theme_ingestion_skips_triaged_out_article(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Local softball team wins", "https://example.com/softball")]
    )
    ai = FakeThemeAIClient(not_relevant_titles={"Local softball team wins"})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 0
    assert result.triaged_out == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason == "triaged_out"
    assert ai.summarize_calls == []


def test_theme_ingestion_dedupes_semantic_duplicate_within_theme(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    same_vector = [1.0] + [0.0] * 63
    google = FakeGoogleClient(
        articles=[
            _article("Acme Corp raises funding A", "https://example.com/a"),
            _article("Acme Corp raises funding B", "https://example.com/b"),
        ]
    )
    ai = FakeThemeAIClient(
        embeddings_by_title={
            "Acme Corp raises funding A": same_vector,
            "Acme Corp raises funding B": same_vector,
        }
    )

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1
    assert result.duplicates_skipped == 1


def test_theme_ingestion_cross_path_dedup_skips_url_already_an_article(db_session):
    theme = _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    tc = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    db_session.add(
        Article(
            target_company_id=tc.id,
            source_name="Reuters",
            title="Already covered",
            url="https://example.com/shared-url",
            description="desc",
        )
    )
    db_session.commit()

    google = FakeGoogleClient(articles=[_article("Already covered", "https://example.com/shared-url")])
    ai = FakeThemeAIClient()

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 0
    assert db_session.query(ThemeMatch).count() == 0


def test_theme_ingestion_respects_max_articles_per_theme_per_run_cap(db_session):
    _make_theme(db_session, name="Automotive")
    settings = _enable_sources(db_session, google_news_rss_enabled=True)
    settings.max_articles_per_theme_per_run = 1
    db_session.commit()

    google = FakeGoogleClient(
        articles=[
            _article("Story one", "https://example.com/one"),
            _article("Story two", "https://example.com/two"),
        ]
    )
    ai = FakeThemeAIClient()

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1
    assert db_session.query(ThemeMatch).count() == 1


def test_theme_ingestion_not_run_when_google_news_rss_disabled(db_session):
    _make_theme(db_session, name="Automotive")
    # google_news_rss_enabled defaults to False, and no google_news_client is injected.
    result = run_ingestion(db_session, ai_client=FakeThemeAIClient())

    assert result.themes_processed == 0
    assert result.theme_matches_created == 0


def test_theme_ingestion_skips_inactive_themes(db_session):
    _make_theme(db_session, name="Paused theme", is_active=False)
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("Some story", "https://example.com/x")])

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert result.themes_processed == 0
    assert google.calls == []


def test_theme_ingestion_continues_after_ai_failure(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("Will fail", "https://example.com/fail")])
    ai = FakeThemeAIClient(fail_summarize_titles={"Will fail"})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 0
    assert len(result.errors) == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason == "ai_error"


def test_theme_ingestion_continues_after_fetch_error(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(error=True)

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert result.theme_matches_created == 0
    assert len(result.errors) == 1
    assert result.themes_processed == 1


def test_theme_ingestion_uses_theme_query_terms_and_source_allowlist(db_session):
    theme = _make_theme(db_session, name="Automotive", query_terms=["EV battery", "Series B"])
    theme.google_news_source_allowlist = ["techcrunch.com"]
    db_session.commit()
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[])

    run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert len(google.calls) == 1
    query = google.calls[0]["query_override"]
    assert "EV battery" in query
    assert "Series B" in query
    # Sources are baked into the query string itself (site:...), not passed as a
    # separate fetch_articles() kwarg for the theme path — see _ingest_theme_watch.
    assert "site:techcrunch.com" in query
