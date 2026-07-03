from dataclasses import dataclass
from datetime import datetime

import httpx


class NewsClientError(Exception):
    """Raised when the news provider can't be reached or returns an error."""


@dataclass
class NewsArticle:
    source_name: str
    title: str
    url: str
    description: str | None
    published_at: datetime | None


class NewsClient:
    """Thin wrapper around NewsAPI.org's /v2/everything endpoint.

    Kept provider-specific logic isolated here so a different news source
    can be swapped in later without touching the ingestion orchestration.
    """

    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch_articles(self, *, name: str, keywords: list[str], since: datetime) -> list[NewsArticle]:
        if not self.api_key:
            raise NewsClientError("NEWSAPI_API_KEY is not configured")

        params = {
            "q": self._build_query(name, keywords),
            "from": since.strftime("%Y-%m-%dT%H:%M:%S"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 20,
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
        # Only ever store http(s) URLs — this is rendered as a clickable link in the
        # dashboard and in digest emails, so a javascript:/data: URL here would be a
        # stored-XSS vector if the upstream feed is ever malicious or compromised.
        if not url or not url.startswith(("http://", "https://")):
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
