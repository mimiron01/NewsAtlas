from datetime import datetime

import pytest

from app.services.news_client import NewsClient, NewsClientError


def test_build_query_dedupes_and_quotes_multiword_terms():
    query = NewsClient._build_query("Acme Corp", ["Acme", "acme.com", "Acme Corp"])
    assert query == '"Acme Corp" OR Acme OR acme.com'


def test_build_query_ignores_blank_keywords():
    query = NewsClient._build_query("Acme", ["", "  ", "Acme"])
    assert query == "Acme"


def test_parse_article_skips_missing_url():
    assert NewsClient._parse_article({"title": "No URL here"}) is None


def test_parse_article_handles_malformed_published_at():
    article = NewsClient._parse_article(
        {"url": "https://example.com/a", "title": "T", "publishedAt": "not-a-date"}
    )
    assert article is not None
    assert article.published_at is None
    assert article.url == "https://example.com/a"


def test_parse_article_defaults_for_missing_fields():
    article = NewsClient._parse_article({"url": "https://example.com/a"})
    assert article.source_name == "Unknown"
    assert article.title == "(untitled)"
    assert article.description is None


def test_fetch_articles_requires_api_key():
    client = NewsClient(api_key="")
    with pytest.raises(NewsClientError, match="NEWSAPI_API_KEY"):
        client.fetch_articles(name="Acme", keywords=[], since=datetime.now())
