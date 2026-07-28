"""Validators shared across schemas that have a "list of short strings" field spliced
into a news-provider query (TargetCompany.keywords, ThemeWatch.query_terms) or a
Google News site: allowlist (TargetCompany/ThemeWatch/WorkspaceSettings
.google_news_source_allowlist) — kept in one place so the v1 roadmap's length/hostname
caps (§5) apply identically everywhere rather than being re-specified per schema.
"""
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
