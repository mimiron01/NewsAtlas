from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.services.news_query import build_or_query, is_safe_article_url


class NewsClientError(Exception):
    """Raised when the news provider can't be reached or returns an error."""


@dataclass
class NewsArticle:
    source_name: str
    title: str
    url: str
    description: str | None
    published_at: datetime | None


@dataclass
class FetchOutcome:
    """What a provider call produced, including the Phase 0 funnel diagnostics (see
    docs/google-news-quality-planning.html §5.1).

    Only Google News RSS currently filters anything client-side — the other two providers
    filter by date server-side and so have nothing to report beyond the article list — but
    every provider is normalized into this shape by ingestion's dispatcher, so the usage
    log has one code path instead of a per-provider special case.
    """

    articles: list[NewsArticle] = field(default_factory=list)
    # NewsData.io reports a real per-call credit cost; the others cost exactly one.
    requests_used: int = 1
    # The query actually sent, pre-encoding. None for providers that don't build one.
    query_text: str | None = None
    # Entries returned before any client-side filtering.
    articles_raw: int = 0
    # Per-stage discard counts, e.g. {"stale": 41, "unsafe_url": 2}.
    drop_counts: dict[str, int] = field(default_factory=dict)


class NewsClient:
    """Thin wrapper around NewsAPI.org's /v2/everything endpoint.

    Kept provider-specific logic isolated here so a different news source
    can be swapped in later without touching the ingestion orchestration.
    """

    BASE_URL = "https://newsapi.org/v2/everything"

    # NewsAPI.org bills per request, not per article, so asking for fewer than the
    # documented maximum buys nothing and just hands the candidate scorer
    # (services/article_scoring.py) an arbitrarily truncated pool to choose from.
    PAGE_SIZE = 100

    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch_articles(
        self,
        *,
        name: str,
        keywords: list[str],
        since: datetime,
        language: str = "en",
        query_override: str | None = None,
    ) -> list[NewsArticle]:
        """language was hardcoded to "en" until docs/google-news-quality-planning.html §6.4
        (finding F16): a workspace targeting a non-English market could not get
        native-language coverage from this provider at all, which is noise by construction
        rather than a tuning problem.

        query_override is used by theme ingestion, which has no company name to anchor a
        query to — same convention as GoogleNewsRSSClient (see §11.5).
        """
        if not self.api_key:
            raise NewsClientError("NEWSAPI_API_KEY is not configured")

        params = {
            "q": query_override if query_override is not None else self._build_query(name, keywords),
            "from": since.strftime("%Y-%m-%dT%H:%M:%S"),
            "sortBy": "publishedAt",
            "language": language,
            "pageSize": self.PAGE_SIZE,
            "apiKey": self.api_key,
        }
        try:
            response = httpx.get(self.BASE_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NewsClientError(f"NewsAPI request failed: {exc}") from exc

        payload = response.json()
        if payload.get("status") != "ok":
            raise NewsClientError(f"NewsAPI error: {payload.get('message', 'unknown error')}")

        return [
            article
            for item in payload.get("articles", [])
            if (article := self._parse_article(item)) is not None
        ]

    @staticmethod
    def _parse_article(item: dict) -> NewsArticle | None:
        url = item.get("url")
        if not is_safe_article_url(url):
            return None

        published_at = None
        raw_published_at = item.get("publishedAt")
        if raw_published_at:
            try:
                published_at = datetime.fromisoformat(raw_published_at.replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        return NewsArticle(
            source_name=(item.get("source") or {}).get("name") or "Unknown",
            title=item.get("title") or "(untitled)",
            url=url,
            description=item.get("description"),
            published_at=published_at,
        )

    @staticmethod
    def _build_query(name: str, keywords: list[str]) -> str:
        return build_or_query(name, keywords)
