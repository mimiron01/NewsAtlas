from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_usage_log import AIUsageLog
from app.models.article import Article
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.schemas.ingestion import IngestionRunResult
from app.services.ai_client import AIClient, AIClientError, MistralUsage, cosine_similarity, vector_norm
from app.services.feedback import refresh_feedback_note
from app.services.news_client import NewsClient, NewsClientError
from app.services.workspace_settings import get_or_create_workspace_settings, resolve_mistral_api_key

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
        api_key=resolve_mistral_api_key(workspace_settings, app_settings),
        model=workspace_settings.mistral_model,
        triage_model=workspace_settings.mistral_triage_model,
        embed_model=workspace_settings.mistral_embed_model,
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
        seen_urls: set[str] = set()
        for fetched in fetched_articles:
            # Guards against the same URL appearing twice in one fetch response, not just
            # against previously-ingested articles: the batched commit below means the DB
            # query alone (autoflush is off) wouldn't see a duplicate added earlier in this
            # same loop, and Article.url has a unique constraint.
            if fetched.url in seen_urls:
                continue
            existing = db.query(Article).filter(Article.url == fetched.url).first()
            if existing is not None:
                continue
            seen_urls.add(fetched.url)
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

        # A single commit (session default expire_on_commit=True) is enough — any later
        # attribute access lazily re-fetches from the DB as needed, so an eager
        # db.refresh() per article here would just be N redundant round trips.
        db.commit()
        articles_new += len(new_articles)

        signals_created_here, duplicates_here, triaged_out_here, batch_errors = _process_new_articles(
            db,
            ai_client=ai_client,
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
            # Articles that failed summarization (transient Mistral outage, etc.) never
            # reached a settled outcome — they shouldn't anchor future dedupe decisions,
            # or a real story could get silently marked "duplicate" of a failed attempt
            # and never actually get summarized once the outage clears.
            or_(Article.skip_reason.is_(None), Article.skip_reason != "ai_error"),
        )
        .order_by(Article.fetched_at.desc())
        .limit(RECENT_ARTICLES_FOR_DEDUPE)
        .all()
    )

    # Fetched once per target company rather than once per article: articles created
    # earlier in *this same batch* are prepended as they're summarized, so continuity
    # context still reflects the full run without a DB round trip per article.
    recent_signal_summaries = _recent_signal_context(db, target_company.id)

    for article in new_articles:
        if article.embedding is not None:
            duplicate = _find_duplicate(
                article, candidates, workspace_settings.mistral_dedupe_similarity_threshold
            )
            if duplicate is not None:
                article.duplicate_of_article_id = duplicate.id
                _skip_article(db, article, "duplicate")
                duplicates_skipped += 1
                # Still added as a dedupe anchor: a later article in this same batch may
                # be a closer paraphrase of THIS duplicate than of the original, so
                # dropping it from the pool would miss transitive duplicate chains.
                candidates.insert(0, article)
                continue
            candidates.insert(0, article)

        if workspace_settings.mistral_triage_enabled:
            try:
                triage, triage_usage = ai_client.triage_article(
                    company_name=workspace_settings.company_name,
                    offering_description=workspace_settings.offering_description,
                    target_company_name=target_company.name,
                    article_title=article.title,
                    article_description=article.description,
                )
                _log_usage(
                    db, "triage", ai_client.triage_model, triage_usage, target_company.id, commit=False
                )
            except AIClientError as exc:
                errors.append(
                    f"[{target_company.name}] triage failed for {article.url}: {exc} "
                    "(proceeding to full summarization without the cost-saving triage filter)"
                )
                triage = None
            if triage is not None and not triage.relevant:
                _skip_article(db, article, "triaged_out")
                triaged_out += 1
                continue

        try:
            result, usage = ai_client.summarize_article(
                company_name=workspace_settings.company_name,
                offering_description=workspace_settings.offering_description,
                target_company_name=target_company.name,
                article_title=article.title,
                article_description=article.description,
                industry=target_company.industry,
                # A copy, not the live list: it's mutated below as new signals are
                # created, and the callee must see the state as of *this* call, not
                # whatever the list looks like by the time it's inspected later.
                recent_signals=list(recent_signal_summaries),
                feedback_note=workspace_settings.ai_feedback_note,
            )
            _log_usage(db, "summarize", ai_client.model, usage, target_company.id, commit=False)
        except AIClientError as exc:
            _skip_article(db, article, "ai_error")
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
        recent_signal_summaries.insert(0, _truncate_summary(result.summary))
        del recent_signal_summaries[RECENT_SIGNALS_FOR_CONTEXT:]

    return signals_created, duplicates_skipped, triaged_out, errors


def _skip_article(db: Session, article: Article, reason: str) -> None:
    """Commits the skip_reason together with any pending (not-yet-committed) usage-log
    rows added earlier for this article, instead of a separate commit per write."""
    article.skip_reason = reason
    db.commit()


def _log_usage(
    db: Session,
    call_type: str,
    model: str,
    usage: MistralUsage,
    target_company_id,
    *,
    commit: bool = True,
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
    if commit:
        db.commit()


def _find_duplicate(
    article: Article, candidates: list[Article], threshold: float
) -> Article | None:
    norm_a = vector_norm(article.embedding)
    best: Article | None = None
    best_sim = 0.0
    for candidate in candidates:
        if candidate.embedding is None:
            continue
        sim = cosine_similarity(article.embedding, candidate.embedding, norm_a=norm_a)
        if sim > best_sim:
            best_sim = sim
            best = candidate
    return best if best_sim >= threshold else None


def _truncate_summary(text: str) -> str:
    text = text.strip()
    if len(text) > SUMMARY_CONTEXT_TRUNCATE:
        text = text[:SUMMARY_CONTEXT_TRUNCATE].rsplit(" ", 1)[0] + "..."
    return text


def _recent_signal_context(db: Session, target_company_id) -> list[str]:
    rows = (
        db.query(Signal)
        .join(Article, Signal.article_id == Article.id)
        .filter(Article.target_company_id == target_company_id)
        .order_by(Signal.created_at.desc())
        .limit(RECENT_SIGNALS_FOR_CONTEXT)
        .all()
    )
    return [_truncate_summary(signal.summary) for signal in rows]
