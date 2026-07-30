"""Validators shared across schemas that have a "list of short strings" field spliced
into a news-provider query (TargetCompany.keywords, ThemeWatch.query_terms) or a
Google News site: allowlist (TargetCompany/ThemeWatch/WorkspaceSettings
.google_news_source_allowlist) — kept in one place so the v1 roadmap's length/hostname
caps (§5) apply identically everywhere rather than being re-specified per schema.
"""
from app.models.article import ArticleSource
from app.services.news_query import is_valid_source_hostname

# A term can be a "Tier 1 supplier"-style multi-word phrase — 100 chars comfortably
# covers legitimate use while capping the cost/DB-bloat/prompt-injection surface a huge
# array of huge strings would otherwise open (see docs/v1-release-roadmap.html §5).
MAX_TERMS = 20
MAX_TERM_LENGTH = 100


def validate_term_list(value: list[str]) -> list[str]:
    if len(value) > MAX_TERMS:
        raise ValueError(f"at most {MAX_TERMS} terms are allowed")
    for term in value:
        if len(term) > MAX_TERM_LENGTH:
            raise ValueError(f"each term must be at most {MAX_TERM_LENGTH} characters")
    return value


def validate_source_allowlist(value: list[str]) -> list[str]:
    cleaned = [domain.strip().lower() for domain in value]
    for domain in cleaned:
        if not is_valid_source_hostname(domain):
            raise ValueError(f"{domain!r} is not a valid bare hostname (no scheme, no path)")
    return cleaned


def validate_news_sources(value: list[str] | None) -> list[str] | None:
    """Provider identifiers a theme (or the workspace default) may use. Validated against
    the ArticleSource enum so a typo fails loudly at the API boundary rather than silently
    matching no provider and leaving a topic fetching nothing."""
    if value is None:
        return None
    valid = {source.value for source in ArticleSource}
    cleaned = []
    for raw in value:
        source = raw.strip().lower()
        if source not in valid:
            raise ValueError(f"{raw!r} is not a known news source ({', '.join(sorted(valid))})")
        if source not in cleaned:
            cleaned.append(source)
    return cleaned


def validate_locale_code(value: str | None, *, upper: bool) -> str | None:
    """Normalizes a news-edition country (`gl`, uppercase) or language (`hl`, lowercase).

    Empty string means "inherit the workspace default", same as never having set one —
    normalized to None so the two spellings can't diverge in the DB. Shared by ThemeWatch
    and TargetCompany, which have identical edition-override semantics.
    """
    if value is None:
        return None
    value = value.strip().upper() if upper else value.strip().lower()
    if not value:
        return None
    # Language codes may be region-qualified ("pt-BR"); country codes never are.
    normalized = value if upper else value.replace("-", "")
    if not normalized.isalpha() or not 2 <= len(value) <= 8:
        label = "country code, e.g. DE or US" if upper else "language code, e.g. de or en"
        raise ValueError(f"Must be a 2-letter {label}")
    return value
