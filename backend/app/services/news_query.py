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
