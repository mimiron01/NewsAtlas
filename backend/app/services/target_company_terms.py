"""Keeps TargetCompany.keywords synchronized with the split term roles.

`keywords` is retained as a derived column rather than dropped, because it is what
NewsAPI.org/NewsData.io query building (news_query.build_or_query) and every AI prompt
still read. Synchronizing it on write means splitting a company's terms into aliases and
context terms didn't have to touch any of those call sites — the one place the two
representations meet is here (see docs/google-news-quality-planning.html §7.2).
"""


def derive_keywords(aliases: list[str] | None, context_terms: list[str] | None) -> list[str]:
    """The flat legacy list: aliases first, then context terms, de-duplicated
    case-insensitively while preserving each term's original casing and first position.

    Exclusion terms are deliberately absent — `keywords` is OR-joined into provider
    queries and injected into AI prompts, so a term the user wants *excluded* would there
    become a term that broadens the search and steers the model toward the exact subject
    they asked to avoid.
    """
    combined: list[str] = []
    seen: set[str] = set()
    for term in [*(aliases or []), *(context_terms or [])]:
        term = term.strip()
        if not term or term.lower() in seen:
            continue
        seen.add(term.lower())
        combined.append(term)
    return combined


def sync_keywords(target_company) -> None:
    """Recomputes the derived column in place. Call after any write that touches aliases
    or context_terms, before the commit."""
    target_company.keywords = derive_keywords(target_company.aliases, target_company.context_terms)
