"""Shared helpers used by every news provider client (NewsClient, GoogleNewsRSSClient,
NewsDataClient) so the query-building and URL-safety logic lives in exactly one place
instead of being copied per provider.
"""


def build_or_query(name: str, keywords: list[str]) -> str:
    """Builds an OR-joined, quoted search query from a target company's name + keywords.

    Multi-word terms are quoted so the provider treats them as a phrase rather than
    independent keywords; duplicate terms (case-insensitive) are dropped.
    """
    terms = [name, *keywords]
    seen: set[str] = set()
    quoted_terms: list[str] = []
    for term in terms:
        term = term.strip()
        if not term or term.lower() in seen:
            continue
        seen.add(term.lower())
        quoted_terms.append(f'"{term}"' if " " in term else term)
    return " OR ".join(quoted_terms)


def is_safe_article_url(url: str | None) -> bool:
    """Only ever accept http(s) URLs — these get rendered as clickable links in the
    dashboard and in digest emails, so a javascript:/data: URL from a malicious or
    compromised upstream feed would otherwise be a stored-XSS vector."""
    return bool(url) and url.startswith(("http://", "https://"))


def article_mentions_company(
    *, title: str, description: str | None, full_content: str | None, name: str, keywords: list[str]
) -> bool:
    """True if the company name or any configured keyword/alias appears as a
    case-insensitive substring somewhere in the article's title/description/full_content.

    build_or_query() above asks providers for an OR match on name-or-any-keyword, which
    is necessary for keywords to work as aliases — but providers' own search relevance is
    frequently loose/fuzzy (stemming, related-entity matches, etc.), so they can return an
    article that never actually contains any of the terms it was matched on. This is a
    cheap grounding guard against exactly that: articles that fail this check should never
    be attributed to the company (see docs/ingestion-reliability-planning.html §5).
    """
    haystack = " ".join(filter(None, [title, description, full_content])).lower()
    for term in [name, *keywords]:
        term = term.strip()
        if term and term.lower() in haystack:
            return True
    return False
