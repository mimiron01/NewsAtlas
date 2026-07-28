import html
import re
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser

from app.services.news_client import NewsArticle, NewsClientError
from app.services.news_query import build_google_news_query, is_safe_article_url

_TAG_RE = re.compile(r"<[^>]+>")


class GoogleNewsRSSClient:
    """Wraps Google News' public RSS search feed (news.google.com/rss/search).

    Unlike NewsClient (NewsAPI.org) and NewsDataClient, this needs no API key — but Google
    also publishes no official supported API or quota for it, so callers are expected to
    rate-limit their own usage (see services/news_rate_limiter.py) rather than relying on
    the provider to enforce one.
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
    ) -> list[NewsArticle]:
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
        """
        if query_override is not None:
            query = query_override
        else:
            query = build_google_news_query(name or "", keywords or [], sources)
        effective_country = country or self.country
        effective_language = language or self.language
        ceid = f"{effective_country}:{effective_language}"
        url = (
            f"{self.BASE_URL}?q={quote(query)}&hl={effective_language}"
            f"&gl={effective_country}&ceid={quote(ceid)}"
        )

        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # feedparser rarely raises, but never let a parse bug crash ingestion
            raise NewsClientError(f"Google News RSS request failed: {exc}") from exc

        if getattr(feed, "bozo", False) and not feed.entries:
            raise NewsClientError(
                f"Google News RSS feed could not be parsed: {feed.get('bozo_exception')}"
            )

        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)

        articles: list[NewsArticle] = []
        for entry in feed.entries:
            article = self._parse_entry(entry)
            if article is None:
                continue
            # No server-side date filter on this feed, so entries older than `since` are
            # dropped client-side after parsing.
            if article.published_at is not None and article.published_at < since_utc:
                continue
            articles.append(article)
        return articles

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
