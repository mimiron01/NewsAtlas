import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.article import Article, ArticleSource
from app.models.target_company import TargetCompany
from app.services.ai_client import AIClient
from app.services.ingestion import _process_new_articles
from app.services.news_client import NewsClientError
from app.services.news_query import article_mentions_company
from app.services.news_rate_limiter import has_headroom
from app.services.news_usage import log_rate_limited
from app.services.news_usage import log_usage as log_news_usage
from app.services.newsdata_client import NewsDataClient
from app.services.workspace_settings import (
    get_or_create_workspace_settings,
    resolve_mistral_api_key,
    resolve_newsdata_api_key,
)


def run_backfill_for_company(
    db: Session,
    target_company_id: uuid.UUID,
    *,
    newsdata_client: NewsDataClient | None = None,
    ai_client: AIClient | None = None,
) -> bool:
    """One-time NewsData.io historical archive pull for a single target company (see
    docs/news-source-expansion-planning.html §10.4). Feeds results through the exact
    same insertion + dedupe/triage/summarize path as routine ingestion.

    Returns True if the backfill actually ran (a request was made to NewsData.io),
    False if it was skipped (disabled, already done, or rate-limited) — callers that
    invoke this from a background task after the request session has closed must pass
    a freshly opened session, not the request-scoped one (see api/target_companies.py).
    """
    target_company = db.get(TargetCompany, target_company_id)
    if target_company is None or target_company.backfilled_at is not None:
        return False

    app_settings = get_settings()
    workspace_settings = get_or_create_workspace_settings(db)
    if not workspace_settings.newsdata_enabled or workspace_settings.newsdata_backfill_days <= 0:
        return False

    if not has_headroom(
        db,
        ArticleSource.NEWSDATA,
        per_minute_limit=workspace_settings.newsdata_max_requests_per_minute,
        per_day_limit=workspace_settings.newsdata_max_requests_per_day,
    ):
        log_rate_limited(db, source=ArticleSource.NEWSDATA, target_company_id=target_company.id)
        return False

    client = newsdata_client or NewsDataClient(
        api_key=resolve_newsdata_api_key(workspace_settings, app_settings)
    )
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=workspace_settings.newsdata_backfill_days)

    try:
        fetched, requests_used = client.fetch_archive(
            name=target_company.name,
            keywords=target_company.keywords,
            since=since,
            until=now,
            full_content=workspace_settings.newsdata_full_content_enabled,
            use_native_dedupe=workspace_settings.newsdata_use_native_dedupe,
        )
    except NewsClientError:
        # Transient failure (bad key, outage) — leave backfilled_at unset so a later
        # manual retry or reactivation can still succeed, rather than permanently
        # burning the one-time backfill attempt on a fixable error.
        return False

    log_news_usage(
        db,
        source=ArticleSource.NEWSDATA,
        call_type="archive",
        target_company_id=target_company.id,
        requests_used=requests_used,
        articles_returned=len(fetched),
    )

    new_articles: list[Article] = []
    seen_urls: set[str] = set()
    for item in fetched:
        # Same grounding guard as routine ingestion (services/ingestion.py) — the
        # archive endpoint uses the same loose OR query, so it's just as prone to
        # returning an article that never actually mentions the company.
        if not article_mentions_company(
            title=item.title,
            description=item.description,
            full_content=getattr(item, "full_content", None),
            name=target_company.name,
            keywords=target_company.keywords,
        ):
            continue
        if item.url in seen_urls:
            continue
        if db.query(Article).filter(Article.url == item.url).first() is not None:
            continue
        seen_urls.add(item.url)
        article = Article(
            target_company_id=target_company.id,
            source=ArticleSource.NEWSDATA,
            source_name=item.source_name,
            title=item.title,
            url=item.url,
            description=item.description,
            published_at=item.published_at,
            full_content=getattr(item, "full_content", None),
            external_sentiment=getattr(item, "sentiment", None),
            external_tags=getattr(item, "tags", None),
        )
        db.add(article)
        new_articles.append(article)

    target_company.backfilled_at = now
    db.commit()

    if new_articles:
        resolved_ai_client = ai_client or AIClient(
            api_key=resolve_mistral_api_key(workspace_settings, app_settings),
            model=workspace_settings.mistral_model,
            triage_model=workspace_settings.mistral_triage_model,
            embed_model=workspace_settings.mistral_embed_model,
        )
        _process_new_articles(
            db,
            ai_client=resolved_ai_client,
            workspace_settings=workspace_settings,
            target_company=target_company,
            new_articles=new_articles,
        )

    return True
