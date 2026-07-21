from datetime import datetime, timedelta, timezone

from app.services.google_news_rss_client import GoogleNewsRSSClient


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


def test_fetch_articles_filters_entries_older_than_since(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)

    class FakeFeed:
        bozo = False
        entries = [
            {
                "title": "Recent - Outlet",
                "link": "https://example.com/recent",
                "published_parsed": now.timetuple(),
            },
            {
                "title": "Old - Outlet",
                "link": "https://example.com/old",
                "published_parsed": (now - timedelta(days=5)).timetuple(),
            },
        ]

        def get(self, key, default=None):
            return getattr(self, key, default)

    monkeypatch.setattr(
        "app.services.google_news_rss_client.feedparser.parse", lambda url: FakeFeed()
    )

    articles = client.fetch_articles(name="Acme", keywords=[], since=now - timedelta(days=1))
    assert [a.title for a in articles] == ["Recent"]


def test_fetch_articles_includes_site_restriction_in_query_url(monkeypatch):
    client = GoogleNewsRSSClient(country="US", language="en")
    now = datetime.now(timezone.utc)

    class EmptyFeed:
        bozo = False
        entries: list = []

        def get(self, key, default=None):
            return getattr(self, key, default)

    captured = {}

    def fake_parse(url):
        captured["url"] = url
        return EmptyFeed()

    monkeypatch.setattr("app.services.google_news_rss_client.feedparser.parse", fake_parse)

    client.fetch_articles(
        name="Acme", keywords=[], since=now - timedelta(days=1), sources=["reuters.com"]
    )
    assert "site%3Areuters.com" in captured["url"]
