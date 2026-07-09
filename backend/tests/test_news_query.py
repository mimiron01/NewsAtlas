from app.services.news_query import article_mentions_company, build_or_query, is_safe_article_url


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
