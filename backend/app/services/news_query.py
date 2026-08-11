"""Shared helpers used by every news provider client (NewsClient, GoogleNewsRSSClient,
NewsDataClient) so the query-building and URL-safety logic lives in exactly one place
instead of being copied per provider.
"""
import math
import re
from datetime import datetime, timezone

# Google's search feed accepts hour and day granularities for its freshness operator.
# Anything longer than a week is clamped: the feed's own depth runs out around there, and
# a wider window just re-admits the stale results the operator exists to exclude.
_MAX_WHEN_DAYS = 7

# Google has historically capped queries at roughly 32 words and truncates past that
# silently. The schema validators allow far more input than that (20 keywords plus 50
# allowlist domains), so without an explicit budget a fully-populated configuration
# degrades invisibly. Conservative by one word: the exact limit is undocumented, and the
# cost of being one word under is nil while being one word over loses a clause.
MAX_QUERY_WORDS = 31

_WORD_RE = re.compile(r"\w+", re.UNICODE)
# Crude but language-agnostic stemming for the theme pre-filter: comparing the first few
# characters of a token collapses ordinary inflection ("battery"/"batteries",
# "Übernahme"/"Übernahmen") without a stemmer dependency or per-language rules. Short
# tokens are compared whole, so "EV" and "AI" don't collide with everything.
_STEM_PREFIX_LEN = 5


def _stem(token: str) -> str:
    return token[:_STEM_PREFIX_LEN]

_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def is_valid_source_hostname(value: str) -> bool:
    """True only for a bare domain (e.g. "nytimes.com") — no scheme, no path, no
    whitespace. Callers are expected to strip() before calling (as the settings/
    target-company schema validators do); this function itself is strict so a
    trailing space can't silently slip through. These values are spliced directly
    into a Google News RSS query string (site:{domain}) rather than fetched, so this
    guards query integrity, not SSRF — but malformed input shouldn't be allowed to
    break the constructed URL."""
    return bool(_HOSTNAME_RE.match(value))


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


def _quote_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    quoted: list[str] = []
    for term in terms:
        term = term.strip()
        if not term or term.lower() in seen:
            continue
        seen.add(term.lower())
        quoted.append(f'"{term}"' if " " in term else term)
    return quoted


def _or_group(terms: list[str]) -> str:
    """Parenthesized OR of already-quoted terms; a single term needs no group."""
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return f"({' OR '.join(terms)})"


def _count_words(query: str) -> int:
    """Google's query length limit is counted in words, and both quoted phrases and
    operators consume from the same budget, so count whitespace-separated tokens rather
    than characters."""
    return len(query.split())


def build_google_news_query(
    *,
    name: str,
    aliases: list[str] | None = None,
    context_terms: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    allow_sites: list[str] | None = None,
    deny_sites: list[str] | None = None,
    when: str | None = None,
    require_name_in_title: bool = False,
    max_words: int = MAX_QUERY_WORDS,
) -> tuple[str, bool]:
    """Builds a Google-News-RSS-specific query from a company's distinct term roles.

    Returns (query, truncated). `truncated` is True when the word budget forced terms to
    be dropped, so the caller can record it rather than let the query silently degrade —
    Google truncates over-long queries without saying so, which surfaces to a user only as
    "bad results" (docs/google-news-quality-planning.html finding F8).

    Terms are joined by implicit AND (a space) rather than the literal token `AND`: a bare
    space is unambiguously conjunction, Google's handling of the explicit keyword is
    documented as loose, and it saves a word against the budget on every query.

    Deliberately separate from build_or_query() above, which stays a flat OR-join for
    NewsAPI.org/NewsData.io.
    """
    identity = _quote_terms([name, *(aliases or [])])
    if require_name_in_title:
        # intitle: binds to the single following token, so a quoted multi-word phrase
        # keeps its quotes inside the operator.
        identity = [f"intitle:{term}" for term in identity]

    context = _quote_terms(context_terms or [])
    exclusions = [f"-{term}" for term in _quote_terms(exclude_terms or [])]
    allow = [f"site:{domain.strip()}" for domain in (allow_sites or []) if domain.strip()]
    deny = [f"-site:{domain.strip()}" for domain in (deny_sites or []) if domain.strip()]

    # Drop order when over budget, documented and tested: context terms first (they only
    # narrow), then allowlist domains. Identity terms, exclusions and the freshness
    # operator are never dropped — losing those changes what the query *means*, where
    # losing a narrower only widens it.
    truncated = False
    while True:
        parts = [p for p in [_or_group(identity)] if p]
        if context:
            parts.append(_or_group(context))
        parts.extend(exclusions)
        if allow:
            parts.append(_or_group(allow))
        parts.extend(deny)
        if when:
            parts.append(when)
        query = " ".join(parts)

        if _count_words(query) <= max_words:
            return query, truncated
        if context:
            context.pop()
            truncated = True
            continue
        if allow:
            allow.pop()
            truncated = True
            continue
        # Only identity/exclusions/when left — over budget but nothing droppable without
        # changing the query's meaning, so send it and let the caller see `truncated`.
        return query, True


def build_theme_query(
    query_terms: list[str],
    *,
    exclude_terms: list[str] | None = None,
    allow_sites: list[str] | None = None,
    deny_sites: list[str] | None = None,
    when: str | None = None,
    max_words: int = MAX_QUERY_WORDS,
) -> tuple[str, bool]:
    """Pure OR of a theme's own query terms — unlike build_google_news_query, there's no
    company name to require (see docs/theme-search-planning.html §3) — plus the same
    exclusion/allow/deny/freshness handling and word budget.

    A theme's terms are its identity *and* its topicality at once, so they're never
    dropped by the budget; allowlist domains are.
    """
    terms = _quote_terms(query_terms)
    exclusions = [f"-{term}" for term in _quote_terms(exclude_terms or [])]
    allow = [f"site:{domain.strip()}" for domain in (allow_sites or []) if domain.strip()]
    deny = [f"-site:{domain.strip()}" for domain in (deny_sites or []) if domain.strip()]

    truncated = False
    while True:
        parts = [p for p in [_or_group(terms)] if p]
        parts.extend(exclusions)
        if allow:
            parts.append(_or_group(allow))
        parts.extend(deny)
        if when:
            parts.append(when)
        query = " ".join(parts)

        if _count_words(query) <= max_words or not allow:
            return query, truncated or _count_words(query) > max_words
        allow.pop()
        truncated = True


def google_when_operator(since: datetime, now: datetime | None = None) -> str:
    """Smallest Google `when:` bucket that still covers everything back to `since`.

    Google News RSS is capped at ~100 items with no pagination and ranks by all-time
    relevance, so without a freshness operator that entire budget is spent on results the
    client-side `since` filter then discards — and genuinely recent coverage may never make
    the 100 at all (see docs/google-news-quality-planning.html §6.2). Buckets are always
    rounded *up* so the operator can only ever be more permissive than `since`, never less:
    the exact filter stays client-side, and this is purely a hint that makes Google rank
    within the right window.
    """
    now = now or datetime.now(timezone.utc)
    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    hours = max(1, math.ceil((now_utc - since_utc).total_seconds() / 3600))
    if hours <= 1:
        return "when:1h"
    if hours <= 12:
        return "when:12h"
    if hours <= 24:
        return "when:1d"
    return f"when:{min(math.ceil(hours / 24), _MAX_WHEN_DAYS)}d"


def is_safe_article_url(url: str | None) -> bool:
    """Only ever accept http(s) URLs — these get rendered as clickable links in the
    dashboard and in digest emails, so a javascript:/data: URL from a malicious or
    compromised upstream feed would otherwise be a stored-XSS vector."""
    return bool(url) and url.startswith(("http://", "https://"))


def article_mentions_company(
    *,
    title: str,
    description: str | None,
    full_content: str | None,
    name: str,
    aliases: list[str] | None = None,
) -> bool:
    """True if the company name or one of its aliases appears as a case-insensitive
    substring somewhere in the article's title/description/full_content.

    Providers' own search relevance is frequently loose/fuzzy (stemming, related-entity
    matches, etc.), so they can return an article that never actually contains any of the
    terms it was matched on. This is a cheap grounding guard against exactly that:
    articles that fail this check should never be attributed to the company (see
    docs/ingestion-reliability-planning.html §5).

    Identity terms ONLY. This used to accept any keyword, which meant an article
    containing a generic topic word ("Produktion") and never naming the company at all
    passed the guard and was stored under that company — the very failure the guard exists
    to prevent (docs/google-news-quality-planning.html finding F2). Context terms are
    topicality, not evidence of identity, and no longer count.
    """
    haystack = " ".join(filter(None, [title, description, full_content])).lower()
    for term in [name, *(aliases or [])]:
        term = term.strip()
        if term and term.lower() in haystack:
            return True
    return False


def article_matches_theme_terms(
    *, title: str, description: str | None, full_content: str | None, query_terms: list[str]
) -> bool:
    """The theme-path analogue of article_mentions_company: a theme's query terms are its
    relevance signal, so an article matching none of them was matched by provider fuzz
    rather than by the theme.

    A cheap pre-filter ahead of triage, not a replacement for it — triage still judges
    whether a genuinely on-topic article carries a business angle. Before this existed,
    LLM triage was the first filter anything on the theme path met, so the app paid tokens
    to reject articles a token check rejects for free (see
    docs/google-news-quality-planning.html §11.4).

    Matching is per-token and prefix-based rather than a verbatim substring test, unlike
    the company guard above. A theme term is a common noun phrase, so it inflects: a
    verbatim test rejects "EV batteries" for the term "EV battery", and in German
    (compounds, cases) it would reject far more than it kept. Comparing token stems keeps
    the check free and deterministic while surviving ordinary inflection. Adjacency is
    deliberately not required — this is a pre-filter whose job is to catch articles with
    no connection to the theme at all, and triage still has the final say.

    Identity is a different problem and keeps the stricter rule: see
    article_mentions_company, where a loose match means attributing a story to the wrong
    company.
    """
    haystack_stems = {
        _stem(token)
        for token in _WORD_RE.findall(" ".join(filter(None, [title, description, full_content])).lower())
    }
    for term in query_terms:
        term_tokens = _WORD_RE.findall(term.lower())
        if term_tokens and all(_stem(token) in haystack_stems for token in term_tokens):
            return True
    return False


def article_excluded_by_theme_terms(
    *, title: str, description: str | None, full_content: str | None, exclude_terms: list[str]
) -> bool:
    """True if the article's text contains one of the theme's exclude_terms.

    exclude_terms are sent to the provider as a `-term` query operator, but that's a
    request, not a guarantee: provider relevance/exclusion handling is the same
    "frequently loose/fuzzy" matching that motivates article_matches_theme_terms above, so
    an excluded term can still come back in the results. This is the client-side backstop
    — same per-token, stem-prefix matching as the positive-match check, so "layoffs" still
    excludes "layoff" and German compounds/cases still collapse the same way, but nothing
    that actually contains an excluded term is ever stored as a match.
    """
    haystack_stems = {
        _stem(token)
        for token in _WORD_RE.findall(" ".join(filter(None, [title, description, full_content])).lower())
    }
    for term in exclude_terms:
        term_tokens = _WORD_RE.findall(term.lower())
        if term_tokens and all(_stem(token) in haystack_stems for token in term_tokens):
            return True
    return False


def identity_terms(target_company) -> list[str]:
    """A company's name plus its aliases — the terms that establish identity, as opposed
    to context_terms which only establish topicality. Duck-typed so both ORM rows and
    lightweight preview payloads can be passed."""
    return [target_company.name, *(getattr(target_company, "aliases", None) or [])]


def resolve_allowlist(entity_allowlist: list[str] | None, workspace_allowlist: list[str]) -> list[str]:
    """Override semantics: NULL inherits the workspace default, [] means explicitly
    unrestricted, a non-empty list replaces the workspace list entirely.

    site: is a hard restriction rather than a preference, so the previous union semantics
    (v1 roadmap §2.3) meant a workspace allowlist silently hard-restricted every company
    and theme, with no way for one to narrow or opt out (see
    docs/google-news-quality-planning.html §7.6).
    """
    if entity_allowlist is None:
        return list(workspace_allowlist or [])
    return list(entity_allowlist)


def resolve_denylist(entity_denylist: list[str] | None, workspace_denylist: list[str]) -> list[str]:
    """Union, deliberately unlike resolve_allowlist: a denylist subtracts rather than
    restricts, "never accept this aggregator" is a workspace-wide policy an entity
    shouldn't be able to silently drop, and union fails safe — the worst case is slightly
    less coverage, whereas a dropped denylist entry reintroduces the exact noise it was
    added to remove."""
    return list(dict.fromkeys([*(workspace_denylist or []), *(entity_denylist or [])]))
