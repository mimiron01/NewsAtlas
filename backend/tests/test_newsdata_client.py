import pytest

from app.services.news_client import NewsClientError
from app.services.newsdata_client import NewsDataClient, _clean_gated_field, _parse_tags


def test_base_params_requires_api_key():
    client = NewsDataClient(api_key="")
    with pytest.raises(NewsClientError, match="NEWSDATA_API_KEY"):
        client._base_params("Acme", [], full_content=False, use_native_dedupe=True)


def test_base_params_includes_dedupe_and_full_content_flags():
    client = NewsDataClient(api_key="test-key")
    params = client._base_params("Acme", ["Acme Corp"], full_content=True, use_native_dedupe=True)
    assert params["removeduplicate"] == 1
    assert params["full_content"] == 1
    assert params["q"] == 'Acme OR "Acme Corp"'


def test_base_params_omits_flags_when_disabled():
    client = NewsDataClient(api_key="test-key")
    params = client._base_params("Acme", [], full_content=False, use_native_dedupe=False)
    assert "removeduplicate" not in params
    assert "full_content" not in params


def test_parse_article_rejects_unsafe_url():
    assert NewsDataClient._parse_article({"link": "javascript:alert(1)"}) is None


def test_parse_article_extracts_full_content_sentiment_and_tags():
    item = {
        "link": "https://example.com/a",
        "title": "Acme raises $10M",
        "description": "Short snippet",
        "source_name": "TechCrunch",
        "content": "The full article body goes here.",
        "sentiment": "positive",
        "ai_tag": "funding, startups",
        "pubDate": "2026-07-01 12:00:00",
    }
    article = NewsDataClient._parse_article(item)
    assert article is not None
    assert article.full_content == "The full article body goes here."
    assert article.sentiment == "positive"
    assert article.tags == ["funding", "startups"]
    assert article.source_name == "TechCrunch"
    assert article.published_at is not None


def test_parse_article_filters_gated_placeholder_fields():
    item = {
        "link": "https://example.com/a",
        "title": "T",
        "content": "ONLY AVAILABLE IN PAID PLANS",
        "sentiment": "Not available",
        "ai_tag": "Not available",
    }
    article = NewsDataClient._parse_article(item)
    assert article.full_content is None
    assert article.sentiment is None
    assert article.tags is None


def test_parse_article_handles_malformed_pubdate():
    item = {"link": "https://example.com/a", "title": "T", "pubDate": "not-a-date"}
    article = NewsDataClient._parse_article(item)
    assert article.published_at is None


def test_clean_gated_field():
    assert _clean_gated_field(None) is None
    assert _clean_gated_field("") is None
    assert _clean_gated_field("ONLY AVAILABLE IN PAID PLANS") is None
    assert _clean_gated_field("real value") == "real value"


def test_parse_tags_from_comma_separated_string():
    assert _parse_tags("funding, startups") == ["funding", "startups"]


def test_parse_tags_from_list():
    assert _parse_tags(["funding", "startups"]) == ["funding", "startups"]


def test_parse_tags_handles_none_and_unavailable():
    assert _parse_tags(None) is None
    assert _parse_tags("Not available") is None
