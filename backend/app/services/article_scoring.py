"""Free, deterministic candidate ranking and near-duplicate collapse, applied before any
Mistral call is made (see docs/google-news-quality-planning.html §8).

Two jobs, both purely local — no AI, no network, no new dependencies:

1. `score_candidate` / `rank_candidates` decide *which* candidates are worth the
   embedding + triage + summarization budget when there are more than the per-run cap
   allows. This replaces a plain newest-first sort, which on a syndication-heavy,
   relevance-ranked feed systematically preferred aggregator reposts over the original.
2. `collapse_near_duplicate_titles` removes obvious syndicated repeats *before* the
   embedding call, so the semantic dedupe that follows isn't paying to rediscover them.

The weights below are a starting point to be tuned against the Phase 0 funnel data, not
constants derived from anything principled. They are kept in one table so tuning is a
single-file change with a test to match.
"""
import re
from datetime import datetime, timezone
from typing import Callable, Iterable, TypeVar
from urllib.parse import urlparse

T = TypeVar("T")

# --- Scoring weights (see module docstring — provisional, tune against real data) ---
IDENTITY_IN_TITLE = 3.0
IDENTITY_IN_DESCRIPTION = 1.0
ALLOWLISTED_DOMAIN = 2.0
FRESH_HALF_OF_WINDOW = 2.0
CONTEXT_TERM_PRESENT = 1.0
# Applied per article beyond SAME_DOMAIN_FREE_SLOTS from the same domain in one run, so a
# single prolific outlet can't consume the whole per-company budget.
SAME_DOMAIN_PENALTY = 2.0
SAME_DOMAIN_FREE_SLOTS = 3

# Two headlines whose word sets overlap this much are treated as the same story. Set high
# deliberately: a false merge silently hides a real story, which is a worse failure than
# paying for one extra embedding.
TITLE_SIMILARITY_THRESHOLD = 0.85

_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
# Trailing " - Outlet Name" / " | Outlet Name" attribution that publishers and aggregators
# append inconsistently to the same headline.
_TITLE_SUFFIX_RE = re.compile(r"\s+[-|–—]\s+[^-|–—]{1,40}$")


def normalize_title(title: str) -> str:
    """Lowercased, punctuation-stripped, attribution-suffix-stripped form used for
    near-duplicate comparison."""
    text = _TITLE_SUFFIX_RE.sub("", title.strip())
    return _WORD_RE.sub(" ", text).lower().strip()


def title_similarity(left: str, right: str) -> float:
    """Jaccard similarity over word sets. Deliberately not a sequence/edit distance:
    syndicated copies reorder and re-punctuate headlines far more often than they change
    the words in them, and a set comparison is both cheaper and more robust to that."""
    left_words = set(normalize_title(left).split())
    right_words = set(normalize_title(right).split())
    if not left_words or not right_words:
        return 0.0
    intersection = len(left_words & right_words)
    union = len(left_words | right_words)
    return intersection / union if union else 0.0


def article_domain(url: str | None) -> str:
    """Registrable-ish host for grouping and allowlist comparison. Not a public-suffix
    parse — `www.` stripping is enough for the counting and matching done here, and a
    real PSL dependency would buy nothing for either."""
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _contains_any(haystack: str, terms: Iterable[str]) -> bool:
    lowered = haystack.lower()
    return any(term.strip() and term.strip().lower() in lowered for term in terms)


def score_candidate(
    article,
    *,
    identity_terms: list[str],
    context_terms: list[str] | None = None,
    allowlist: list[str] | None = None,
    since: datetime | None = None,
    now: datetime | None = None,
    domain_seen_count: int = 0,
) -> float:
    """Higher is better. Duck-typed on .title/.description/.url/.published_at so it works
    for both raw provider results and persisted Article rows."""
    score = 0.0
    title = getattr(article, "title", "") or ""
    description = getattr(article, "description", None) or ""

    if _contains_any(title, identity_terms):
        score += IDENTITY_IN_TITLE
    elif _contains_any(description, identity_terms):
        score += IDENTITY_IN_DESCRIPTION

    if context_terms and _contains_any(f"{title} {description}", context_terms):
        score += CONTEXT_TERM_PRESENT

    if allowlist:
        domain = article_domain(getattr(article, "url", None))
        if domain and any(domain == d.lower() or domain.endswith(f".{d.lower()}") for d in allowlist):
            score += ALLOWLISTED_DOMAIN

    published_at = getattr(article, "published_at", None)
    if published_at is not None and since is not None:
        now = now or datetime.now(timezone.utc)
        published = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        midpoint = since_utc + (now - since_utc) / 2
        if published >= midpoint:
            score += FRESH_HALF_OF_WINDOW

    if domain_seen_count >= SAME_DOMAIN_FREE_SLOTS:
        score -= SAME_DOMAIN_PENALTY

    return score


def rank_candidates(
    items: list[T],
    *,
    article_of: Callable[[T], object],
    identity_terms: list[str],
    context_terms: list[str] | None = None,
    allowlist: list[str] | None = None,
    since: datetime | None = None,
    now: datetime | None = None,
) -> list[T]:
    """Best-first ordering. The same-domain penalty is applied in a first pass over the
    items in their original (provider-ranked) order, so which copies get penalized is
    stable rather than dependent on the sort it feeds."""
    now = now or datetime.now(timezone.utc)
    domain_counts: dict[str, int] = {}
    scored: list[tuple[float, datetime, int, T]] = []

    for position, item in enumerate(items):
        article = article_of(item)
        domain = article_domain(getattr(article, "url", None))
        seen = domain_counts.get(domain, 0)
        domain_counts[domain] = seen + 1
        published_at = getattr(article, "published_at", None) or datetime.min.replace(
            tzinfo=timezone.utc
        )
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        scored.append(
            (
                score_candidate(
                    article,
                    identity_terms=identity_terms,
                    context_terms=context_terms,
                    allowlist=allowlist,
                    since=since,
                    now=now,
                    domain_seen_count=seen,
                ),
                published_at,
                # Final tiebreak on original position keeps the ordering total and stable,
                # so a run over identical inputs always produces an identical selection.
                -position,
                item,
            )
        )

    scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    return [row[3] for row in scored]


def collapse_near_duplicate_titles(
    items: list[T],
    *,
    key: Callable[[T], str],
    score: Callable[[T], float] | None = None,
) -> tuple[list[T], list[T]]:
    """Splits items into (kept, dropped) by near-identical title.

    Within each cluster the highest-scoring member is kept (falling back to the first
    occurrence when no scorer is given), because the best copy of a syndicated story is
    rarely the first one a provider happened to return.
    """
    kept: list[T] = []
    dropped: list[T] = []
    # (representative title, index into `kept`) per cluster.
    clusters: list[tuple[str, int]] = []

    for item in items:
        title = key(item)
        matched_index = None
        for cluster_title, kept_index in clusters:
            if title_similarity(title, cluster_title) >= TITLE_SIMILARITY_THRESHOLD:
                matched_index = kept_index
                break

        if matched_index is None:
            clusters.append((title, len(kept)))
            kept.append(item)
            continue

        if score is not None and score(item) > score(kept[matched_index]):
            # Newcomer is the better copy: it takes the slot, the incumbent is dropped.
            dropped.append(kept[matched_index])
            kept[matched_index] = item
        else:
            dropped.append(item)

    return kept, dropped
