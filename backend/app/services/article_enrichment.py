"""Turns headline-only Google News rows into rows with real text behind them.

Two independent steps, each behind its own admin toggle and each entirely optional — every
failure here is swallowed and leaves the article exactly as it was (see
docs/google-news-quality-planning.html §9):

1. URL resolution: news.google.com/rss/articles/CBMi… → the publisher's own URL, stored in
   canonical_url. Makes cross-source dedupe possible (a Google redirect link never matches
   the same story's NewsAPI.org URL) and makes digest-email links durable.
2. Snippet enrichment: fetch the publisher page and lift its own description out of the
   metadata, so triage and summarization judge real text instead of a headline.

Deliberately metadata-only, not full article extraction: og:description and JSON-LD
description are what publishers *intend* to be shown by third parties, they're short
enough to send to Mistral without truncation games, and taking them needs no readability
heuristics that would silently degrade across site redesigns.
"""
import json
import logging
import re
from datetime import datetime, timezone

import httpx

from app.services.safe_fetch import UnsafeURLError, fetch_text, resolve_final_url

logger = logging.getLogger("newsatlas.article_enrichment")

GOOGLE_NEWS_HOST = "news.google.com"
# Publisher descriptions are a sentence or three. Anything longer is a page that put its
# whole lede in a meta tag, and there's no value in sending the rest to the model.
MAX_SNIPPET_CHARS = 1200

_META_PATTERNS = (
    # Attribute order varies by CMS, so match either arrangement rather than assuming one.
    re.compile(
        r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\'](?:og:description|description)["\']',
        re.IGNORECASE,
    ),
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def needs_url_resolution(url: str | None) -> bool:
    """Only Google News hands out redirect links; the other providers already return
    publisher URLs, so resolving theirs would be a pointless round trip."""
    return bool(url) and GOOGLE_NEWS_HOST in url


def resolve_article_url(url: str) -> str | None:
    """Publisher URL behind a Google News redirect, or None if it can't be resolved.

    None is a perfectly ordinary outcome — Google serves consent interstitials to some
    datacenter IPs — so callers keep the redirect URL and carry on."""
    try:
        resolved = resolve_final_url(url)
    except (UnsafeURLError, httpx.HTTPError) as exc:
        logger.info("Could not resolve Google News URL %s: %s", url, exc)
        return None
    if not resolved or GOOGLE_NEWS_HOST in resolved:
        # Still on Google: a consent wall or an interstitial, not the article.
        return None
    return resolved


def extract_description(html: str) -> str | None:
    """Publisher's own description from page metadata, preferring JSON-LD (structured,
    explicitly about the article) over og:description (sometimes a site-wide tagline)."""
    for raw in _JSON_LD_RE.findall(html):
        description = _description_from_json_ld(raw)
        if description:
            return description

    for pattern in _META_PATTERNS:
        match = pattern.search(html)
        if match and match.group(1).strip():
            return _clean(match.group(1))
    return None


def _description_from_json_ld(raw: str) -> str | None:
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    # A page may ship a list of blocks, or a @graph wrapper, or a single object.
    candidates = data if isinstance(data, list) else [data]
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        candidates = data["@graph"]

    for block in candidates:
        if not isinstance(block, dict):
            continue
        description = block.get("description")
        if isinstance(description, str) and description.strip():
            return _clean(description)
    return None


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:MAX_SNIPPET_CHARS]


def fetch_description(url: str) -> str | None:
    """Publisher description for `url`, or None when the page can't be fetched or carries
    no usable metadata. Never raises: enrichment is a bonus, not a dependency."""
    try:
        _final_url, html = fetch_text(url)
    except (UnsafeURLError, httpx.HTTPError) as exc:
        logger.info("Could not fetch article page %s: %s", url, exc)
        return None
    except Exception as exc:  # a malformed body must not take an ingestion run down
        logger.warning("Unexpected error fetching article page %s: %s", url, exc)
        return None
    return extract_description(html)


class EnrichmentBudget:
    """Per-run ceilings on enrichment work, so a slow publisher can't stretch an ingestion
    run indefinitely. Checked before each fetch rather than enforced by cancelling one in
    flight — a partially-enriched run is fine, a hung one isn't."""

    def __init__(self, max_fetches: int, max_seconds: float, clock=None):
        self.max_fetches = max_fetches
        self.max_seconds = max_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc).timestamp())
        self._started = self._clock()
        self._used = 0

    def consume(self) -> bool:
        """True if there's budget left for one more fetch (and claims it)."""
        if self.max_fetches > 0 and self._used >= self.max_fetches:
            return False
        if self.max_seconds > 0 and (self._clock() - self._started) >= self.max_seconds:
            return False
        self._used += 1
        return True


def enrich_articles(articles, workspace_settings, budget: EnrichmentBudget | None = None) -> None:
    """Resolves URLs and attaches snippets in place, honouring both toggles and the budget.

    Applied only to articles that already survived scoring and the per-run cap — enriching
    the whole raw result set would spend most of its fetches on candidates about to be
    discarded.
    """
    resolve_enabled = workspace_settings.google_news_resolve_urls_enabled
    snippets_enabled = workspace_settings.google_news_fetch_snippets_enabled
    if not resolve_enabled and not snippets_enabled:
        return

    for article in articles:
        if budget is not None and not budget.consume():
            return

        if resolve_enabled and needs_url_resolution(article.url) and not article.canonical_url:
            article.canonical_url = resolve_article_url(article.url)

        if not snippets_enabled:
            continue
        # Only rows with nothing better already: NewsData.io full content and NewsAPI.org
        # snippets are both preferable to a meta description, and re-fetching a page we've
        # already enriched is pure waste.
        if article.content_enriched or getattr(article, "full_content", None):
            continue
        target_url = article.canonical_url or article.url
        if GOOGLE_NEWS_HOST in target_url:
            # Unresolved redirect link — fetching it yields Google's page, not the article.
            continue

        description = fetch_description(target_url)
        if description:
            article.description = description
            article.content_enriched = True
