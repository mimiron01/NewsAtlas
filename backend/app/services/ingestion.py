from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_usage_log import AIUsageLog
from app.models.article import Article, ArticleSource
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.schemas.ingestion import IngestionRunResult
from app.services.ai_client import AIClient, AIClientError, MistralUsage, cosine_similarity, vector_norm
from app.services.feedback import refresh_feedback_note
from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.news_client import NewsClient, NewsClientError
from app.services.news_rate_limiter import has_headroom
from app.services.news_usage import log_rate_limited
from app.services.news_usage import log_usage as log_news_usage
from app.services.newsdata_client import NewsDataClient
from app.services.workspace_settings import (
    get_or_create_workspace_settings,
    resolve_mistral_api_key,
    resolve_newsdata_api_key,
)

MIN_LOOKBACK_HOURS = 24
RECENT_SIGNALS_FOR_CONTEXT = 2
RECENT_ARTICLES_FOR_DEDUPE = 50
SUMMARY_CONTEXT_TRUNCATE = 160
# Caps how much of a NewsData.io full-content article is sent to Mistral (embedding or
# chat) — full articles can run to many thousands of characters, and grounding quality
# gains from going past a few thousand characters are marginal relative to token cost.
FULL_TEXT_TRUNCATE = 6000


class IngestionProgress(Protocol):
    """Sink for live progress updates while a run is in flight — see
    services/ingestion_runs.py for the DB-backed implementation that powers the
    frontend's progress bar and the Settings > Logs admin view. Callers that don't care
    about progress (most direct tests) simply omit it and get _NullProgress."""

    def update(self, **fields: object) -> None: ...

    def append_error(self, message: str) -> None: ...


class _NullProgress:
    def update(self, **fields: object) -> None:
        pass

    def append_error(self, message: str) -> None:
        pass


_NULL_PROGRESS = _NullProgress()


@dataclass
class _CompanyIngestOutcome:
    articles_fetched: int = 0
    articles_new: int = 0
    signals_created: int = 0
    duplicates_skipped: int = 0
    triaged_out: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    rate_limited: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _record_error(errors: list[str], progress: IngestionProgress, message: str) -> None:
    errors.append(message)
    progress.append_error(message)


def run_ingestion(
    db: Session,
    news_client: NewsClient | None = None,
    ai_client: AIClient | None = None,
    *,
    google_news_client: GoogleNewsRSSClient | None = None,
    newsdata_client: NewsDataClient | None = None,
    progress: IngestionProgress | None = None,
) -> IngestionRunResult:
    progress = progress or _NULL_PROGRESS
    app_settings = get_settings()
    workspace_settings = get_or_create_workspace_settings(db)
    refresh_feedback_note(db, workspace_settings)

    ai_client = ai_client or AIClient(
        api_key=resolve_mistral_api_key(workspace_settings, app_settings),
        model=workspace_settings.mistral_model,
        triage_model=workspace_settings.mistral_triage_model,
        embed_model=workspace_settings.mistral_embed_model,
    )

    # Every enabled source gets a slot in this list; disabled sources are simply never
    # called (see docs/news-source-expansion-planning.html §8) — a source explicitly
    # injected for testing is used even if the caller didn't also flip its toggle, so
    # existing single-source tests keep working unchanged.
    providers: list[tuple[ArticleSource, object]] = []
    if workspace_settings.newsapi_enabled or news_client is not None:
        providers.append((ArticleSource.NEWSAPI, news_client or NewsClient(api_key=app_settings.newsapi_api_key)))
    if workspace_settings.google_news_rss_enabled or google_news_client is not None:
        providers.append(
            (
                ArticleSource.GOOGLE_NEWS_RSS,
                google_news_client
                or GoogleNewsRSSClient(
                    country=workspace_settings.google_news_rss_country,
                    language=workspace_settings.google_news_rss_language,
                ),
            )
        )
    if workspace_settings.newsdata_enabled or newsdata_client is not None:
        providers.append(
            (
                ArticleSource.NEWSDATA,
                newsdata_client
                or NewsDataClient(api_key=resolve_newsdata_api_key(workspace_settings, app_settings)),
            )
        )

    lookback_hours = max(workspace_settings.ingestion_interval_hours * 2, MIN_LOOKBACK_HOURS)
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    target_companies = db.query(TargetCompany).filter(TargetCompany.is_active.is_(True)).all()
    progress.update(companies_total=len(target_companies))

    articles_fetched = 0
    articles_new = 0
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0
    by_source: dict[str, int] = {}
    rate_limited: dict[str, int] = {}
    errors: list[str] = []

    for idx, target_company in enumerate(target_companies, start=1):
        outcome = _ingest_target_company(
            db,
            ai_client=ai_client,
            workspace_settings=workspace_settings,
            providers=providers,
            target_company=target_company,
            since=since,
            progress=progress,
        )
        articles_fetched += outcome.articles_fetched
        articles_new += outcome.articles_new
        signals_created += outcome.signals_created
        duplicates_skipped += outcome.duplicates_skipped
        triaged_out += outcome.triaged_out
        errors.extend(outcome.errors)
        for source_name, count in outcome.by_source.items():
            by_source[source_name] = by_source.get(source_name, 0) + count
        for source_name, count in outcome.rate_limited.items():
            rate_limited[source_name] = rate_limited.get(source_name, 0) + count
        # Updated unconditionally after every company, regardless of which early-exit
        # path _ingest_target_company took internally (no fetch results, no new
        # articles, etc.) — the progress bar's company count must never stall.
        progress.update(companies_processed=idx)

    return IngestionRunResult(
        target_companies_processed=len(target_companies),
        articles_fetched=articles_fetched,
        articles_new=articles_new,
        signals_created=signals_created,
        duplicates_skipped=duplicates_skipped,
        triaged_out=triaged_out,
        by_source=by_source,
        rate_limited=rate_limited,
        errors=errors,
    )


def _ingest_target_company(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    providers: list[tuple[ArticleSource, object]],
    target_company: TargetCompany,
    since: datetime,
    progress: IngestionProgress,
) -> _CompanyIngestOutcome:
    outcome = _CompanyIngestOutcome()
    progress.update(
        current_company_name=target_company.name,
        current_step="fetching",
        articles_total_this_company=0,
        articles_processed_this_company=0,
    )

    fetched_items: list[tuple[ArticleSource, object]] = []

    for source, client in providers:
        per_minute_limit, per_day_limit = _rate_limit_config(workspace_settings, source)
        if not has_headroom(db, source, per_minute_limit=per_minute_limit, per_day_limit=per_day_limit):
            outcome.rate_limited[source.value] = outcome.rate_limited.get(source.value, 0) + 1
            log_rate_limited(db, source=source, target_company_id=target_company.id)
            continue

        try:
            fetched, requests_used = _fetch_from_source(
                source, client, workspace_settings, target_company, since
            )
        except NewsClientError as exc:
            _record_error(
                outcome.errors, progress, f"[{target_company.name}] {source.value} fetch failed: {exc}"
            )
            continue

        outcome.by_source[source.value] = outcome.by_source.get(source.value, 0) + len(fetched)
        outcome.articles_fetched += len(fetched)
        log_news_usage(
            db,
            source=source,
            call_type="latest",
            target_company_id=target_company.id,
            requests_used=requests_used,
            articles_returned=len(fetched),
        )
        fetched_items.extend((source, article) for article in fetched)

    if not fetched_items:
        return outcome

    new_articles: list[Article] = []
    seen_urls: set[str] = set()
    for source, fetched in fetched_items:
        # Guards against the same URL appearing twice across this company's combined
        # fetch results (whether from one provider or two), not just against
        # previously-ingested articles: the batched commit below means the DB query
        # alone (autoflush is off) wouldn't see a duplicate added earlier in this same
        # loop, and Article.url has a unique constraint. This also doubles as the
        # first, free cross-source dedupe pass — NewsAPI.org and NewsData.io both tend
        # to return the same canonical publisher URL for the same story.
        if fetched.url in seen_urls:
            continue
        existing = db.query(Article).filter(Article.url == fetched.url).first()
        if existing is not None:
            continue
        seen_urls.add(fetched.url)
        article = Article(
            target_company_id=target_company.id,
            source=source,
            source_name=fetched.source_name,
            title=fetched.title,
            url=fetched.url,
            description=fetched.description,
            published_at=fetched.published_at,
            full_content=getattr(fetched, "full_content", None),
            external_sentiment=getattr(fetched, "sentiment", None),
            external_tags=getattr(fetched, "tags", None),
        )
        db.add(article)
        new_articles.append(article)

    if not new_articles:
        return outcome

    # A single commit (session default expire_on_commit=True) is enough — any later
    # attribute access lazily re-fetches from the DB as needed, so an eager
    # db.refresh() per article here would just be N redundant round trips.
    db.commit()
    outcome.articles_new = len(new_articles)
    progress.update(current_step="summarizing", articles_total_this_company=len(new_articles))

    signals_created_here, duplicates_here, triaged_out_here, batch_errors = _process_new_articles(
        db,
        ai_client=ai_client,
        workspace_settings=workspace_settings,
        target_company=target_company,
        new_articles=new_articles,
        progress=progress,
    )
    outcome.signals_created = signals_created_here
    outcome.duplicates_skipped = duplicates_here
    outcome.triaged_out = triaged_out_here
    outcome.errors.extend(batch_errors)
    return outcome


def _rate_limit_config(workspace_settings, source: ArticleSource) -> tuple[int | None, int | None]:
    """Returns (per_minute_limit, per_day_limit) for a source's enforced rate limit
    (see services/news_rate_limiter.py). A None limit means that dimension isn't
    configured for this source and is never checked."""
    if source == ArticleSource.NEWSAPI:
        return None, workspace_settings.newsapi_max_requests_per_day
    if source == ArticleSource.GOOGLE_NEWS_RSS:
        return workspace_settings.google_news_rss_max_requests_per_minute, None
    if source == ArticleSource.NEWSDATA:
        return (
            workspace_settings.newsdata_max_requests_per_minute,
            workspace_settings.newsdata_max_requests_per_day,
        )
    return None, None


def _fetch_from_source(
    source: ArticleSource,
    client,
    workspace_settings,
    target_company: TargetCompany,
    since: datetime,
) -> tuple[list, int]:
    """Normalizes each provider's fetch_articles() call to a uniform (articles,
    requests_used) return, since only NewsDataClient reports a per-call credit cost —
    the others are treated as costing exactly one request per call."""
    if source == ArticleSource.NEWSDATA:
        return client.fetch_articles(
            name=target_company.name,
            keywords=target_company.keywords,
            since=since,
            full_content=workspace_settings.newsdata_full_content_enabled,
            use_native_dedupe=workspace_settings.newsdata_use_native_dedupe,
        )
    articles = client.fetch_articles(name=target_company.name, keywords=target_company.keywords, since=since)
    return articles, 1


def _process_new_articles(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    target_company: TargetCompany,
    new_articles: list[Article],
    progress: IngestionProgress | None = None,
) -> tuple[int, int, int, list[str]]:
    progress = progress or _NULL_PROGRESS
    errors: list[str] = []
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0

    # One embeddings request for every new article in this batch, instead of one call
    # per article — the main lever for keeping dedupe cheap at scale. Grounds on full
    # content when NewsData.io provided it (better semantic dedupe than a snippet).
    try:
        embed_inputs = [f"{a.title}\n{_grounding_text(a)}" for a in new_articles]
        vectors, embed_usage = ai_client.embed_texts(embed_inputs)
        _log_usage(db, "embedding", ai_client.embed_model, embed_usage, target_company.id)
        for article, vector in zip(new_articles, vectors):
            article.embedding = vector
        db.commit()
    except AIClientError as exc:
        _record_error(errors, progress, f"[{target_company.name}] embedding failed: {exc}")

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

    for position, article in enumerate(new_articles):
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
                progress.update(articles_processed_this_company=position + 1)
                continue
            candidates.insert(0, article)

        if workspace_settings.mistral_triage_enabled:
            try:
                triage, triage_usage = ai_client.triage_article(
                    company_name=workspace_settings.company_name,
                    offering_description=workspace_settings.offering_description,
                    target_company_name=target_company.name,
                    article_title=article.title,
                    article_description=_grounding_text(article),
                )
                _log_usage(
                    db, "triage", ai_client.triage_model, triage_usage, target_company.id, commit=False
                )
            except AIClientError as exc:
                _record_error(
                    errors,
                    progress,
                    f"[{target_company.name}] triage failed for {article.url}: {exc} "
                    "(proceeding to full summarization without the cost-saving triage filter)",
                )
                triage = None
            if triage is not None and not triage.relevant:
                _skip_article(db, article, "triaged_out")
                triaged_out += 1
                progress.update(articles_processed_this_company=position + 1)
                continue

        try:
            result, usage = ai_client.summarize_article(
                company_name=workspace_settings.company_name,
                offering_description=workspace_settings.offering_description,
                target_company_name=target_company.name,
                article_title=article.title,
                article_description=_grounding_text(article),
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
            _record_error(
                errors, progress, f"[{target_company.name}] summarization failed for {article.url}: {exc}"
            )
            progress.update(articles_processed_this_company=position + 1)
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
        progress.update(articles_processed_this_company=position + 1)

    return signals_created, duplicates_skipped, triaged_out, errors


def _grounding_text(article: Article) -> str:
    """Full article body when NewsData.io's full-content option provided one (a genuine
    quality upgrade over a snippet — a supporting quote pulled from a full article is far
    more checkable than one inferred from two sentences); falls back to the short
    description every other source provides. Truncated defensively since full articles
    can run far longer than a snippet."""
    text = article.full_content or article.description or ""
    if len(text) > FULL_TEXT_TRUNCATE:
        text = text[:FULL_TEXT_TRUNCATE].rsplit(" ", 1)[0] + "..."
    return text


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
