from app.services.news_query import build_or_query, is_safe_article_url


def test_build_or_query_dedupes_and_quotes_multiword_terms():
    assert build_or_query("Acme Corp", ["Acme", "acme.com", "Acme Corp"]) == '"Acme Corp" OR Acme OR acme.com'


def test_build_or_query_ignores_blank_keywords():
    assert build_or_query("Acme", ["", "  ", "Acme"]) == "Acme"


def test_is_safe_article_url_accepts_http_and_https():
    assert is_safe_article_url("http://example.com/a")
    assert is_safe_article_url("https://example.com/a")


def test_is_safe_article_url_rejects_javascript_and_data_schemes():
    assert not is_safe_article_url("javascript:alert(document.cookie)")
    assert not is_safe_article_url("data:text/html,<script>alert(1)</script>")


def test_is_safe_article_url_rejects_missing_url():
    assert not is_safe_article_url(None)
    assert not is_safe_article_url("")
