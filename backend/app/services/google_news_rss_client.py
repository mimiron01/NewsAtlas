import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import httpx

from app.services.news_client import FetchOutcome, NewsArticle, NewsClientError
from app.services.news_query import build_google_news_query, is_safe_article_url

_TAG_RE = re.compile(r"<[^>]+>")

# feedparser's default User-Agent is a well-known scraper signature and a throttling
# magnet. Identifying the application honestly is both politer and less likely to be
# rate-limited than pretending to be a browser.
USER_AGENT = "NewsAtlas/1.0 (+https://github.com/mimiron01/NewsAtlas) feed-reader"

# Google publishes no quota for this feed, so a 429 is a real possibility on a shared
# egress IP. One retry only: ingestion runs over every company in sequence, and a client
# that retries aggressively turns a transient throttle into a much longer outage.
MAX_RETRIES = 1
RETRY_BACKOFF_SECONDS = 2.0


class GoogleNewsRSSClient:
    """Wraps Google News' public RSS search feed (news.google.com/rss/search).

    Unlike NewsClient (NewsAPI.org) and NewsDataClient, this needs no API key — but Google
    also publishes no official supported API or quota for it, so callers are expected to
    rate-limit their own usage (see services/news_rate_limiter.py) rather than relying on
    the provider to enforce one.

    The HTTP request is made here with httpx rather than by feedparser, which is handed
    only the response bytes to parse. feedparser.parse(url) does its own fetch with no
    timeout parameter and no way to see the response status, which meant an unresponsive
    Google could hang a run indefinitely and a 429 was indistinguishable from "no news"
    (see docs/google-news-quality-planning.html findings F13/F14).
    """

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, country: str = "US", language: str = "en", timeout: float = 10.0):
        self.country = country
        self.language = language
        self.timeout = timeout

    def fetch_articles(
        self,
        *,
        name: str | None = None,
        keywords: list[str] | None = None,
        since: datetime,
        sources: list[str] | None = None,
        query_override: str | None = None,
        country: str | None = None,
        language: str | None = None,
        when: str | None = None,
    ) -> FetchOutcome:
        """Builds the query from name/keywords via build_google_news_query() as usual —
        unless query_override is given, in which case it's used verbatim. Theme ingestion
        (see docs/theme-search-planning.html §3) has no company name to anchor a query to,
        so it passes a pre-built query (build_theme_query()) here instead.

        country/language override this client's workspace-wide edition for a single call.
        Google News is edition-scoped: the same query against ceid=US:en and ceid=DE:de
        returns substantially different results, so a theme tracking a national market
        ("Startups DE") needs its own edition without forcing every other caller sharing
        this client instance onto it. Per-call rather than per-client so the instance (and
        its rate-limit accounting) stays shared across companies and themes alike.

        `when` is a pre-built Google time operator ("when:1d") appended to the query, so
        Google filters and — more importantly — re-ranks within the window server-side.
        Without it the feed's ~100-item budget is spent on all-time-relevant results and
        then mostly discarded here (see §6.2). Callers derive it with
        news_query.google_when_operator(); None keeps the old all-time behaviour.

        Returns a FetchOutcome rather than a bare list so the caller can log what was
        actually asked for and where the discarded entries went (§5.1).
        """
        if query_override is not None:
            query = query_override
        else:
            # Convenience path for direct callers; ingestion always passes a query built
            # from the company's split term roles. Bare keywords are treated as context
            # terms, the role they played before the split.
            query, _truncated = build_google_news_query(
                name=name or "", context_terms=keywords or [], allow_sites=sources
            )
        if when:
            query = f"{query} {when}"
        effective_country = country or self.country
        effective_language = language or self.language
        url = (
            f"{self.BASE_URL}?q={quote(query)}"
            f"&hl={quote(_display_language(effective_language, effective_country))}"
            f"&gl={quote(effective_country)}"
            f"&ceid={quote(f'{effective_country}:{effective_language}')}"
        )

        feed = self._parse_feed(url)

        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)

        articles: list[NewsArticle] = []
        drop_counts = {"stale": 0, "unsafe_url": 0}
        for entry in feed.entries:
            article = self._parse_entry(entry)
            if article is None:
                drop_counts["unsafe_url"] += 1
                continue
            # Belt and braces alongside the `when:` operator above: Google's buckets are
            # coarse (1h/12h/1d/7d) and it is not contractually obliged to honour them at
            # all, so `since` is still enforced exactly, here.
            if article.published_at is not None and article.published_at < since_utc:
                drop_counts["stale"] += 1
                continue
            articles.append(article)

        return FetchOutcome(
            articles=articles,
            requests_used=1,
            query_text=query,
            articles_raw=len(feed.entries),
            drop_counts=drop_counts,
        )

    def _parse_feed(self, url: str):
        """Fetches and parses, mapping every failure mode onto NewsClientError rather than
        onto an empty result — a throttled or broken fetch must never be silently
        indistinguishable from a company genuinely having no coverage."""
        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = httpx.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                last_error = f"Google News RSS request failed: {exc}"
            else:
                if response.status_code == 200:
                    return self._parse_body(response.content)
                # 429 (throttled) and 5xx (transient upstream) are the only statuses worth
                # a second attempt; a 4xx means the request itself is wrong and retrying
                # would just repeat it.
                if response.status_code != 429 and response.status_code < 500:
                    raise NewsClientError(
                        f"Google News RSS returned HTTP {response.status_code}"
                    )
                last_error = (
                    f"Google News RSS returned HTTP {response.status_code} "
                    "(throttled or upstream error, not an empty result)"
                )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)

        raise NewsClientError(last_error or "Google News RSS request failed")

    @staticmethod
    def _parse_body(body: bytes):
        try:
            feed = feedparser.parse(body)
        except Exception as exc:  # feedparser rarely raises, but never let a parse bug crash ingestion
            raise NewsClientError(f"Google News RSS request failed: {exc}") from exc

        # A 200 that isn't valid RSS is usually a consent interstitial or an error page
        # rendered as HTML — still a failed fetch, not an empty one. feedparser is lenient
        # enough to parse such a page without flagging `bozo`, so an empty result is only
        # trusted when what came back actually identified itself as a feed (`version`).
        if not feed.entries:
            if getattr(feed, "bozo", False):
                raise NewsClientError(
                    f"Google News RSS feed could not be parsed: {feed.get('bozo_exception')}"
                )
            if not getattr(feed, "version", ""):
                raise NewsClientError(
                    "Google News RSS returned a 200 that is not a feed "
                    "(usually a consent or error page, not an empty result)"
                )
        return feed

    @staticmethod
    def _parse_entry(entry: dict) -> NewsArticle | None:
        url = entry.get("link")
        if not is_safe_article_url(url):
            return None

        title = entry.get("title") or "(untitled)"

        # Google News RSS includes a proper <source> element on most entries; fall back to
        # parsing the "Headline - Source Name" title-suffix convention it also uses when
        # that element is missing.
        source_name = None
        source_obj = entry.get("source")
        if isinstance(source_obj, dict):
            source_name = source_obj.get("title")

        if source_name and title.endswith(f" - {source_name}"):
            title = title[: -(len(source_name) + 3)].strip()
        elif not source_name and " - " in title:
            title, _, suffix = title.rpartition(" - ")
            source_name = suffix.strip()
        source_name = source_name or "Unknown"

        description = entry.get("summary") or entry.get("description")
        if description:
            description = html.unescape(_TAG_RE.sub("", description)).strip() or None

        published_at = None
        parsed_time = entry.get("published_parsed")
        if parsed_time:
            try:
                published_at = datetime(*parsed_time[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published_at = None

        return NewsArticle(
            source_name=source_name,
            title=title or "(untitled)",
            url=url,
            description=description,
            published_at=published_at,
        )


def _display_language(language: str, country: str) -> str:
    """Google's documented canonical `hl` is a language-region tag ("de-DE"), not a bare
    language code. A bare code is accepted, but the canonical form is what Google's own
    URLs use, so build it when the caller gave a plain language and a country to pair it
    with. An already-regioned value ("pt-BR") is passed through untouched."""
    if "-" in language or not country:
        return language
    return f"{language}-{country}"
