from app.models.article import Article, ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.services.ai_client import MistralUsage, ThemeArticleResult, TriageResult
from app.services.ingestion import run_ingestion
from app.services.news_client import FetchOutcome, NewsClientError
from app.services.news_usage import log_usage
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

    def fetch_articles(
        self,
        *,
        name=None,
        keywords=None,
        since,
        sources=None,
        query_override=None,
        country=None,
        language=None,
        when=None,
    ):
        self.calls.append(
            {
                "name": name,
                "query_override": query_override,
                "sources": sources,
                "country": country,
                "language": language,
                "when": when,
            }
        )
        if self.error:
            raise NewsClientError("google news boom")
        # Both paths come through query_override now, so a fetch is identified as a
        # company's by its name appearing in the built query; anything else is the theme
        # query and gets `articles`.
        articles = self.articles
        for company_name, company_articles in self.articles_by_company.items():
            if query_override and company_name in query_override:
                articles = company_articles
                break
        return FetchOutcome(
            articles=articles, requests_used=1, query_text=query_override,
            articles_raw=len(articles),
        )


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
        relevance_score_by_title: dict[str, int] | None = None,
    ):
        self.extracted_company_by_title = extracted_company_by_title or {}
        self.not_relevant_titles = not_relevant_titles or set()
        self.embeddings_by_title = embeddings_by_title or {}
        self.fail_summarize_titles = fail_summarize_titles or set()
        self.relevance_score_by_title = relevance_score_by_title or {}
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
                              article_title, article_description, industry=None,
                              feedback_note=None, headline_only=False):
        self.triage_calls.append(article_title)
        self.last_triage_feedback_note = feedback_note
        relevant = article_title not in self.not_relevant_titles
        return TriageResult(relevant=relevant, reason="test"), USAGE

    def summarize_theme_article(self, *, company_name, offering_description, theme_name, query_terms,
                                 article_title, article_description, industry=None,
                                 feedback_note=None, output_language="en", headline_only=False):
        self.last_summarize_feedback_note = feedback_note
        self.summarize_calls.append(article_title)
        if article_title in self.fail_summarize_titles:
            from app.services.ai_client import AIClientError

            raise AIClientError("model unavailable")
        return (
            ThemeArticleResult(
                extracted_company_name=self.extracted_company_by_title.get(article_title),
                summary=f"Summary of {article_title}",
                business_relevance="Relevant because reasons",
                relevance_score=self.relevance_score_by_title.get(article_title, 4),
                signal_type="funding",
                confidence="high",
                entities={},
            ),
            USAGE,
        )


def _make_theme(
    db_session, name="Automotive", query_terms=None, exclude_terms=None, is_active=True
) -> ThemeWatch:
    theme = ThemeWatch(
        name=name,
        query_terms=query_terms or ["EV battery"],
        exclude_terms=exclude_terms or [],
        is_active=is_active,
    )
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
        articles=[_article("EV battery sales up 20% industry-wide", "https://example.com/ev-trend")]
    )
    ai = FakeThemeAIClient(extracted_company_by_title={"EV battery sales up 20% industry-wide": None})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1
    match = db_session.query(ThemeMatch).one()
    assert match.extracted_company_name is None


def test_theme_ingestion_drops_article_containing_an_excluded_term(db_session):
    """exclude_terms are sent to the provider as `-term`, but the fake client here
    ignores query content entirely, so this article slips past the provider unfiltered —
    exactly the scenario the client-side backstop exists for."""
    _make_theme(db_session, name="Automotive", exclude_terms=["EV/EBITDA"])
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[
            _article(
                "EV maker trades at a rich EV/EBITDA multiple",
                "https://example.com/ev-valuation",
            )
        ]
    )
    ai = FakeThemeAIClient()

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 0
    assert db_session.query(ThemeMatch).count() == 0
    assert ai.triage_calls == []  # dropped before it ever reaches (paid) triage


def test_theme_ingestion_keeps_article_when_excluded_term_is_absent(db_session):
    _make_theme(db_session, name="Automotive", exclude_terms=["EV/EBITDA"])
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Acme Corp raises $10M for EV batteries", "https://example.com/acme-ev")]
    )
    ai = FakeThemeAIClient(
        extracted_company_by_title={"Acme Corp raises $10M for EV batteries": "Acme Corp"}
    )

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 1


def test_theme_ingestion_auto_links_existing_target_company(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    tc = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)

    google = FakeGoogleClient(
        articles=[_article("Acme Corp raises $10M for EV batteries", "https://example.com/acme-ev")],
        articles_by_company={"Acme Corp": []},
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
        articles=[_article("EV battery plant softball team wins local derby", "https://example.com/softball")]
    )
    ai = FakeThemeAIClient(not_relevant_titles={"EV battery plant softball team wins local derby"})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert result.theme_matches_created == 0
    assert result.triaged_out == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason == "triaged_out"
    assert ai.summarize_calls == []


def test_theme_ingestion_skips_match_below_relevance_floor(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("EV battery industry sees broad growth this quarter", "https://example.com/broad-growth")]
    )
    ai = FakeThemeAIClient(
        relevance_score_by_title={"EV battery industry sees broad growth this quarter": 2}
    )

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    # Default workspace_settings.theme_match_min_relevance_score is 3, so a score-2
    # match (tangential background news, no outreach angle) must not be surfaced —
    # but it did run through full summarization, unlike a triaged_out article.
    assert result.theme_matches_created == 0
    assert result.triaged_out == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason == "low_relevance"
    assert match.relevance_score == 2
    assert match.summary == "Summary of EV battery industry sees broad growth this quarter"
    assert ai.summarize_calls == ["EV battery industry sees broad growth this quarter"]


def test_theme_ingestion_keeps_match_at_relevance_floor(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Acme Corp secures EV battery supply deal", "https://example.com/acme-deal")]
    )
    ai = FakeThemeAIClient(relevance_score_by_title={"Acme Corp secures EV battery supply deal": 3})

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    # Exactly at the default floor (3) — must be kept, not skipped.
    assert result.theme_matches_created == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason is None
    assert match.relevance_score == 3


def test_theme_ingestion_respects_custom_relevance_floor(db_session):
    from app.services.workspace_settings import get_or_create_workspace_settings

    settings = get_or_create_workspace_settings(db_session)
    settings.theme_match_min_relevance_score = 1
    db_session.commit()

    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("EV battery industry sees broad growth this quarter", "https://example.com/broad-growth")]
    )
    ai = FakeThemeAIClient(
        relevance_score_by_title={"EV battery industry sees broad growth this quarter": 2}
    )

    result = run_ingestion(db_session, ai_client=ai, google_news_client=google)

    # A workspace that lowers the floor to 1 sees the same score-2 match kept.
    assert result.theme_matches_created == 1
    match = db_session.query(ThemeMatch).one()
    assert match.skip_reason is None


def test_theme_ingestion_dedupes_semantic_duplicate_within_theme(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    same_vector = [1.0] + [0.0] * 63
    google = FakeGoogleClient(
        articles=[
            _article("Acme Corp raises EV battery funding A", "https://example.com/a"),
            _article("Acme Corp raises EV battery funding B", "https://example.com/b"),
        ]
    )
    ai = FakeThemeAIClient(
        embeddings_by_title={
            "Acme Corp raises EV battery funding A": same_vector,
            "Acme Corp raises EV battery funding B": same_vector,
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
            title="Already covered EV battery story",
            url="https://example.com/shared-url",
            description="desc",
        )
    )
    db_session.commit()

    google = FakeGoogleClient(articles=[_article("Already covered EV battery story", "https://example.com/shared-url")])
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
            _article("EV battery story one", "https://example.com/one"),
            _article("EV battery story two", "https://example.com/two"),
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

    assert result.theme_matches_created == 0
    # The skip must be visible, not silent: without this the run reports success and the
    # user is left with a topic that never produces anything and no stated reason. The
    # message names the theme, since with multiple possible providers "no source is
    # enabled" can now be true for one topic and false for another.
    assert len(result.errors) == 1
    assert "none of the news sources this topic may use are enabled" in result.errors[0]
    assert "[theme:Automotive]" in result.errors[0]


def test_no_google_news_disabled_error_when_there_are_no_themes(db_session):
    """The warning is about themes going unserved — a workspace with no themes at all has
    nothing to warn about, whatever its source configuration."""
    result = run_ingestion(db_session, ai_client=FakeThemeAIClient())

    assert result.errors == []


def test_theme_ingestion_records_error_when_rate_limited(db_session, monkeypatch):
    """A per-minute ceiling is normally waited out rather than skipped (see
    wait_for_minute_headroom), so the skip branch is only reached when that wait gives up.
    Patched rather than slept through, so this stays a fast unit test of the branch."""
    theme = _make_theme(db_session, name="Automotive")
    _enable_sources(
        db_session, google_news_rss_enabled=True, google_news_rss_max_requests_per_minute=1
    )
    # Consume the single request of per-minute headroom so the theme's check reports
    # MINUTE_LIMITED and reaches the wait in the first place.
    log_usage(
        db_session,
        source=ArticleSource.GOOGLE_NEWS_RSS,
        target_company_id=None,
        theme_watch_id=theme.id,
        requests_used=1,
    )
    monkeypatch.setattr("app.services.ingestion.wait_for_minute_headroom", lambda *a, **k: False)
    google = FakeGoogleClient(articles=[_article("Some EV battery story", "https://example.com/x")])

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert google.calls == []
    # Previously a silent return: a rate-limited theme was indistinguishable from a theme
    # that simply found no news.
    assert len(result.errors) == 1
    assert "rate limit" in result.errors[0].lower()
    rate_limited_log = (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.call_type == "rate_limited")
        .one()
    )
    assert rate_limited_log.theme_watch_id == theme.id


def test_theme_ingestion_uses_per_theme_country_and_language(db_session):
    """A theme tracking a national market needs its own Google News edition — the
    workspace-wide one can only ever be right for a single market."""
    theme = _make_theme(db_session, name="Startups DE", query_terms=["Startup"])
    theme.google_news_country = "DE"
    theme.google_news_language = "de"
    db_session.commit()
    _enable_sources(
        db_session,
        google_news_rss_enabled=True,
        google_news_rss_country="US",
        google_news_rss_language="en",
    )
    google = FakeGoogleClient(articles=[])

    run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert google.calls[0]["country"] == "DE"
    assert google.calls[0]["language"] == "de"


def test_theme_without_locale_override_inherits_workspace_edition(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(
        db_session,
        google_news_rss_enabled=True,
        google_news_rss_country="US",
        google_news_rss_language="en",
    )
    google = FakeGoogleClient(articles=[])

    run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    # None, not "US"/"en" — the client falls back to its own configured edition, so the
    # workspace value stays the single source of truth for non-overridden themes.
    assert google.calls[0]["country"] is None
    assert google.calls[0]["language"] is None


def test_scoped_run_processes_only_that_theme_and_no_companies(db_session):
    wanted = _make_theme(db_session, name="Automotive", query_terms=["EV battery"])
    _make_theme(db_session, name="Fintech", query_terms=["neobank"])
    company = TargetCompany(name="Acme Corp", aliases=["Acme"], keywords=["Acme"], is_active=True)
    db_session.add(company)
    db_session.commit()
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("EV battery plant opens", "https://example.com/ev")],
        articles_by_company={"Acme Corp": [_article("Acme news", "https://example.com/acme")]},
    )

    result = run_ingestion(
        db_session,
        ai_client=FakeThemeAIClient(),
        google_news_client=google,
        theme_watch_id=wanted.id,
    )

    assert result.themes_processed == 1
    assert result.themes_total == 1
    assert result.target_companies_processed == 0
    assert result.signals_created == 0
    # Exactly one fetch, for the scoped theme — neither the other theme nor the company
    # was touched.
    assert len(google.calls) == 1
    assert google.calls[0]["name"] is None
    matches = db_session.query(ThemeMatch).all()
    assert [m.theme_watch_id for m in matches] == [wanted.id]


def test_scoped_run_ignores_a_paused_other_theme_and_still_runs_the_target(db_session):
    wanted = _make_theme(db_session, name="Automotive")
    _make_theme(db_session, name="Paused", is_active=False)
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("EV battery plant", "https://example.com/ev")])

    result = run_ingestion(
        db_session,
        ai_client=FakeThemeAIClient(),
        google_news_client=google,
        theme_watch_id=wanted.id,
    )

    assert result.themes_processed == 1
    assert result.theme_matches_created == 1


def test_theme_fetch_usage_is_attributed_to_the_theme(db_session):
    theme = _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("EV battery story", "https://example.com/ev")])

    run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    log = (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.call_type == "latest")
        .one()
    )
    assert log.theme_watch_id == theme.id
    assert log.target_company_id is None


def test_company_ingestion_skips_url_already_covered_by_a_theme_match(db_session):
    """The mirror image of the existing theme-side check. Without it the cross-path URL
    dedupe held in one direction only, so the same story surfaced as both a theme match
    and a company signal depending purely on which loop fetched it first."""
    theme = _make_theme(db_session, name="Automotive")
    db_session.add(
        ThemeMatch(
            theme_watch_id=theme.id,
            source=ArticleSource.GOOGLE_NEWS_RSS,
            source_name="Reuters",
            title="Acme opens EV battery plant",
            url="https://example.com/shared-story",
            description="desc",
        )
    )
    company = TargetCompany(name="Acme Corp", aliases=["Acme"], keywords=["Acme"], is_active=True)
    db_session.add(company)
    db_session.commit()
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[],
        articles_by_company={
            "Acme Corp": [_article("Acme opens EV battery plant", "https://example.com/shared-story")]
        },
    )

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert result.articles_new == 0
    assert result.signals_created == 0
    assert db_session.query(Article).count() == 0


def test_theme_ingestion_skips_inactive_themes(db_session):
    _make_theme(db_session, name="Paused theme", is_active=False)
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("Some EV battery story", "https://example.com/x")])

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert result.themes_processed == 0
    assert google.calls == []


def test_theme_ingestion_continues_after_ai_failure(db_session):
    _make_theme(db_session, name="Automotive")
    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("EV battery story that will fail", "https://example.com/fail")])
    ai = FakeThemeAIClient(fail_summarize_titles={"EV battery story that will fail"})

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


def test_theme_ingestion_computes_and_passes_feedback_note(db_session):
    """See docs/topics-ux-improvements-planning.html §3.1: refresh_theme_feedback_note
    runs once per theme per ingestion pass, and the resulting note is threaded into both
    the triage and summarize calls."""
    from app.models.signal import SignalStatus
    from app.services.feedback import MIN_SAMPLE_SIZE

    theme = _make_theme(db_session, name="Automotive")
    for i in range(MIN_SAMPLE_SIZE):
        db_session.add(
            ThemeMatch(
                theme_watch_id=theme.id,
                source_name="Example",
                title=f"Old article {i}",
                url=f"https://example.com/old-{i}",
                extracted_company_name="NoiseCo",
                status=SignalStatus.DISMISSED,
            )
        )
    db_session.commit()

    _enable_sources(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Acme Corp raises $10M for EV batteries", "https://example.com/acme-ev")]
    )
    ai = FakeThemeAIClient(
        extracted_company_by_title={"Acme Corp raises $10M for EV batteries": "Acme Corp"}
    )

    run_ingestion(db_session, ai_client=ai, google_news_client=google)

    db_session.refresh(theme)
    assert "NoiseCo" in theme.ai_feedback_note
    assert ai.last_triage_feedback_note == theme.ai_feedback_note
    assert ai.last_summarize_feedback_note == theme.ai_feedback_note
