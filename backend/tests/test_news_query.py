from app.services.news_query import (
    article_mentions_company,
    build_google_news_query,
    build_or_query,
    is_safe_article_url,
    is_valid_source_hostname,
)


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


def test_article_mentions_company_matches_on_name_in_title():
    assert article_mentions_company(
        title="Acme Corp raises $10M", description=None, full_content=None,
        name="Acme Corp", keywords=[],
    )


def test_article_mentions_company_matches_on_keyword_in_description():
    assert article_mentions_company(
        title="Big funding round announced",
        description="Acme.com today announced a new funding round.",
        full_content=None,
        name="Acme Corp",
        keywords=["acme.com"],
    )


def test_article_mentions_company_matches_on_full_content_only():
    assert article_mentions_company(
        title="Industry roundup",
        description="A look at recent industry news.",
        full_content="...deep in the article, Acme Corp announced layoffs...",
        name="Acme Corp",
        keywords=[],
    )


def test_article_mentions_company_is_case_insensitive():
    assert article_mentions_company(
        title="ACME CORP posts record earnings", description=None, full_content=None,
        name="Acme Corp", keywords=[],
    )


def test_article_mentions_company_false_when_nothing_matches():
    assert not article_mentions_company(
        title="Unrelated company posts record earnings",
        description="A totally different business made news today.",
        full_content=None,
        name="Acme Corp",
        keywords=["acme.com"],
    )


def test_article_mentions_company_ignores_blank_keywords():
    assert not article_mentions_company(
        title="Some other story", description=None, full_content=None,
        name="Acme Corp", keywords=["", "   "],
    )


def test_build_google_news_query_falls_back_to_name_only_with_no_keywords():
    assert build_google_news_query("Acme", []) == "Acme"


def test_build_google_news_query_requires_name_and_any_keyword():
    assert (
        build_google_news_query("Acme Corp", ["acme.com", "Acme Widgets"])
        == '"Acme Corp" AND (acme.com OR "Acme Widgets")'
    )


def test_build_google_news_query_adds_site_clause_when_sources_given():
    assert (
        build_google_news_query("Acme", ["acme.com"], ["reuters.com", "techcrunch.com"])
        == "(Acme AND (acme.com)) (site:reuters.com OR site:techcrunch.com)"
    )


def test_build_google_news_query_no_sources_omits_site_clause():
    assert build_google_news_query("Acme", ["acme.com"], []) == "Acme AND (acme.com)"


def test_build_google_news_query_dedupes_keywords_case_insensitively():
    assert (
        build_google_news_query("Acme", ["Widgets", "widgets", "Widgets"])
        == "Acme AND (Widgets)"
    )


def test_is_valid_source_hostname_accepts_bare_domains():
    assert is_valid_source_hostname("reuters.com")
    assert is_valid_source_hostname("news.example.co.uk")


def test_is_valid_source_hostname_rejects_scheme_and_path():
    assert not is_valid_source_hostname("https://reuters.com")
    assert not is_valid_source_hostname("reuters.com/world")
    assert not is_valid_source_hostname("reuters.com ")
    assert not is_valid_source_hostname("not a domain")
    assert not is_valid_source_hostname("justaword")
