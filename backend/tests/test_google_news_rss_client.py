from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.news_client import NewsClientError


def rss(items: list[dict]) -> bytes:
    """Minimal but real Google-News-shaped RSS, so the tests exercise the actual parse
    path rather than a stand-in for it."""
    entries = []
    for item in items:
        published = item.get("published")
        entries.append(
            "<item>"
            f"<title>{item['title']}</title>"
            f"<link>{item['link']}</link>"
            + (f"<description>{item['description']}</description>" if item.get("description") else "")
            + (f"<pubDate>{format_datetime(published)}</pubDate>" if published else "")
            + (
                f'<source url="{item["source_url"]}">{item["source"]}</source>'
                if item.get("source")
                else ""
            )
            + "</item>"
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>News</title>'
        + "".join(entries)
        + "</channel></rss>"
    ).encode()


class FakeResponse:
    def __init__(self, status_code=200, content=b"", encoding="utf-8"):
        self.status_code = status_code
        self.content = content
        self.encoding = encoding


def patch_get(monkeypatch, response, capture: list | None = None):
    def fake_get(url, **kwargs):
        if capture is not None:
            capture.append({"url": url, **kwargs})
        if isinstance(response, Exception):
            raise response
        return response(url) if callable(response) else response

    monkeypatch.setattr("app.services.google_news_rss_client.httpx.get", fake_get)


# --- Entry parsing ------------------------------------------------------------------


def test_parse_entry_extracts_source_from_source_tag_and_strips_title_suffix():
    entry = {
        "title": "Acme raises $10M - TechCrunch",
        "link": "https://news.google.com/rss/articles/abc123",
        "source": {"title": "TechCrunch", "href": "https://techcrunch.com"},
        "summary": "<a href='...'>Acme raises $10M</a>",
    }
    article = GoogleNewsRSSClient._parse_entry(entry)
    assert article is not None
    assert article.title == "Acme raises $10M"
    assert article.source_name == "TechCrunch"
    assert article.description == "Acme raises $10M"


def test_parse_entry_falls_back_to_title_suffix_when_no_source_tag():
    entry = {
        "title": "Acme raises $10M - Reuters",
        "link": "https://news.google.com/rss/articles/def456",
    }
    article = GoogleNewsRSSClient._parse_entry(entry)
    assert article is not None
    assert article.title == "Acme raises $10M"
    assert article.source_name == "Reuters"


def test_parse_entry_rejects_unsafe_url():
    entry = {"title": "T", "link": "javascript:alert(1)"}
    assert GoogleNewsRSSClient._parse_entry(entry) is None


def test_parse_entry_defaults_source_name_when_unavailable():
    entry = {"title": "Just a headline with no dash", "link": "https://example.com/a"}
    article = GoogleNewsRSSClient._parse_entry(entry)
    assert article is not None
    assert article.source_name == "Unknown"
    assert article.title == "Just a headline with no dash"


def test_parse_entry_parses_published_time():
    entry = {
        "title": "T",
        "link": "https://example.com/a",
        "published_parsed": (2026, 7, 1, 12, 0, 0, 0, 0, 0),
    }
    article = GoogleNewsRSSClient._parse_entry(entry)
    assert article.published_at == datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_entry_handles_missing_published_time():
    entry = {"title": "T", "link": "https://example.com/a"}
    article = GoogleNewsRSSClient._parse_entry(entry)
    assert article.published_at is None


# --- Fetching -----------------------------------------------------------------------


def test_fetch_articles_filters_entries_older_than_since_and_counts_the_drop(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)
    patch_get(
        monkeypatch,
        FakeResponse(
            content=rss(
                [
                    {"title": "Recent - Outlet", "link": "https://example.com/recent", "published": now},
                    {
                        "title": "Old - Outlet",
                        "link": "https://example.com/old",
                        "published": now - timedelta(days=5),
                    },
                ]
            )
        ),
    )

    outcome = client.fetch_articles(name="Acme", keywords=[], since=now - timedelta(days=1))

    assert [a.title for a in outcome.articles] == ["Recent"]
    # articles_raw is what Google returned; the gap to len(articles) is explained by
    # drop_counts — that pairing is the whole point of the Phase 0 instrumentation.
    assert outcome.articles_raw == 2
    assert outcome.drop_counts["stale"] == 1


def test_fetch_articles_reports_the_query_it_sent(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)
    patch_get(monkeypatch, FakeResponse(content=rss([])))

    outcome = client.fetch_articles(
        since=now - timedelta(days=1), query_override='Acme -site:msn.com', when="when:1d"
    )

    assert outcome.query_text == "Acme -site:msn.com when:1d"


def test_fetch_articles_appends_the_when_operator_to_the_url(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)
    calls: list[dict] = []
    patch_get(monkeypatch, FakeResponse(content=rss([])), capture=calls)

    client.fetch_articles(since=now - timedelta(days=1), query_override="Acme", when="when:1d")

    assert "when%3A1d" in calls[0]["url"]


def test_fetch_articles_uses_query_override_verbatim_when_given(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)
    calls: list[dict] = []
    patch_get(monkeypatch, FakeResponse(content=rss([])), capture=calls)

    client.fetch_articles(since=now - timedelta(days=1), query_override='Automotive OR "EV battery"')

    assert "Automotive" in calls[0]["url"]
    assert "EV%20battery" in calls[0]["url"]


def test_fetch_articles_builds_canonical_language_region_hl(monkeypatch):
    """Google's documented canonical `hl` is a language-region tag, not a bare code."""
    client = GoogleNewsRSSClient(country="DE", language="de")
    calls: list[dict] = []
    patch_get(monkeypatch, FakeResponse(content=rss([])), capture=calls)

    client.fetch_articles(since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x")

    assert "hl=de-DE" in calls[0]["url"]
    assert "gl=DE" in calls[0]["url"]
    assert "ceid=DE%3Ade" in calls[0]["url"]


def test_fetch_articles_passes_through_an_already_regioned_language(monkeypatch):
    client = GoogleNewsRSSClient(country="BR", language="pt-BR")
    calls: list[dict] = []
    patch_get(monkeypatch, FakeResponse(content=rss([])), capture=calls)

    client.fetch_articles(since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x")

    assert "hl=pt-BR" in calls[0]["url"]


def test_fetch_articles_applies_the_configured_timeout(monkeypatch):
    """The timeout used to be stored and never used, because feedparser did its own fetch
    and has no timeout parameter — an unresponsive Google could hang a whole run."""
    client = GoogleNewsRSSClient(country="US", language="en", timeout=3.5)
    calls: list[dict] = []
    patch_get(monkeypatch, FakeResponse(content=rss([])), capture=calls)

    client.fetch_articles(since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x")

    assert calls[0]["timeout"] == 3.5
    assert "NewsAtlas" in calls[0]["headers"]["User-Agent"]


# --- Failure modes ------------------------------------------------------------------


def test_fetch_articles_raises_on_throttling_instead_of_returning_empty(monkeypatch):
    """A 429 must never look like "this company has no news" — that made throttling
    invisible, run after run."""
    client = GoogleNewsRSSClient(country="US", language="en")
    monkeypatch.setattr("app.services.google_news_rss_client.time.sleep", lambda _s: None)
    patch_get(monkeypatch, FakeResponse(status_code=429))

    with pytest.raises(NewsClientError) as exc:
        client.fetch_articles(
            since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x"
        )
    assert "429" in str(exc.value)


def test_fetch_articles_retries_once_then_succeeds(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    monkeypatch.setattr("app.services.google_news_rss_client.time.sleep", lambda _s: None)
    responses = [FakeResponse(status_code=503), FakeResponse(content=rss([]))]
    patch_get(monkeypatch, lambda _url: responses.pop(0))

    outcome = client.fetch_articles(
        since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x"
    )

    assert outcome.articles == []
    assert responses == []


def test_fetch_articles_does_not_retry_a_client_error(monkeypatch):
    """A 4xx means the request itself is wrong; retrying just repeats it."""
    client = GoogleNewsRSSClient(country="US", language="en")
    attempts: list[dict] = []
    patch_get(monkeypatch, FakeResponse(status_code=400), capture=attempts)

    with pytest.raises(NewsClientError):
        client.fetch_articles(
            since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x"
        )
    assert len(attempts) == 1


def test_fetch_articles_raises_on_transport_error(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    monkeypatch.setattr("app.services.google_news_rss_client.time.sleep", lambda _s: None)
    patch_get(monkeypatch, httpx.ConnectTimeout("timed out"))

    with pytest.raises(NewsClientError):
        client.fetch_articles(
            since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x"
        )


def test_fetch_articles_raises_when_a_200_is_not_valid_rss(monkeypatch):
    """A consent interstitial or error page served with a 200 is still a failed fetch."""
    client = GoogleNewsRSSClient(country="US", language="en")
    patch_get(monkeypatch, FakeResponse(content=b"<html><body>Before you continue</body></html>"))

    with pytest.raises(NewsClientError):
        client.fetch_articles(
            since=datetime.now(timezone.utc) - timedelta(days=1), query_override="x"
        )
