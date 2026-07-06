from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.services.news_client import NewsArticle, NewsClientError
from app.services.news_query import build_or_query, is_safe_article_url

# NewsData.io charges roughly one credit per API call regardless of how many articles
# it returns, so this bounds credit spend from a single busy company per call — a bound
# on top of, not instead of, the workspace-level rate limit in services/news_rate_limiter.py.
MAX_PAGES_PER_CALL = 2

_UNAVAILABLE_MARKERS = ("ONLY AVAILABLE IN PAID PLANS", "NOT AVAILABLE")


@dataclass
class NewsDataArticle(NewsArticle):
    # Populated only when the full-content option is requested and the account's plan
    # tier includes it; otherwise NewsData.io returns a placeholder string we filter out.
    full_content: str | None = None
    # NewsData.io's own sentiment/AI-tag output — read defensively since both are only
    # present when the account's plan/add-ons include them.
    sentiment: str | None = None
    tags: list[str] | None = None


class NewsDataClient:
    """Wraps NewsData.io's paid /news (latest) and /archive (historical) endpoints.

    Unlike NewsClient/GoogleNewsRSSClient, this leans into paid-tier-only features when
    the workspace has them enabled: full article content (better-grounded summarization
    than a snippet), native duplicate-content removal, and native sentiment/AI tags.
    """

    BASE_URL = "https://newsdata.io/api/1"

    def __init__(self, api_key: str, timeout: float = 15.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch_articles(
        self,
        *,
        name: str,
        keywords: list[str],
        since: datetime,
        full_content: bool = False,
        use_native_dedupe: bool = True,
    ) -> tuple[list[NewsDataArticle], int]:
        """Returns (articles, requests_used) — requests_used is the number of API pages
        actually fetched (NewsData.io charges roughly one credit per call), for the caller
        to log to NewsSourceUsageLog."""
        params = self._base_params(name, keywords, full_content=full_content, use_native_dedupe=use_native_dedupe)
        params["from_date"] = since.strftime("%Y-%m-%d")
        return self._paginate(f"{self.BASE_URL}/news", params)

    def fetch_archive(
        self,
        *,
        name: str,
        keywords: list[str],
        since: datetime,
        until: datetime,
        full_content: bool = False,
        use_native_dedupe: bool = True,
    ) -> tuple[list[NewsDataArticle], int]:
        """Historical coverage via the paid-only /archive endpoint, used solely by the
        one-time backfill workflow (services/newsdata_backfill.py) — not the routine
        polling loop."""
        params = self._base_params(name, keywords, full_content=full_content, use_native_dedupe=use_native_dedupe)
        params["from_date"] = since.strftime("%Y-%m-%d")
        params["to_date"] = until.strftime("%Y-%m-%d")
        return self._paginate(f"{self.BASE_URL}/archive", params)

    def _base_params(
        self, name: str, keywords: list[str], *, full_content: bool, use_native_dedupe: bool
    ) -> dict:
        if not self.api_key:
            raise NewsClientError("NEWSDATA_API_KEY is not configured")
        params: dict = {
            "q": build_or_query(name, keywords),
            "apikey": self.api_key,
            "language": "en",
        }
        if use_native_dedupe:
            params["removeduplicate"] = 1
        if full_content:
            params["full_content"] = 1
        return params

    def _paginate(self, url: str, params: dict) -> tuple[list[NewsDataArticle], int]:
        articles: list[NewsDataArticle] = []
        requests_used = 0
        next_page: str | None = None

        for _ in range(MAX_PAGES_PER_CALL):
            page_params = dict(params)
            if next_page:
                page_params["page"] = next_page
            try:
                response = httpx.get(url, params=page_params, timeout=self.timeout)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise NewsClientError(f"NewsData.io request failed: {exc}") from exc
            requests_used += 1

            payload = response.json()
            if payload.get("status") != "success":
                raise NewsClientError(f"NewsData.io error: {payload.get('message', 'unknown error')}")

            for item in payload.get("results", []) or []:
                article = self._parse_article(item)
                if article is not None:
                    articles.append(article)

            next_page = payload.get("nextPage")
            if not next_page:
                break

        return articles, requests_used

    @staticmethod
    def _parse_article(item: dict) -> NewsDataArticle | None:
        url = item.get("link")
        if not is_safe_article_url(url):
            return None

        published_at = None
        raw_published_at = item.get("pubDate")
        if raw_published_at:
            try:
                published_at = datetime.strptime(raw_published_at, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                published_at = None

        return NewsDataArticle(
            source_name=item.get("source_name") or item.get("source_id") or "Unknown",
            title=item.get("title") or "(untitled)",
            url=url,
            description=item.get("description"),
            published_at=published_at,
            full_content=_clean_gated_field(item.get("content")),
            sentiment=_clean_gated_field(item.get("sentiment")),
            tags=_parse_tags(item.get("ai_tag")),
        )


def _clean_gated_field(value: str | None) -> str | None:
    """NewsData.io returns a placeholder string (not null) for fields gated to a higher
    plan tier than the account has — treat those the same as "not present" rather than
    storing the placeholder text as if it were real content."""
    if not value or value.strip().upper() in _UNAVAILABLE_MARKERS:
        return None
    return value


def _parse_tags(raw_tags) -> list[str] | None:
    if isinstance(raw_tags, list):
        return raw_tags or None
    if isinstance(raw_tags, str):
        cleaned = _clean_gated_field(raw_tags)
        if not cleaned:
            return None
        return [tag.strip() for tag in cleaned.split(",") if tag.strip()] or None
    return None
