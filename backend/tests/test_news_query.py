from datetime import datetime, timedelta, timezone

from app.services.news_query import (
    MAX_QUERY_WORDS,
    article_matches_theme_terms,
    article_mentions_company,
    build_google_news_query,
    build_or_query,
    build_theme_query,
    google_when_operator,
    is_safe_article_url,
    is_valid_source_hostname,
    resolve_allowlist,
    resolve_denylist,
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


# --- Grounding guard (identity only) -----------------------------------------------


def test_article_mentions_company_matches_on_name_in_title():
    assert article_mentions_company(
        title="Acme Corp raises $10M", description=None, full_content=None,
        name="Acme Corp", aliases=[],
    )


def test_article_mentions_company_matches_on_alias_in_description():
    assert article_mentions_company(
        title="Big funding round announced",
        description="Acme.com today announced a new funding round.",
        full_content=None,
        name="Acme Corp",
        aliases=["acme.com"],
    )


def test_article_mentions_company_rejects_context_term_only_match():
    """The finding-F2 regression test.

    A context term is topicality, not identity. Before the term split this same article
    passed the guard — the keyword list was OR'd into it — and was stored under a company
    it never named, which is exactly how wrong-company signals were produced.
    """
    assert not article_mentions_company(
        title="German manufacturers expand production capacity",
        description="Several firms announced new Produktion lines this quarter.",
        full_content=None,
        name="Acme Corp",
        aliases=[],
    )


def test_article_mentions_company_matches_on_full_content_only():
    assert article_mentions_company(
        title="Industry roundup",
        description="A look at recent industry news.",
        full_content="...deep in the article, Acme Corp announced layoffs...",
        name="Acme Corp",
        aliases=[],
    )


def test_article_mentions_company_is_case_insensitive():
    assert article_mentions_company(
        title="ACME CORP posts record earnings", description=None, full_content=None,
        name="Acme Corp", aliases=[],
    )


def test_article_mentions_company_false_when_nothing_matches():
    assert not article_mentions_company(
        title="Unrelated company posts record earnings",
        description="A totally different business made news today.",
        full_content=None,
        name="Acme Corp",
        aliases=["acme.com"],
    )


def test_article_mentions_company_ignores_blank_aliases():
    assert not article_mentions_company(
        title="Some other story", description=None, full_content=None,
        name="Acme Corp", aliases=["", "   "],
    )


# --- Google News query builder ------------------------------------------------------


def test_build_google_news_query_name_only():
    assert build_google_news_query(name="Acme") == ("Acme", False)


def test_build_google_news_query_ors_aliases_into_identity_group():
    assert build_google_news_query(name="Acme Corp", aliases=["Acme", "Acme Widgets"]) == (
        '("Acme Corp" OR Acme OR "Acme Widgets")',
        False,
    )


def test_build_google_news_query_ands_context_terms_as_a_group():
    query, truncated = build_google_news_query(
        name="Acme Corp", context_terms=["Motorsport", "Rennsport"]
    )
    # Implicit AND (a space), not the literal token: unambiguous to Google, and a word
    # cheaper against the length budget.
    assert query == '"Acme Corp" (Motorsport OR Rennsport)'
    assert truncated is False


def test_build_google_news_query_emits_exclusions_and_denylist():
    query, _ = build_google_news_query(
        name="Acme", exclusion_terms=["Aktie"], deny_sites=["msn.com"]
    )
    assert query == "Acme -Aktie -site:msn.com"


def test_build_google_news_query_adds_site_clause_when_allowlisted():
    query, _ = build_google_news_query(name="Acme", allow_sites=["reuters.com", "techcrunch.com"])
    assert query == "Acme (site:reuters.com OR site:techcrunch.com)"


def test_build_google_news_query_appends_when_operator():
    query, _ = build_google_news_query(name="Acme", when="when:1d")
    assert query == "Acme when:1d"


def test_build_google_news_query_wraps_identity_in_intitle_when_requested():
    query, _ = build_google_news_query(
        name="Acme Corp", aliases=["Acme"], require_name_in_title=True
    )
    assert query == '(intitle:"Acme Corp" OR intitle:Acme)'


def test_build_google_news_query_dedupes_terms_case_insensitively():
    query, _ = build_google_news_query(name="Acme", context_terms=["Widgets", "widgets", "Widgets"])
    assert query == "Acme Widgets"


def test_build_google_news_query_drops_context_terms_first_when_over_budget():
    """Documented drop order: context terms only narrow, so losing one widens the query;
    losing an identity term, an exclusion or the freshness operator would change what the
    query means."""
    query, truncated = build_google_news_query(
        name="Acme",
        context_terms=[f"term{i}" for i in range(40)],
        allow_sites=["reuters.com"],
        exclusion_terms=["Aktie"],
        when="when:1d",
    )
    assert truncated is True
    assert len(query.split()) <= MAX_QUERY_WORDS
    assert "Acme" in query
    assert "-Aktie" in query
    assert "when:1d" in query
    assert "site:reuters.com" in query


def test_build_google_news_query_drops_allowlist_after_context_terms():
    query, truncated = build_google_news_query(
        name="Acme", allow_sites=[f"site{i}.com" for i in range(40)]
    )
    assert truncated is True
    assert len(query.split()) <= MAX_QUERY_WORDS


def test_build_google_news_query_reports_truncation_when_nothing_is_droppable():
    """Identity terms are never dropped, so an over-budget query still goes out — but the
    caller is told, instead of Google truncating it silently."""
    query, truncated = build_google_news_query(
        name="Acme", aliases=[f"alias{i}" for i in range(40)]
    )
    assert truncated is True
    assert "alias39" in query


# --- Theme query builder ------------------------------------------------------------


def test_build_theme_query_ors_all_terms_with_no_anchor_name():
    assert build_theme_query(["Automotive", "EV battery"]) == ('(Automotive OR "EV battery")', False)


def test_build_theme_query_dedupes_terms_case_insensitively():
    assert build_theme_query(["Series B", "series b", "Seed round"]) == (
        '("Series B" OR "Seed round")',
        False,
    )


def test_build_theme_query_adds_site_clause_and_exclusions():
    query, _ = build_theme_query(
        ["Automotive"],
        exclusion_terms=["Formel 1"],
        allow_sites=["reuters.com"],
        deny_sites=["msn.com"],
        when="when:1d",
    )
    assert query == 'Automotive -"Formel 1" site:reuters.com -site:msn.com when:1d'


def test_build_theme_query_no_sources_omits_site_clause():
    assert build_theme_query(["Automotive"]) == ("Automotive", False)


# --- Freshness operator -------------------------------------------------------------


def test_google_when_operator_buckets():
    now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    assert google_when_operator(now - timedelta(minutes=30), now) == "when:1h"
    assert google_when_operator(now - timedelta(hours=6), now) == "when:12h"
    assert google_when_operator(now - timedelta(hours=24), now) == "when:1d"
    assert google_when_operator(now - timedelta(hours=48), now) == "when:2d"


def test_google_when_operator_clamps_to_a_week():
    now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    assert google_when_operator(now - timedelta(days=60), now) == "when:7d"


def test_google_when_operator_rounds_up_so_it_never_excludes_wanted_results():
    """The bucket must always cover at least as much as `since` — the exact cut stays
    client-side, and the operator is only a ranking hint."""
    now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    assert google_when_operator(now - timedelta(hours=25), now) == "when:2d"


# --- Theme relevance pre-filter -----------------------------------------------------


def test_article_matches_theme_terms_survives_inflection():
    """Verbatim substring matching would reject this: "EV battery" is not a substring of
    "EV batteries". Theme terms are common nouns and inflect, unlike company names."""
    assert article_matches_theme_terms(
        title="Acme raises $10M for EV batteries",
        description=None,
        full_content=None,
        query_terms=["EV battery"],
    )


def test_article_matches_theme_terms_rejects_unrelated_article():
    assert not article_matches_theme_terms(
        title="Local football club wins derby",
        description="A report from the stadium.",
        full_content=None,
        query_terms=["EV battery", "Series B"],
    )


def test_article_matches_theme_terms_requires_every_token_of_a_term():
    assert not article_matches_theme_terms(
        title="Battery prices fall",
        description=None,
        full_content=None,
        query_terms=["EV battery"],
    )


# --- Allowlist / denylist resolution ------------------------------------------------


def test_resolve_allowlist_none_inherits_workspace():
    assert resolve_allowlist(None, ["reuters.com"]) == ["reuters.com"]


def test_resolve_allowlist_empty_means_explicitly_unrestricted():
    """The distinction the nullable column exists for: [] is not "unset". Without it, a
    workspace allowlist would be impossible to opt out of."""
    assert resolve_allowlist([], ["reuters.com"]) == []


def test_resolve_allowlist_non_empty_replaces_workspace_list():
    assert resolve_allowlist(["heise.de"], ["reuters.com"]) == ["heise.de"]


def test_resolve_denylist_unions_rather_than_overriding():
    """Deliberately asymmetric with the allowlist: a workspace-wide "never accept this"
    shouldn't be droppable by one entity, and union fails safe."""
    assert resolve_denylist(["spam.example"], ["msn.com"]) == ["msn.com", "spam.example"]


def test_resolve_denylist_dedupes():
    assert resolve_denylist(["msn.com"], ["msn.com"]) == ["msn.com"]


# --- Hostname validation ------------------------------------------------------------


def test_is_valid_source_hostname_accepts_bare_domains():
    assert is_valid_source_hostname("reuters.com")
    assert is_valid_source_hostname("news.example.co.uk")


def test_is_valid_source_hostname_rejects_scheme_and_path():
    assert not is_valid_source_hostname("https://reuters.com")
    assert not is_valid_source_hostname("reuters.com/world")
    assert not is_valid_source_hostname("reuters.com ")
    assert not is_valid_source_hostname("not a domain")
    assert not is_valid_source_hostname("justaword")
