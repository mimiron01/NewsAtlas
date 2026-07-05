from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_usage_log import AIUsageLog
from app.models.article import Article
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.schemas.ingestion import IngestionRunResult
from app.services.ai_client import AIClient, AIClientError, MistralUsage
from app.services.feedback import refresh_feedback_note
from app.services.news_client import NewsClient, NewsClientError
from app.services.workspace_settings import get_or_create_workspace_settings

MIN_LOOKBACK_HOURS = 24
RECENT_SIGNALS_FOR_CONTEXT = 2
RECENT_ARTICLES_FOR_DEDUPE = 50
SUMMARY_CONTEXT_TRUNCATE = 160


def run_ingestion(
    db: Session,
    news_client: NewsClient | None = None,
    ai_client: AIClient | None = None,
) -> IngestionRunResult:
    app_settings = get_settings()
    workspace_settings = get_or_create_workspace_settings(db)
    refresh_feedback_note(db, workspace_settings)

    news_client = news_client or NewsClient(api_key=app_settings.newsapi_api_key)
    ai_client = ai_client or AIClient(
        api_key=app_settings.mistral_api_key,
        model=app_settings.mistral_model,
        triage_model=app_settings.mistral_triage_model,
        embed_model=app_settings.mistral_embed_model,
    )

    lookback_hours = max(workspace_settings.ingestion_interval_hours * 2, MIN_LOOKBACK_HOURS)
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    target_companies = db.query(TargetCompany).filter(TargetCompany.is_active.is_(True)).all()

    articles_fetched = 0
    articles_new = 0
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0
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

        new_articles: list[Article] = []
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
            new_articles.append(article)

        if not new_articles:
            continue

        db.commit()
        for article in new_articles:
            db.refresh(article)
        articles_new += len(new_articles)

        signals_created_here, duplicates_here, triaged_out_here, batch_errors = _process_new_articles(
            db,
            ai_client=ai_client,
            app_settings=app_settings,
            workspace_settings=workspace_settings,
            target_company=target_company,
            new_articles=new_articles,
        )
        signals_created += signals_created_here
        duplicates_skipped += duplicates_here
        triaged_out += triaged_out_here
        errors.extend(batch_errors)

    return IngestionRunResult(
        target_companies_processed=len(target_companies),
        articles_fetched=articles_fetched,
        articles_new=articles_new,
        signals_created=signals_created,
        duplicates_skipped=duplicates_skipped,
        triaged_out=triaged_out,
        errors=errors,
    )


def _process_new_articles(
    db: Session,
    *,
    ai_client: AIClient,
    app_settings,
    workspace_settings,
    target_company: TargetCompany,
    new_articles: list[Article],
) -> tuple[int, int, int, list[str]]:
    errors: list[str] = []
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0

    # One embeddings request for every new article in this batch, instead of one call
    # per article — the main lever for keeping dedupe cheap at scale.
    try:
        embed_inputs = [f"{a.title}\n{a.description or ''}" for a in new_articles]
        vectors, embed_usage = ai_client.embed_texts(embed_inputs)
        _log_usage(db, "embedding", ai_client.embed_model, embed_usage, target_company.id)
        for article, vector in zip(new_articles, vectors):
            article.embedding = vector
        db.commit()
    except AIClientError as exc:
        errors.append(f"[{target_company.name}] embedding failed: {exc}")

    new_article_ids = {a.id for a in new_articles}
    candidates = (
        db.query(Article)
        .filter(
            Article.target_company_id == target_company.id,
            Article.embedding.isnot(None),
            ~Article.id.in_(new_article_ids),
        )
        .order_by(Article.fetched_at.desc())
        .limit(RECENT_ARTICLES_FOR_DEDUPE)
        .all()
    )

    for article in new_articles:
        if article.embedding is not None:
            duplicate = _find_duplicate(
                article, candidates, app_settings.mistral_dedupe_similarity_threshold
            )
            if duplicate is not None:
                article.duplicate_of_article_id = duplicate.id
                article.skip_reason = "duplicate"
                db.commit()
                duplicates_skipped += 1
                continue
            candidates.insert(0, article)

        if app_settings.mistral_triage_enabled:
            try:
                triage, triage_usage = ai_client.triage_article(
                    company_name=workspace_settings.company_name,
                    offering_description=workspace_settings.offering_description,
                    target_company_name=target_company.name,
                    article_title=article.title,
                    article_description=article.description,
                )
                _log_usage(db, "triage", ai_client.triage_model, triage_usage, target_company.id)
            except AIClientError as exc:
                errors.append(f"[{target_company.name}] triage failed for {article.url}: {exc}")
                triage = None
            if triage is not None and not triage.relevant:
                article.skip_reason = "triaged_out"
                db.commit()
                triaged_out += 1
                continue

        recent_signals = _recent_signal_context(db, target_company.id)

        try:
            result, usage = ai_client.summarize_article(
                company_name=workspace_settings.company_name,
                offering_description=workspace_settings.offering_description,
                target_company_name=target_company.name,
                article_title=article.title,
                article_description=article.description,
                industry=target_company.industry,
                recent_signals=recent_signals,
                feedback_note=workspace_settings.ai_feedback_note,
            )
            _log_usage(db, "summarize", ai_client.model, usage, target_company.id)
        except AIClientError as exc:
            article.skip_reason = "ai_error"
            db.commit()
            errors.append(f"[{target_company.name}] summarization failed for {article.url}: {exc}")
            continue

        signal = Signal(
            article_id=article.id,
            summary=result.summary,
            business_relevance=result.business_relevance,
            supporting_quote=result.supporting_quote,
            outreach_snippet_email=result.outreach_snippet_email,
            outreach_snippet_linkedin=result.outreach_snippet_linkedin,
            outreach_call_opener=result.outreach_call_opener,
            relevance_score=result.relevance_score,
            signal_type=result.signal_type,
            confidence=result.confidence,
            entities=result.entities,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
        db.add(signal)
        db.commit()
        signals_created += 1

    return signals_created, duplicates_skipped, triaged_out, errors


def _log_usage(
    db: Session, call_type: str, model: str, usage: MistralUsage, target_company_id
) -> None:
    db.add(
        AIUsageLog(
            call_type=call_type,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            target_company_id=target_company_id,
        )
    )
    db.commit()


def _find_duplicate(
    article: Article, candidates: list[Article], threshold: float
) -> Article | None:
    best: Article | None = None
    best_sim = 0.0
    for candidate in candidates:
        if candidate.embedding is None:
            continue
        sim = AIClient.cosine_similarity(article.embedding, candidate.embedding)
        if sim > best_sim:
            best_sim = sim
            best = candidate
    return best if best_sim >= threshold else None


def _recent_signal_context(db: Session, target_company_id) -> list[str]:
    rows = (
        db.query(Signal)
        .join(Article, Signal.article_id == Article.id)
        .filter(Article.target_company_id == target_company_id)
        .order_by(Signal.created_at.desc())
        .limit(RECENT_SIGNALS_FOR_CONTEXT)
        .all()
    )
    lines = []
    for signal in rows:
        text = signal.summary.strip()
        if len(text) > SUMMARY_CONTEXT_TRUNCATE:
            text = text[:SUMMARY_CONTEXT_TRUNCATE].rsplit(" ", 1)[0] + "..."
        lines.append(text)
    return lines
