"""End-to-end coverage for docs/google-news-quality-planning.html.

Each test names the finding it protects, because most of these behaviours look like
implementation detail until you know which failure they were written to prevent.
"""
from datetime import datetime, timedelta, timezone

from app.models.article import Article, ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.services.ingestion import run_ingestion
from app.services.news_client import FetchOutcome, NewsArticle
from app.services.workspace_settings import get_or_create_workspace_settings

from tests.test_ingestion import FakeAIClient, FakeNewsClient
from tests.test_theme_ingestion import FakeThemeAIClient


def _article(title, url, published_at=None, description="desc"):
    return NewsArticle(
        source_name="Reuters",
        title=title,
        url=url,
        description=description,
        published_at=published_at or datetime.now(timezone.utc),
    )


class FakeGoogleClient:
    """Records the query it was asked for and replays a fixed result set."""

    def __init__(self, articles=None, raw_extra=0):
        self.articles = articles or []
        self.raw_extra = raw_extra
        self.calls: list[dict] = []

    def fetch_articles(
        self, *, name=None, keywords=None, since, sources=None, query_override=None,
        country=None, language=None, when=None,
    ):
        self.calls.append(
            {"query": query_override, "country": country, "language": language, "when": when}
        )
        return FetchOutcome(
            articles=list(self.articles),
            requests_used=1,
            query_text=query_override,
            articles_raw=len(self.articles) + self.raw_extra,
            drop_counts={"stale": self.raw_extra} if self.raw_extra else {},
        )


def _settings(db_session, **flags):
    settings = get_or_create_workspace_settings(db_session)
    for key, value in flags.items():
        setattr(settings, key, value)
    db_session.commit()
    return settings


def _company(db_session, name="Acme Corp", **kwargs):
    kwargs.setdefault("aliases", ["Acme"])
    kwargs.setdefault("keywords", ["Acme"])
    company = TargetCompany(name=name, is_active=True, **kwargs)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


# --- Phase 0: the funnel is visible ------------------------------------------------


def test_usage_log_records_the_query_and_the_full_drop_funnel(db_session):
    _company(db_session)
    _settings(db_session, google_news_rss_enabled=True, max_articles_per_company_per_run=1)
    google = FakeGoogleClient(
        articles=[
            _article("Acme wins a contract", "https://example.com/1"),
            _article("Acme opens a plant", "https://example.com/2"),
            _article("Unrelated firm news", "https://example.com/3"),
        ],
        raw_extra=4,
    )

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    log = (
        db_session.query(NewsSourceUsageLog)
        .filter(NewsSourceUsageLog.source == ArticleSource.GOOGLE_NEWS_RSS)
        .one()
    )
    assert "Acme Corp" in log.query_text
    assert log.articles_raw == 7
    # Stale drops come from the client, the rest from the pipeline — one row explains the
    # whole funnel, which is the entire point of deferring the write.
    assert log.drop_counts["stale"] == 4
    assert log.drop_counts["not_grounded"] == 1
    assert log.drop_counts["over_cap"] == 1


def test_usage_log_is_written_even_when_everything_is_dropped(db_session):
    """A run where nothing survived is exactly when the funnel matters most."""
    _company(db_session)
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("Totally unrelated story", "https://example.com/x")])

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    log = db_session.query(NewsSourceUsageLog).one()
    assert log.drop_counts["not_grounded"] == 1
    assert log.articles_returned == 1


# --- Phase 1: recency + edition ----------------------------------------------------


def test_query_carries_the_when_operator_by_default(db_session):
    _company(db_session)
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert "when:" in google.calls[0]["query"]


def test_time_operator_can_be_switched_off(db_session):
    _company(db_session)
    _settings(db_session, google_news_rss_enabled=True, google_news_time_operator_enabled=False)
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert "when:" not in google.calls[0]["query"]


def test_per_company_edition_overrides_the_workspace_one(db_session):
    _company(db_session, google_news_country="DE", google_news_language="de")
    _settings(
        db_session,
        google_news_rss_enabled=True,
        google_news_rss_country="US",
        google_news_rss_language="en",
    )
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert google.calls[0]["country"] == "DE"
    assert google.calls[0]["language"] == "de"


def test_company_without_an_edition_inherits_the_workspace_one(db_session):
    _company(db_session)
    _settings(
        db_session,
        google_news_rss_enabled=True,
        google_news_rss_country="DE",
        google_news_rss_language="de",
    )
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert google.calls[0]["country"] == "DE"


def test_paid_providers_receive_the_companys_language_not_hardcoded_english(db_session):
    """Finding F16: both paid clients pinned language="en", so a German-market workspace
    could not get native-language coverage from them at all."""
    _company(db_session, google_news_language="de")
    _settings(db_session, newsapi_enabled=True)
    news = FakeNewsClient({"Acme Corp": []})

    run_ingestion(db_session, news_client=news, ai_client=FakeAIClient())

    assert news.languages == ["de"]


# --- Phase 2: term roles + allowlist override --------------------------------------


def test_context_terms_narrow_the_query_and_aliases_widen_the_identity_group(db_session):
    _company(db_session, aliases=["Acme"], context_terms=["Motorsport"], keywords=["Acme"])
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    query = google.calls[0]["query"]
    assert '("Acme Corp" OR Acme)' in query
    assert "Motorsport" in query


def test_exclusions_and_denylist_reach_the_query(db_session):
    _company(db_session, exclude_terms=["Aktie"], google_news_source_denylist=["spam.example"])
    _settings(
        db_session, google_news_rss_enabled=True, google_news_source_denylist=["msn.com"]
    )
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    query = google.calls[0]["query"]
    assert "-Aktie" in query
    # Union, not override: the workspace policy survives the company's own additions.
    assert "-site:msn.com" in query
    assert "-site:spam.example" in query


def test_company_allowlist_replaces_the_workspace_one(db_session):
    _company(db_session, google_news_source_allowlist=["heise.de"])
    _settings(db_session, google_news_rss_enabled=True, google_news_source_allowlist=["reuters.com"])
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    query = google.calls[0]["query"]
    assert "site:heise.de" in query
    assert "reuters.com" not in query


def test_empty_company_allowlist_means_unrestricted_not_inherit(db_session):
    """The distinction the nullable column exists for — without it a workspace allowlist
    could never be opted out of."""
    _company(db_session, google_news_source_allowlist=[])
    _settings(db_session, google_news_rss_enabled=True, google_news_source_allowlist=["reuters.com"])
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert "site:" not in google.calls[0]["query"]


def test_grounding_guard_rejects_a_context_term_only_match(db_session):
    """Finding F2, end to end: this article would previously have been stored under this
    company and summarized as if it were about it."""
    _company(db_session, aliases=[], context_terms=["Produktion"], keywords=["Produktion"])
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Andere Firma erweitert Produktion", "https://example.com/other")]
    )

    result = run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert result.articles_new == 0
    assert db_session.query(Article).count() == 0


def test_split_query_strategy_issues_a_second_identity_only_fetch(db_session):
    _company(db_session, context_terms=["Motorsport"])
    _settings(
        db_session, google_news_rss_enabled=True, google_news_query_strategy="split"
    )
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert len(google.calls) == 2
    assert "Motorsport" in google.calls[0]["query"]
    assert "Motorsport" not in google.calls[1]["query"]


def test_split_strategy_does_not_double_fetch_without_context_terms(db_session):
    _company(db_session, context_terms=[])
    _settings(db_session, google_news_rss_enabled=True, google_news_query_strategy="split")
    google = FakeGoogleClient()

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert len(google.calls) == 1


# --- Phase 3: selection ------------------------------------------------------------


def test_cap_keeps_the_best_candidate_not_the_newest(db_session):
    """Finding F5: newest-first handed the whole AI budget to aggregator reposts."""
    _company(db_session, google_news_source_allowlist=["reuters.com"])
    _settings(db_session, google_news_rss_enabled=True, max_articles_per_company_per_run=1)
    now = datetime.now(timezone.utc)
    google = FakeGoogleClient(
        articles=[
            _article("Acme Corp wins major contract", "https://reuters.com/acme", now - timedelta(hours=6)),
            _article("Roundup mentioning Acme Corp", "https://aggregator.example/x", now),
        ]
    )

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    article = db_session.query(Article).one()
    assert article.url == "https://reuters.com/acme"


def test_syndicated_copies_collapse_before_any_embedding_call(db_session):
    _company(db_session)
    _settings(db_session, google_news_rss_enabled=True)
    ai = FakeAIClient()
    google = FakeGoogleClient(
        articles=[
            _article("Acme Corp raises $10M in Series B - Outlet A", "https://a.example/1"),
            _article("Acme Corp raises $10M in Series B - Outlet B", "https://b.example/2"),
        ]
    )

    run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert db_session.query(Article).count() == 1


def test_the_same_story_can_belong_to_two_tracked_companies(db_session):
    """Finding F12: a global URL constraint silently gave the story to whichever company
    the loop reached first."""
    _company(db_session, name="Acme Corp", aliases=["Acme"], keywords=["Acme"])
    _company(db_session, name="Beta GmbH", aliases=["Beta"], keywords=["Beta"])
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(
        articles=[_article("Acme Corp acquires Beta GmbH", "https://example.com/deal")]
    )

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    articles = db_session.query(Article).all()
    assert len(articles) == 2
    assert {a.target_company_id for a in articles} == {
        c.id for c in db_session.query(TargetCompany).all()
    }
    assert db_session.query(Signal).count() == 2


def test_a_company_still_never_ingests_the_same_url_twice(db_session):
    company = _company(db_session)
    _settings(db_session, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("Acme Corp news", "https://example.com/one")])

    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)
    run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert (
        db_session.query(Article).filter(Article.target_company_id == company.id).count() == 1
    )


# --- Company-scoped runs (POST /target-companies/{id}/run-now and /run-now bulk) ---


def test_company_scoped_run_processes_only_selected_companies_and_no_themes(db_session):
    wanted = _company(db_session, name="Acme Corp", aliases=["Acme"], keywords=["Acme"])
    _company(db_session, name="Other Corp", aliases=["Other"], keywords=["Other"])
    _theme(db_session, name="Automotive")
    _settings(db_session, newsapi_enabled=True)
    news = FakeNewsClient(
        {
            "Acme Corp": [_article("Acme wins a contract", "https://example.com/acme")],
            "Other Corp": [_article("Other Corp news", "https://example.com/other")],
        }
    )

    result = run_ingestion(
        db_session, ai_client=FakeAIClient(), news_client=news, target_company_ids=[wanted.id]
    )

    assert result.target_companies_processed == 1
    assert result.themes_processed == 0
    assert result.themes_total == 0
    # Exactly one fetch, for the scoped company — neither the other company nor the theme
    # was touched.
    assert news.calls == ["Acme Corp"]
    assert [a.target_company_id for a in db_session.query(Article).all()] == [wanted.id]


def test_company_scoped_run_excludes_a_paused_selected_company(db_session):
    active = _company(db_session, name="Acme Corp", aliases=["Acme"], keywords=["Acme"])
    paused = _company(db_session, name="Paused Co", aliases=["Paused"], keywords=["Paused"])
    paused.is_active = False
    db_session.commit()
    _settings(db_session, newsapi_enabled=True)
    news = FakeNewsClient(
        {
            "Acme Corp": [_article("Acme wins a contract", "https://example.com/acme")],
            "Paused Co": [_article("Paused Co news", "https://example.com/paused")],
        }
    )

    result = run_ingestion(
        db_session,
        ai_client=FakeAIClient(),
        news_client=news,
        target_company_ids=[active.id, paused.id],
    )

    assert result.target_companies_processed == 1
    assert news.calls == ["Acme Corp"]


# --- Phase 6: multi-provider themes ------------------------------------------------


def _theme(db_session, **kwargs):
    kwargs.setdefault("query_terms", ["EV battery"])
    theme = ThemeWatch(name=kwargs.pop("name", "Automotive"), is_active=True, **kwargs)
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def test_theme_defaults_to_google_news_only(db_session):
    _theme(db_session)
    _settings(db_session, google_news_rss_enabled=True, newsapi_enabled=True)
    google = FakeGoogleClient(articles=[_article("EV battery plant opens", "https://example.com/ev")])
    news = FakeNewsClient({})

    run_ingestion(db_session, news_client=news, ai_client=FakeThemeAIClient(), google_news_client=google)

    match = db_session.query(ThemeMatch).one()
    assert match.source == ArticleSource.GOOGLE_NEWS_RSS
    # NewsAPI was enabled workspace-wide but is not in the default theme source list.
    assert news.calls == []


def test_theme_can_opt_into_newsapi(db_session):
    _theme(db_session, news_sources=["newsapi"])
    _settings(db_session, newsapi_enabled=True)
    news = FakeNewsClient({})
    news.articles_by_company[""] = [_article("EV battery plant opens", "https://example.com/ev")]

    run_ingestion(db_session, news_client=news, ai_client=FakeThemeAIClient())

    match = db_session.query(ThemeMatch).one()
    assert match.source == ArticleSource.NEWSAPI


def test_theme_source_selection_cannot_resurrect_a_disabled_provider(db_session):
    """The workspace enable toggles stay the master switch."""
    _theme(db_session, news_sources=["newsapi"])
    _settings(db_session, newsapi_enabled=False, google_news_rss_enabled=True)
    google = FakeGoogleClient(articles=[_article("EV battery plant", "https://example.com/ev")])

    result = run_ingestion(db_session, ai_client=FakeAIClient(), google_news_client=google)

    assert db_session.query(ThemeMatch).count() == 0
    assert any("none of the news sources" in error for error in result.errors)


def test_theme_term_guard_rejects_an_off_theme_article_before_triage(db_session):
    """Finding F17: LLM triage used to be the first filter anything on this path met."""
    _theme(db_session)
    _settings(db_session, google_news_rss_enabled=True)
    ai = FakeAIClient()
    google = FakeGoogleClient(
        articles=[_article("Local football club wins derby", "https://example.com/football")]
    )

    run_ingestion(db_session, ai_client=ai, google_news_client=google)

    assert db_session.query(ThemeMatch).count() == 0
    assert ai.triage_calls == []


def test_theme_request_budget_stops_further_fetches(db_session):
    _theme(db_session, name="One")
    _theme(db_session, name="Two")
    _settings(
        db_session, google_news_rss_enabled=True, max_theme_requests_per_run_per_source=1
    )
    google = FakeGoogleClient(articles=[_article("EV battery plant", "https://example.com/ev")])

    result = run_ingestion(db_session, ai_client=FakeThemeAIClient(), google_news_client=google)

    assert len(google.calls) == 1
    assert any("request budget" in error for error in result.errors)
