from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.article import Article
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.ingestion import IngestionRunResult
from app.services.ai_client import AIClient, AIClientError
from app.services.news_client import NewsClient, NewsClientError

MIN_LOOKBACK_HOURS = 24


def _get_or_create_workspace_settings(db: Session) -> WorkspaceSettings:
    settings = db.query(WorkspaceSettings).first()
    if settings is None:
        settings = WorkspaceSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def run_ingestion(
    db: Session,
    news_client: NewsClient | None = None,
    ai_client: AIClient | None = None,
) -> IngestionRunResult:
    app_settings = get_settings()
    workspace_settings = _get_or_create_workspace_settings(db)

    news_client = news_client or NewsClient(api_key=app_settings.newsapi_api_key)
    ai_client = ai_client or AIClient(
        api_key=app_settings.mistral_api_key, model=app_settings.mistral_model
    )

    lookback_hours = max(workspace_settings.ingestion_interval_hours * 2, MIN_LOOKBACK_HOURS)
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    target_companies = db.query(TargetCompany).filter(TargetCompany.is_active.is_(True)).all()

    articles_fetched = 0
    articles_new = 0
    signals_created = 0
    errors: list[str] = []

    for target_company in target_companies:
        try:
            fetched_articles = news_client.fetch_articles(
                name=target_company.name, keywords=target_company.keywords, since=since
            )
        except NewsClientError as exc:
            errors.append(f"[{target_company.name}] news fetch failed: {exc}")
            continue

        articles_fetched += len(fetched_articles)

        for fetched in fetched_articles:
            existing = db.query(Article).filter(Article.url == fetched.url).first()
            if existing is not None:
                continue

            article = Article(
                target_company_id=target_company.id,
                source_name=fetched.source_name,
                title=fetched.title,
                url=fetched.url,
                description=fetched.description,
                published_at=fetched.published_at,
            )
            db.add(article)
            db.commit()
            db.refresh(article)
            articles_new += 1

            try:
                result = ai_client.summarize_article(
                    company_name=workspace_settings.company_name,
                    offering_description=workspace_settings.offering_description,
                    target_company_name=target_company.name,
                    article_title=article.title,
                    article_description=article.description,
                )
            except AIClientError as exc:
                errors.append(f"[{target_company.name}] summarization failed for {article.url}: {exc}")
                continue

            signal = Signal(
                article_id=article.id,
                summary=result.summary,
                business_relevance=result.business_relevance,
                outreach_snippet=result.outreach_snippet,
            )
            db.add(signal)
            db.commit()
            signals_created += 1

    return IngestionRunResult(
        target_companies_processed=len(target_companies),
        articles_fetched=articles_fetched,
        articles_new=articles_new,
        signals_created=signals_created,
        errors=errors,
    )
