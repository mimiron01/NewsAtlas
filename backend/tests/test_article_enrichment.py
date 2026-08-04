from dataclasses import dataclass, field

from app.services import article_enrichment
from app.services.article_enrichment import (
    EnrichmentBudget,
    enrich_articles,
    extract_description,
    needs_url_resolution,
)


@dataclass
class Row:
    url: str
    description: str | None = None
    canonical_url: str | None = None
    content_enriched: bool = False
    full_content: str | None = None


@dataclass
class Settings:
    google_news_resolve_urls_enabled: bool = False
    google_news_fetch_snippets_enabled: bool = False


GOOGLE_URL = "https://news.google.com/rss/articles/CBMiabc123"


def test_needs_url_resolution_only_for_google_redirects():
    assert needs_url_resolution(GOOGLE_URL)
    assert not needs_url_resolution("https://reuters.com/story")


def test_extract_description_prefers_json_ld():
    html = """
    <html><head>
    <meta property="og:description" content="Site-wide tagline">
    <script type="application/ld+json">
      {"@type": "NewsArticle", "description": "Acme raised $10M in a Series B round."}
    </script>
    </head></html>
    """
    assert extract_description(html) == "Acme raised $10M in a Series B round."


def test_extract_description_handles_json_ld_graph_wrapper():
    html = """
    <script type="application/ld+json">
      {"@graph": [{"@type": "WebSite"}, {"@type": "NewsArticle", "description": "Real story text."}]}
    </script>
    """
    assert extract_description(html) == "Real story text."


def test_extract_description_falls_back_to_og_description():
    html = '<meta property="og:description" content="Acme opens a new plant.">'
    assert extract_description(html) == "Acme opens a new plant."


def test_extract_description_handles_reversed_attribute_order():
    html = '<meta content="Reversed order still works." name="description">'
    assert extract_description(html) == "Reversed order still works."


def test_extract_description_returns_none_without_metadata():
    assert extract_description("<html><body>No metadata here</body></html>") is None


def test_extract_description_strips_tags_and_caps_length():
    html = f'<meta property="og:description" content="{"a" * 3000}">'
    assert len(extract_description(html)) == article_enrichment.MAX_SNIPPET_CHARS


def test_enrichment_is_a_no_op_when_both_toggles_are_off(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("no network call may happen while enrichment is disabled")

    monkeypatch.setattr(article_enrichment, "resolve_article_url", explode)
    monkeypatch.setattr(article_enrichment, "fetch_description", explode)

    row = Row(url=GOOGLE_URL)
    enrich_articles([row], Settings())

    assert row.canonical_url is None
    assert row.content_enriched is False


def test_resolution_populates_canonical_url(monkeypatch):
    monkeypatch.setattr(
        article_enrichment, "resolve_article_url", lambda _url: "https://publisher.example/story"
    )
    row = Row(url=GOOGLE_URL)

    enrich_articles([row], Settings(google_news_resolve_urls_enabled=True))

    assert row.canonical_url == "https://publisher.example/story"


def test_failed_resolution_leaves_the_row_untouched(monkeypatch):
    """Google serves consent interstitials to some datacenter IPs; that's an ordinary
    outcome, not an error."""
    monkeypatch.setattr(article_enrichment, "resolve_article_url", lambda _url: None)
    row = Row(url=GOOGLE_URL)

    enrich_articles([row], Settings(google_news_resolve_urls_enabled=True))

    assert row.canonical_url is None


def test_snippet_enrichment_sets_description_and_flag(monkeypatch):
    monkeypatch.setattr(
        article_enrichment, "resolve_article_url", lambda _url: "https://publisher.example/story"
    )
    monkeypatch.setattr(article_enrichment, "fetch_description", lambda _url: "Real body text.")
    row = Row(url=GOOGLE_URL, description="Headline repeated")

    enrich_articles(
        [row],
        Settings(google_news_resolve_urls_enabled=True, google_news_fetch_snippets_enabled=True),
    )

    assert row.description == "Real body text."
    assert row.content_enriched is True


def test_snippet_enrichment_skips_an_unresolved_google_link(monkeypatch):
    """Fetching the redirect URL itself would scrape Google's page, not the article."""
    monkeypatch.setattr(article_enrichment, "fetch_description", lambda _url: "should not be used")
    row = Row(url=GOOGLE_URL)

    enrich_articles([row], Settings(google_news_fetch_snippets_enabled=True))

    assert row.content_enriched is False


def test_snippet_enrichment_skips_rows_that_already_have_full_content(monkeypatch):
    monkeypatch.setattr(article_enrichment, "fetch_description", lambda _url: "meta description")
    row = Row(url="https://publisher.example/a", full_content="A full article body")

    enrich_articles([row], Settings(google_news_fetch_snippets_enabled=True))

    assert row.description is None
    assert row.content_enriched is False


def test_budget_stops_after_the_fetch_cap():
    budget = EnrichmentBudget(max_fetches=2, max_seconds=0)
    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False


def test_budget_stops_after_the_time_cap():
    clock = iter([0.0, 1.0, 99.0])
    budget = EnrichmentBudget(max_fetches=0, max_seconds=10, clock=lambda: next(clock))
    assert budget.consume() is True
    assert budget.consume() is False


def test_budget_of_zero_is_unlimited():
    budget = EnrichmentBudget(max_fetches=0, max_seconds=0)
    assert all(budget.consume() for _ in range(100))


def test_enrichment_stops_when_the_budget_is_exhausted(monkeypatch):
    monkeypatch.setattr(article_enrichment, "resolve_article_url", lambda _url: "https://p.example/a")
    rows = [Row(url=f"{GOOGLE_URL}{i}") for i in range(5)]

    enrich_articles(
        rows, Settings(google_news_resolve_urls_enabled=True), budget=EnrichmentBudget(2, 0)
    )

    assert [r.canonical_url is not None for r in rows] == [True, True, False, False, False]
