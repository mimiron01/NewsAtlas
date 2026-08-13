import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_usage_log import AIUsageLog
from app.models.article import Article, ArticleSource
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.schemas.ingestion import IngestionRunResult
from app.services.ai_client import AIClient, AIClientError, MistralUsage, cosine_similarity, vector_norm
from app.services.article_enrichment import EnrichmentBudget, enrich_articles
from app.services.article_scoring import collapse_near_duplicate_titles, rank_candidates, score_candidate
from app.services.feedback import refresh_feedback_note, refresh_theme_feedback_note
from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.news_client import FetchOutcome, NewsClient, NewsClientError
from app.services.news_query import (
    article_excluded_by_theme_terms,
    article_matches_theme_terms,
    article_mentions_company,
    build_google_news_query,
    build_theme_query,
    google_when_operator,
    identity_terms,
    resolve_allowlist,
    resolve_denylist,
)
from app.services.news_rate_limiter import HeadroomStatus, check_headroom, wait_for_minute_headroom
from app.services.news_usage import log_rate_limited
from app.services.news_usage import log_usage as log_news_usage
from app.services.newsdata_client import NewsDataClient
from app.services.workspace_settings import (
    get_or_create_workspace_settings,
    resolve_mistral_api_key,
    resolve_newsdata_api_key,
)

# Scheduled runs fire every 4 hours Mon-Fri and once at 20:00 UTC on Sat/Sun (see
# services/scheduler.py) — the widest gap between two consecutive runs is 24h
# (Fri 20:00 -> Sat 20:00, or Sat 20:00 -> Sun 20:00 UTC). Lookback stays fixed rather
# than tracking the schedule so it also covers a manual run after a missed/delayed
# scheduled tick, with a margin above that 24h worst case.
LOOKBACK_HOURS = 30
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

    def should_cancel(self) -> bool: ...


class _NullProgress:
    def update(self, **fields: object) -> None:
        pass

    def append_error(self, message: str) -> None:
        pass

    def should_cancel(self) -> bool:
        return False


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
    # True if a cancellation was observed while processing this company's articles (see
    # IngestionProgress.should_cancel) — the outer per-company loop in run_ingestion()
    # stops after this company rather than starting the next one.
    cancelled: bool = False


@dataclass
class _ThemeIngestOutcome:
    """Mirrors _CompanyIngestOutcome, sized down to what a ThemeWatch run actually
    produces (see docs/theme-search-planning.html §5) — no articles_fetched/by_source/
    rate_limited of its own since those fold into the shared GOOGLE_NEWS_RSS totals the
    company loop already tracks."""

    matches_created: int = 0
    duplicates_skipped: int = 0
    triaged_out: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


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
    theme_watch_id: uuid.UUID | None = None,
    target_company_ids: list[uuid.UUID] | None = None,
) -> IngestionRunResult:
    """Full run by default: every active target company, then every active theme watch.

    Passing theme_watch_id scopes the run down to that single theme and skips the company
    loop entirely — this is what the Themes page's per-theme "fetch now" button triggers
    (see api/theme_watches.py). Passing target_company_ids scopes the run down to just
    those companies and skips the theme loop entirely, the mirror image — this is what the
    "My companies" table's per-row or multi-select "fetch now" triggers (see
    api/target_companies.py). The two scoping params are mutually exclusive; callers only
    ever set one, since each comes from a different button. Default None on both keeps
    every existing caller (the scheduler, the workspace-wide manual trigger) on exactly the
    previous behavior.
    """
    progress = progress or _NULL_PROGRESS
    scoped_to_theme = theme_watch_id is not None
    scoped_to_companies = target_company_ids is not None
    app_settings = get_settings()
    workspace_settings = get_or_create_workspace_settings(db)
    refresh_feedback_note(db, workspace_settings)

    ai_client = ai_client or AIClient(
        api_key=resolve_mistral_api_key(workspace_settings, app_settings),
        model=workspace_settings.mistral_model,
        triage_model=workspace_settings.mistral_triage_model,
        embed_model=workspace_settings.mistral_embed_model,
        max_requests_per_second=app_settings.mistral_max_requests_per_second,
        max_retries=app_settings.mistral_max_retries,
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

    since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    # One budget for the whole run, shared by companies and themes: the ceiling exists to
    # bound how long an ingestion run can spend waiting on other people's web servers, and
    # that's a property of the run, not of any one company.
    enrichment_budget = EnrichmentBudget(
        max_fetches=workspace_settings.max_enrichment_fetches_per_run,
        max_seconds=workspace_settings.max_enrichment_seconds_per_run,
    )

    # A theme-scoped run never touches companies, so the company loop below iterates an
    # empty list rather than being wrapped in a conditional — keeps the counter/progress
    # bookkeeping that follows on exactly one code path. A company-scoped run still filters
    # to is_active, same as the full run — a company paused after being selected shouldn't
    # silently get fetched anyway.
    if scoped_to_theme:
        target_companies = []
    elif scoped_to_companies:
        target_companies = (
            db.query(TargetCompany)
            .filter(TargetCompany.id.in_(target_company_ids), TargetCompany.is_active.is_(True))
            .all()
        )
    else:
        target_companies = db.query(TargetCompany).filter(TargetCompany.is_active.is_(True)).all()

    # The mirror image: a company-scoped run never touches themes, so the theme loop below
    # also iterates an empty list rather than a conditional.
    if scoped_to_companies:
        theme_watches = []
    else:
        theme_watches_query = db.query(ThemeWatch).filter(ThemeWatch.is_active.is_(True))
        if scoped_to_theme:
            theme_watches_query = theme_watches_query.filter(ThemeWatch.id == theme_watch_id)
        theme_watches = theme_watches_query.all()
    progress.update(companies_total=len(target_companies), themes_total=len(theme_watches))

    articles_fetched = 0
    articles_new = 0
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0
    by_source: dict[str, int] = {}
    rate_limited: dict[str, int] = {}
    errors: list[str] = []
    companies_processed = 0
    cancelled = False

    for idx, target_company in enumerate(target_companies, start=1):
        # Checked once per company (and again, more finely, inside article processing —
        # see _process_new_articles) so an admin's "Stop" click takes effect at the next
        # natural checkpoint rather than mid-write. Every checkpoint lands right after a
        # commit, so stopping here never leaves partial/uncommitted work behind.
        if progress.should_cancel():
            cancelled = True
            break

        outcome = _ingest_target_company(
            db,
            ai_client=ai_client,
            workspace_settings=workspace_settings,
            providers=providers,
            target_company=target_company,
            since=since,
            progress=progress,
            enrichment_budget=enrichment_budget,
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
        companies_processed = idx
        # Updated unconditionally after every company, regardless of which early-exit
        # path _ingest_target_company took internally (no fetch results, no new
        # articles, etc.) — the progress bar's company count must never stall.
        progress.update(companies_processed=idx)

        if outcome.cancelled:
            cancelled = True
            break

    # Theme watches share the company loop's GOOGLE_NEWS_RSS client/rate limiting (see
    # docs/theme-search-planning.html §5) — reuse whichever instance is already active
    # (real or test-injected) rather than constructing a second one. No client means
    # Google News RSS isn't enabled for this workspace, so there's nothing to fetch
    # themes with (themes have no other provider in v1).
    theme_matches_created = 0
    themes_processed = 0
    if not cancelled and theme_watches:
        # One shared budget for the whole run rather than per theme: the point is to stop
        # a themes-heavy workspace draining a paid provider's daily quota, and a per-theme
        # cap scales with the number of themes, which is exactly the wrong direction.
        request_budget = (
            {source: workspace_settings.max_theme_requests_per_run_per_source for source, _ in providers}
            if workspace_settings.max_theme_requests_per_run_per_source > 0
            else None
        )
        for idx, theme_watch in enumerate(theme_watches, start=1):
            if progress.should_cancel():
                cancelled = True
                break

            theme_providers = _providers_for_theme(providers, workspace_settings, theme_watch)
            if not theme_providers:
                # This used to be a silent no-op: the run completed "successfully",
                # themes_processed stayed 0, and nothing anywhere told the user why their
                # topic never produced a single match. Recording it as a run error puts it
                # in the Logs view, the feed's run summary, and the Themes page instead.
                _record_error(
                    errors,
                    progress,
                    f"[theme:{theme_watch.name}] skipped: none of the news sources this "
                    "topic may use are enabled for the workspace. Check Settings > News "
                    "sources and the topic's own source selection.",
                )
                themes_processed = idx
                progress.update(themes_processed=idx)
                continue

            theme_outcome = _ingest_theme_watch(
                db,
                ai_client=ai_client,
                workspace_settings=workspace_settings,
                providers=theme_providers,
                theme_watch=theme_watch,
                since=since,
                progress=progress,
                request_budget=request_budget,
                enrichment_budget=enrichment_budget,
            )
            theme_matches_created += theme_outcome.matches_created
            duplicates_skipped += theme_outcome.duplicates_skipped
            triaged_out += theme_outcome.triaged_out
            errors.extend(theme_outcome.errors)
            themes_processed = idx
            # Same unconditional-update rule as the company loop above: whichever
            # early-exit path _ingest_theme_watch took internally, the theme counter
            # must not stall or the progress bar freezes mid-run.
            progress.update(themes_processed=idx)

            if theme_outcome.cancelled:
                cancelled = True
                break

        progress.update(current_theme_name=None, current_step=None)

    return IngestionRunResult(
        themes_total=len(theme_watches),
        target_companies_processed=companies_processed,
        cancelled=cancelled,
        articles_fetched=articles_fetched,
        articles_new=articles_new,
        signals_created=signals_created,
        duplicates_skipped=duplicates_skipped,
        triaged_out=triaged_out,
        by_source=by_source,
        rate_limited=rate_limited,
        errors=errors,
        theme_matches_created=theme_matches_created,
        themes_processed=themes_processed,
    )


def _providers_for_theme(
    providers: list[tuple[ArticleSource, object]], workspace_settings, theme_watch: ThemeWatch
) -> list[tuple[ArticleSource, object]]:
    """Which of the run's active providers this theme may use.

    A provider must be BOTH selected for the theme (its own list, or the workspace default
    when it hasn't set one) AND enabled workspace-wide — the enable toggles stay the master
    switch, so a stale selection can never resurrect a source an admin turned off
    (docs/google-news-quality-planning.html §11.3).
    """
    selected = theme_watch.news_sources
    if selected is None:
        selected = workspace_settings.theme_news_sources or []
    selected_values = {value for value in selected}
    return [(source, client) for source, client in providers if source.value in selected_values]


def _ingest_target_company(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    providers: list[tuple[ArticleSource, object]],
    target_company: TargetCompany,
    since: datetime,
    progress: IngestionProgress,
    enrichment_budget: EnrichmentBudget | None = None,
) -> _CompanyIngestOutcome:
    outcome = _CompanyIngestOutcome()
    progress.update(
        current_company_name=target_company.name,
        current_step="fetching",
        articles_total_this_company=0,
        articles_processed_this_company=0,
    )

    # Resolved once: the scorer needs the same effective allowlist the query was built
    # with, so a company that overrides the workspace list is scored against its own
    # trusted domains rather than the workspace's.
    effective_allowlist = resolve_allowlist(
        target_company.google_news_source_allowlist,
        workspace_settings.google_news_source_allowlist,
    )

    fetched_items: list[tuple[ArticleSource, object]] = []
    pending_logs: list[tuple[ArticleSource, FetchOutcome]] = []
    # Post-fetch drops, attributed back to the source that produced the candidate so each
    # provider's usage row explains its own funnel (see §5.1). Keyed by source, then stage.
    stage_drops: dict[ArticleSource, dict[str, int]] = {}

    def _drop(source: ArticleSource, stage: str) -> None:
        stage_drops.setdefault(source, {})
        stage_drops[source][stage] = stage_drops[source].get(stage, 0) + 1

    for source, client in providers:
        per_minute_limit, per_day_limit = _rate_limit_config(workspace_settings, source)
        status = check_headroom(db, source, per_minute_limit=per_minute_limit, per_day_limit=per_day_limit)

        if status is HeadroomStatus.MINUTE_LIMITED:
            # A per-minute ceiling frees up on its own within the next 60s, so it's
            # worth waiting out rather than permanently dropping this company's
            # coverage from this source — a per-day ceiling (handled below) won't free
            # up for hours, so that case still falls straight through to the skip.
            progress.update(current_step="waiting", current_company_name=target_company.name)
            if wait_for_minute_headroom(
                db, source, per_minute_limit=per_minute_limit, should_cancel=progress.should_cancel
            ):
                status = HeadroomStatus.OK
            progress.update(current_step="fetching")
            if progress.should_cancel():
                outcome.cancelled = True
                return outcome

        if status is not HeadroomStatus.OK:
            outcome.rate_limited[source.value] = outcome.rate_limited.get(source.value, 0) + 1
            log_rate_limited(db, source=source, target_company_id=target_company.id, theme_watch_id=None)
            continue

        try:
            result = _fetch_from_source(source, client, workspace_settings, target_company, since)
        except NewsClientError as exc:
            _record_error(
                outcome.errors, progress, f"[{target_company.name}] {source.value} fetch failed: {exc}"
            )
            continue

        fetched = result.articles
        outcome.by_source[source.value] = outcome.by_source.get(source.value, 0) + len(fetched)
        outcome.articles_fetched += len(fetched)
        # Held until the whole company's funnel is known: the stages after this one
        # (grounding, dedupe, cap) discard candidates too, and a drop breakdown that stops
        # at the fetch boundary answers none of the questions it exists to answer.
        pending_logs.append((source, result))
        fetched_items.extend((source, article) for article in fetched)

    if not fetched_items:
        _flush_usage_logs(db, pending_logs, target_company_id=target_company.id)
        return outcome

    # Grounding guard: a provider's own search relevance is frequently loose/fuzzy, so
    # matching the query doesn't guarantee the article actually mentions the company —
    # drop anything that doesn't, before it's ever stored as this company's Article (see
    # docs/ingestion-reliability-planning.html §5).
    grounded_items = []
    for source, fetched in fetched_items:
        if article_mentions_company(
            title=fetched.title,
            description=fetched.description,
            full_content=getattr(fetched, "full_content", None),
            name=target_company.name,
            aliases=target_company.aliases,
        ):
            grounded_items.append((source, fetched))
        else:
            _drop(source, "not_grounded")
    if not grounded_items:
        _flush_usage_logs(db, pending_logs, target_company_id=target_company.id, stage_drops=stage_drops)
        return outcome

    # Cross-source + already-ingested URL dedupe, kept on raw fetched items (not yet
    # Article rows) so the newest-N cap below only has to sort/slice genuinely-new
    # candidates instead of discarding constructed-then-unused ORM objects.
    seen_urls: set[str] = set()
    deduped_items: list[tuple[ArticleSource, object]] = []
    for source, fetched in grounded_items:
        # Guards against the same URL appearing twice across this company's combined
        # fetch results (whether from one provider or two), not just against
        # previously-ingested articles: the batched commit below means the DB query
        # alone (autoflush is off) wouldn't see a duplicate added earlier in this same
        # loop, and Article.url has a unique constraint. This also doubles as the
        # first, free cross-source dedupe pass — NewsAPI.org and NewsData.io both tend
        # to return the same canonical publisher URL for the same story.
        if fetched.url in seen_urls:
            _drop(source, "url_duplicate")
            continue
        # Company-scoped, not global: the same story can legitimately name two tracked
        # companies, and each deserves its own signal with its own outreach angle. A
        # global check silently gave it to whichever company the loop reached first (see
        # docs/google-news-quality-planning.html §8.3, finding F12).
        existing = (
            db.query(Article)
            .filter(Article.url == fetched.url, Article.target_company_id == target_company.id)
            .first()
        )
        if existing is not None:
            _drop(source, "url_duplicate")
            continue
        # The other half of the cross-path URL dedupe required by
        # docs/theme-search-planning.html §6. The theme path has always checked Article.url
        # before creating a ThemeMatch; without this mirror-image check the guarantee held
        # in only one direction, so the same wire-service story would surface twice — once
        # as a theme match and once as a company signal — purely depending on which loop
        # happened to fetch it first.
        if db.query(ThemeMatch).filter(ThemeMatch.url == fetched.url).first() is not None:
            _drop(source, "url_duplicate")
            continue
        seen_urls.add(fetched.url)
        deduped_items.append((source, fetched))

    if not deduped_items:
        _flush_usage_logs(db, pending_logs, target_company_id=target_company.id, stage_drops=stage_drops)
        return outcome

    # Collapse syndicated near-identical headlines before anything is embedded — Google
    # News in particular returns the same wire story from a dozen outlets, and paying for
    # an embedding per copy to discover they're duplicates is avoidable (see §8.2).
    deduped_items, title_duplicates = collapse_near_duplicate_titles(
        deduped_items,
        key=lambda item: item[1].title,
        score=lambda item: score_candidate(
            item[1],
            identity_terms=identity_terms(target_company),
            context_terms=target_company.context_terms,
            allowlist=effective_allowlist,
            since=since,
        ),
    )
    for source, _dropped in title_duplicates:
        _drop(source, "title_duplicate")

    # Cap the genuinely-new candidates for this company — bounds the expensive
    # embedding/triage/summarization work below regardless of how many raw results the
    # sources returned. 0 disables the cap (unlimited), matching the "0 = off" convention
    # used elsewhere on workspace_settings (e.g. newsdata_backfill_days).
    #
    # Selection is by composite score, not by recency: on a syndication-heavy,
    # relevance-ranked feed the newest item is systematically an aggregator repost rather
    # than the original wire story, so "newest N" spent the entire AI budget on the worst
    # candidates (finding F5). score_candidate() breaks ties on published_at, so this
    # still degrades to the old behaviour when nothing else distinguishes two articles.
    cap = workspace_settings.max_articles_per_company_per_run
    if cap > 0 and len(deduped_items) > cap:
        deduped_items = rank_candidates(
            deduped_items,
            article_of=lambda item: item[1],
            identity_terms=identity_terms(target_company),
            context_terms=target_company.context_terms,
            allowlist=effective_allowlist,
            since=since,
        )
        for source, _dropped in deduped_items[cap:]:
            _drop(source, "over_cap")
        deduped_items = deduped_items[:cap]

    _flush_usage_logs(db, pending_logs, target_company_id=target_company.id, stage_drops=stage_drops)

    new_articles: list[Article] = []
    for source, fetched in deduped_items:
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

    # After the cap, before the first AI call: enrichment turns headline-only Google News
    # rows into rows with real publisher text, which is exactly what triage and
    # summarization are about to judge. No-op unless an admin enabled it.
    enrich_articles(new_articles, workspace_settings, budget=enrichment_budget)

    # A single commit (session default expire_on_commit=True) is enough — any later
    # attribute access lazily re-fetches from the DB as needed, so an eager
    # db.refresh() per article here would just be N redundant round trips.
    db.commit()
    outcome.articles_new = len(new_articles)
    progress.update(current_step="summarizing", articles_total_this_company=len(new_articles))

    signals_created_here, duplicates_here, triaged_out_here, batch_errors, batch_cancelled = (
        _process_new_articles(
            db,
            ai_client=ai_client,
            workspace_settings=workspace_settings,
            target_company=target_company,
            new_articles=new_articles,
            progress=progress,
        )
    )
    outcome.signals_created = signals_created_here
    outcome.duplicates_skipped = duplicates_here
    outcome.triaged_out = triaged_out_here
    outcome.errors.extend(batch_errors)
    outcome.cancelled = batch_cancelled
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


def _effective_edition(entity, workspace_settings) -> tuple[str, str]:
    """(country, language) for an entity, with NULL on the entity meaning "inherit the
    workspace edition" — the convention ThemeWatch established and TargetCompany now
    shares (docs/google-news-quality-planning.html §6.3)."""
    country = getattr(entity, "google_news_country", None) or workspace_settings.google_news_rss_country
    language = getattr(entity, "google_news_language", None) or workspace_settings.google_news_rss_language
    return country, language


def _when_operator(workspace_settings, since: datetime) -> str | None:
    return google_when_operator(since) if workspace_settings.google_news_time_operator_enabled else None


def _fetch_from_source(
    source: ArticleSource,
    client,
    workspace_settings,
    target_company: TargetCompany,
    since: datetime,
) -> FetchOutcome:
    """Normalizes every provider's fetch_articles() call to a uniform FetchOutcome, since
    the three disagree on both return shape and per-call cost (only NewsDataClient reports
    a real credit cost; the others cost exactly one request per call)."""
    _, language = _effective_edition(target_company, workspace_settings)

    if source == ArticleSource.NEWSDATA:
        articles, requests_used = client.fetch_articles(
            name=target_company.name,
            keywords=target_company.keywords,
            since=since,
            full_content=workspace_settings.newsdata_full_content_enabled,
            use_native_dedupe=workspace_settings.newsdata_use_native_dedupe,
            language=language,
        )
        return FetchOutcome(
            articles=articles, requests_used=requests_used, articles_raw=len(articles)
        )

    if source == ArticleSource.GOOGLE_NEWS_RSS:
        country, _ = _effective_edition(target_company, workspace_settings)
        query, truncated = build_google_news_query(
            name=target_company.name,
            aliases=target_company.aliases,
            context_terms=target_company.context_terms,
            exclude_terms=target_company.exclude_terms,
            allow_sites=resolve_allowlist(
                target_company.google_news_source_allowlist,
                workspace_settings.google_news_source_allowlist,
            ),
            deny_sites=resolve_denylist(
                target_company.google_news_source_denylist,
                workspace_settings.google_news_source_denylist,
            ),
            when=_when_operator(workspace_settings, since),
            require_name_in_title=target_company.google_news_require_name_in_title,
        )
        outcome = client.fetch_articles(
            since=since, query_override=query, country=country, language=language
        )
        if truncated:
            # Surfaced in the usage log rather than raised: the query still ran and still
            # returned results, but the user needs to know some of what they configured
            # never reached Google (finding F8).
            outcome.drop_counts["query_truncated"] = 1

        # The identity-only second pass: a company's context terms narrow the query, which
        # is the point, but it also means a genuine story that doesn't happen to use them
        # is invisible. Merged by URL, so the extra request costs nothing downstream.
        if workspace_settings.google_news_query_strategy == "split" and target_company.context_terms:
            identity_query, _ = build_google_news_query(
                name=target_company.name,
                aliases=target_company.aliases,
                exclude_terms=target_company.exclude_terms,
                allow_sites=resolve_allowlist(
                    target_company.google_news_source_allowlist,
                    workspace_settings.google_news_source_allowlist,
                ),
                deny_sites=resolve_denylist(
                    target_company.google_news_source_denylist,
                    workspace_settings.google_news_source_denylist,
                ),
                when=_when_operator(workspace_settings, since),
                require_name_in_title=target_company.google_news_require_name_in_title,
            )
            second = client.fetch_articles(
                since=since, query_override=identity_query, country=country, language=language
            )
            outcome = _merge_outcomes(outcome, second)
        return outcome

    articles = client.fetch_articles(
        name=target_company.name,
        keywords=target_company.keywords,
        since=since,
        language=language,
    )
    return FetchOutcome(articles=articles, requests_used=1, articles_raw=len(articles))


def _merge_outcomes(first: FetchOutcome, second: FetchOutcome) -> FetchOutcome:
    """Merges two fetches of the same source for the same entity, de-duplicating by URL
    and summing their cost and diagnostics."""
    seen = {article.url for article in first.articles}
    merged = list(first.articles)
    for article in second.articles:
        if article.url not in seen:
            seen.add(article.url)
            merged.append(article)

    drop_counts = dict(first.drop_counts)
    for stage, count in second.drop_counts.items():
        drop_counts[stage] = drop_counts.get(stage, 0) + count

    return FetchOutcome(
        articles=merged,
        requests_used=first.requests_used + second.requests_used,
        query_text=" | ".join(filter(None, [first.query_text, second.query_text])) or None,
        articles_raw=first.articles_raw + second.articles_raw,
        drop_counts=drop_counts,
    )


def _flush_usage_logs(
    db: Session,
    pending_logs: list[tuple[ArticleSource, FetchOutcome]],
    *,
    target_company_id=None,
    theme_watch_id=None,
    stage_drops: dict[ArticleSource, dict[str, int]] | None = None,
) -> None:
    """Writes one usage row per provider call, merging the drops the client observed with
    the drops the pipeline observed afterwards. Deferred to the end of an entity's fetch
    so a single row describes that provider's whole funnel, not just its fetch boundary."""
    stage_drops = stage_drops or {}
    for source, result in pending_logs:
        drop_counts = dict(result.drop_counts)
        for stage, count in stage_drops.get(source, {}).items():
            drop_counts[stage] = drop_counts.get(stage, 0) + count
        log_news_usage(
            db,
            source=source,
            call_type="latest",
            target_company_id=target_company_id,
            theme_watch_id=theme_watch_id,
            requests_used=result.requests_used,
            articles_returned=len(result.articles),
            query_text=result.query_text,
            articles_raw=result.articles_raw,
            drop_counts=drop_counts,
        )


def _fetch_theme_from_source(
    source: ArticleSource,
    client,
    workspace_settings,
    theme_watch: ThemeWatch,
    since: datetime,
    effective_allowlist: list[str],
) -> FetchOutcome:
    """Theme-side counterpart to _fetch_from_source. Themes have no company name to anchor
    a query to, so every provider is driven through its query_override path with the
    theme's own terms (docs/google-news-quality-planning.html §11.5)."""
    deny_sites = resolve_denylist(
        theme_watch.google_news_source_denylist, workspace_settings.google_news_source_denylist
    )
    country, language = _effective_edition(theme_watch, workspace_settings)

    if source == ArticleSource.GOOGLE_NEWS_RSS:
        query, truncated = build_theme_query(
            theme_watch.query_terms,
            exclude_terms=theme_watch.exclude_terms,
            allow_sites=effective_allowlist,
            deny_sites=deny_sites,
            when=_when_operator(workspace_settings, since),
        )
        outcome = client.fetch_articles(
            since=since,
            query_override=query,
            # None falls back to the client's workspace-wide edition inside
            # fetch_articles — NULL on the theme means "inherit", not "no edition".
            country=theme_watch.google_news_country,
            language=theme_watch.google_news_language,
        )
        if truncated:
            outcome.drop_counts["query_truncated"] = 1
        return outcome

    # NewsAPI.org and NewsData.io have no site:/-site: equivalent inside the query string
    # (they take domain filters as separate request parameters, which this codebase
    # doesn't yet pass), so their query carries only the terms and exclusions.
    query, _ = build_theme_query(
        theme_watch.query_terms, exclude_terms=theme_watch.exclude_terms
    )

    if source == ArticleSource.NEWSDATA:
        articles, requests_used = client.fetch_articles(
            name="",
            keywords=theme_watch.query_terms,
            since=since,
            full_content=workspace_settings.newsdata_full_content_enabled,
            use_native_dedupe=workspace_settings.newsdata_use_native_dedupe,
            language=language,
            query_override=query,
        )
        return FetchOutcome(
            articles=articles,
            requests_used=requests_used,
            query_text=query,
            articles_raw=len(articles),
        )

    articles = client.fetch_articles(
        name="",
        keywords=theme_watch.query_terms,
        since=since,
        language=language,
        query_override=query,
    )
    return FetchOutcome(
        articles=articles, requests_used=1, query_text=query, articles_raw=len(articles)
    )


def _ingest_theme_watch(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    providers: list[tuple[ArticleSource, object]],
    theme_watch: ThemeWatch,
    since: datetime,
    progress: IngestionProgress,
    request_budget: dict[ArticleSource, int] | None = None,
    enrichment_budget: EnrichmentBudget | None = None,
) -> _ThemeIngestOutcome:
    """Mirrors _ingest_target_company for the theme path (docs/theme-search-planning.html
    §5), across whichever providers this theme is allowed to use
    (docs/google-news-quality-planning.html §11)."""
    # Recomputed per-theme, mirroring the once-per-run workspace-wide
    # refresh_feedback_note call above — see docs/topics-ux-improvements-planning.html
    # §3.1. Free (SQL only), so doing it on every run is cheap.
    refresh_theme_feedback_note(db, theme_watch)
    outcome = _ThemeIngestOutcome()
    progress.update(
        current_theme_name=theme_watch.name,
        # Cleared so the UI stops attributing the theme phase's progress to whichever
        # company happened to be processed last.
        current_company_name=None,
        current_step="fetching",
        articles_total_this_company=0,
        articles_processed_this_company=0,
    )

    effective_allowlist = resolve_allowlist(
        theme_watch.google_news_source_allowlist, workspace_settings.google_news_source_allowlist
    )
    fetched_items: list[tuple[ArticleSource, object]] = []
    pending_logs: list[tuple[ArticleSource, FetchOutcome]] = []
    stage_drops: dict[ArticleSource, dict[str, int]] = {}

    def _drop(source: ArticleSource, stage: str) -> None:
        stage_drops.setdefault(source, {})
        stage_drops[source][stage] = stage_drops[source].get(stage, 0) + 1

    for source, client in providers:
        if request_budget is not None and request_budget.get(source, 0) <= 0:
            _record_error(
                outcome.errors,
                progress,
                f"[theme:{theme_watch.name}] skipped {source.value}: this run's theme "
                "request budget for that source is exhausted "
                "(Settings > News sources > max theme requests per run).",
            )
            continue

        per_minute_limit, per_day_limit = _rate_limit_config(workspace_settings, source)
        rate_status = check_headroom(
            db, source, per_minute_limit=per_minute_limit, per_day_limit=per_day_limit
        )
        if rate_status is HeadroomStatus.MINUTE_LIMITED:
            progress.update(current_step="waiting")
            if wait_for_minute_headroom(
                db, source, per_minute_limit=per_minute_limit, should_cancel=progress.should_cancel
            ):
                rate_status = HeadroomStatus.OK
            progress.update(current_step="fetching")
            if progress.should_cancel():
                outcome.cancelled = True
                return outcome
        if rate_status is not HeadroomStatus.OK:
            log_rate_limited(
                db, source=source, target_company_id=None, theme_watch_id=theme_watch.id
            )
            # Recorded as an error, not skipped silently — otherwise a rate-limited theme is
            # indistinguishable from a theme that simply found no news.
            _record_error(
                outcome.errors,
                progress,
                f"[theme:{theme_watch.name}] skipped {source.value}: rate limit reached.",
            )
            continue

        try:
            result = _fetch_theme_from_source(
                source, client, workspace_settings, theme_watch, since, effective_allowlist
            )
        except NewsClientError as exc:
            _record_error(
                outcome.errors, progress, f"[theme:{theme_watch.name}] {source.value} fetch failed: {exc}"
            )
            continue

        if request_budget is not None:
            request_budget[source] = request_budget.get(source, 0) - result.requests_used
        pending_logs.append((source, result))
        fetched_items.extend((source, item) for item in result.articles)

    if not fetched_items:
        _flush_usage_logs(db, pending_logs, theme_watch_id=theme_watch.id, stage_drops=stage_drops)
        return outcome

    # The theme-path analogue of the company path's grounding guard. A theme has no single
    # identity to check, but its query terms are its relevance signal, so an article
    # containing none of them was matched by provider fuzz — rejecting it here costs
    # nothing, where letting it reach triage costs a token spend per article (§11.4).
    # exclude_terms are already sent to the provider as a `-term` operator (see
    # _fetch_theme_from_source), but that's a request the provider can honor loosely —
    # same fuzziness that motivates the query_terms grounding check above. Re-check
    # locally so an excluded term actually present in the article text can never slip
    # through as a match just because the provider's own exclusion missed it.
    grounded_items = []
    for source, item in fetched_items:
        if not article_matches_theme_terms(
            title=item.title,
            description=item.description,
            full_content=getattr(item, "full_content", None),
            query_terms=theme_watch.query_terms,
        ):
            _drop(source, "not_grounded")
        elif theme_watch.exclude_terms and article_excluded_by_theme_terms(
            title=item.title,
            description=item.description,
            full_content=getattr(item, "full_content", None),
            exclude_terms=theme_watch.exclude_terms,
        ):
            _drop(source, "excluded_term_match")
        else:
            grounded_items.append((source, item))

    if not grounded_items:
        _flush_usage_logs(db, pending_logs, theme_watch_id=theme_watch.id, stage_drops=stage_drops)
        return outcome

    # Cross-path dedup (mandatory floor — see docs/theme-search-planning.html §6):
    # never create a ThemeMatch for a URL already covered via some company's Article,
    # and never create two ThemeMatch rows for the same URL (this theme or another).
    # Both checks stay global, unlike the company path's now company-scoped one: a theme
    # match exists to surface a story nobody is tracking yet, so a story already covered
    # by any company is by definition not that.
    seen_urls: set[str] = set()
    deduped: list = []
    for source, item in grounded_items:
        if item.url in seen_urls:
            _drop(source, "url_duplicate")
            continue
        if db.query(Article).filter(Article.url == item.url).first() is not None:
            _drop(source, "url_duplicate")
            continue
        if db.query(ThemeMatch).filter(ThemeMatch.url == item.url).first() is not None:
            _drop(source, "url_duplicate")
            continue
        seen_urls.add(item.url)
        deduped.append((source, item))

    if not deduped:
        _flush_usage_logs(db, pending_logs, theme_watch_id=theme_watch.id, stage_drops=stage_drops)
        return outcome

    deduped, title_duplicates = collapse_near_duplicate_titles(
        deduped,
        key=lambda item: item[1].title,
        score=lambda item: score_candidate(
            item[1],
            identity_terms=theme_watch.query_terms,
            allowlist=effective_allowlist,
            since=since,
        ),
    )
    for source, _dropped in title_duplicates:
        _drop(source, "title_duplicate")

    cap = workspace_settings.max_articles_per_theme_per_run
    if cap > 0 and len(deduped) > cap:
        deduped = rank_candidates(
            deduped,
            article_of=lambda item: item[1],
            # A theme's query terms are the closest thing it has to identity terms, so
            # they play that role in scoring too.
            identity_terms=theme_watch.query_terms,
            allowlist=effective_allowlist,
            since=since,
        )
        for source, _dropped in deduped[cap:]:
            _drop(source, "over_cap")
        deduped = deduped[:cap]

    _flush_usage_logs(db, pending_logs, theme_watch_id=theme_watch.id, stage_drops=stage_drops)

    new_matches: list[ThemeMatch] = []
    for source, item in deduped:
        match = ThemeMatch(
            theme_watch_id=theme_watch.id,
            source=source,
            source_name=item.source_name,
            title=item.title,
            url=item.url,
            description=item.description,
            published_at=item.published_at,
            full_content=getattr(item, "full_content", None),
        )
        db.add(match)
        new_matches.append(match)

    # Same treatment the company path gets, and it matters more here: a theme match has no
    # company identity to fall back on, so the headline is quite literally all the model
    # would otherwise have to judge relevance from.
    enrich_articles(new_matches, workspace_settings, budget=enrichment_budget)
    db.commit()
    progress.update(current_step="summarizing", articles_total_this_company=len(new_matches))

    created, duplicates_here, triaged_out_here, batch_errors, batch_cancelled = (
        _process_new_theme_matches(
            db,
            ai_client=ai_client,
            workspace_settings=workspace_settings,
            theme_watch=theme_watch,
            new_matches=new_matches,
            progress=progress,
        )
    )
    outcome.matches_created = created
    outcome.duplicates_skipped = duplicates_here
    outcome.triaged_out = triaged_out_here
    outcome.errors.extend(batch_errors)
    outcome.cancelled = batch_cancelled
    return outcome


def _process_new_theme_matches(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    theme_watch: ThemeWatch,
    new_matches: list[ThemeMatch],
    progress: IngestionProgress | None = None,
) -> tuple[int, int, int, list[str], bool]:
    """Mirrors _process_new_articles: batch-embed, dedupe against recent same-theme
    matches, triage, then summarize+extract in one call. No company_mentioned/
    company_mismatch handling — that concept doesn't apply to a theme match (see
    docs/theme-search-planning.html §4.2). Auto-links matched_target_company_id once
    extraction identifies a company that's already tracked (§4.3)."""
    progress = progress or _NULL_PROGRESS
    errors: list[str] = []
    matches_created = 0
    duplicates_skipped = 0
    triaged_out = 0
    cancelled = False

    try:
        embed_inputs = [f"{m.title}\n{_theme_grounding_text(m)}" for m in new_matches]
        vectors, embed_usage = ai_client.embed_texts(embed_inputs)
        _log_usage(db, "embedding", ai_client.embed_model, embed_usage, None)
        for match, vector in zip(new_matches, vectors):
            match.embedding = vector
        db.commit()
    except AIClientError as exc:
        _record_error(errors, progress, f"[theme:{theme_watch.name}] embedding failed: {exc}")

    new_match_ids = {m.id for m in new_matches}
    candidates = (
        db.query(ThemeMatch)
        .filter(
            ThemeMatch.theme_watch_id == theme_watch.id,
            ThemeMatch.embedding.isnot(None),
            ~ThemeMatch.id.in_(new_match_ids),
            or_(ThemeMatch.skip_reason.is_(None), ThemeMatch.skip_reason != "ai_error"),
        )
        .order_by(ThemeMatch.fetched_at.desc())
        .limit(RECENT_ARTICLES_FOR_DEDUPE)
        .all()
    )

    for position, match in enumerate(new_matches):
        if progress.should_cancel():
            cancelled = True
            break

        if match.embedding is not None:
            duplicate = _find_duplicate(
                match, candidates, workspace_settings.mistral_dedupe_similarity_threshold
            )
            if duplicate is not None:
                match.duplicate_of_match_id = duplicate.id
                _skip_theme_match(db, match, "duplicate")
                duplicates_skipped += 1
                candidates.insert(0, match)
                progress.update(articles_processed_this_company=position + 1)
                continue
            candidates.insert(0, match)

        if workspace_settings.mistral_triage_enabled:
            try:
                triage, triage_usage = ai_client.triage_theme_article(
                    offering_description=workspace_settings.offering_description,
                    theme_name=theme_watch.name,
                    query_terms=theme_watch.query_terms,
                    article_title=match.title,
                    article_description=_theme_grounding_text(match),
                    industry=theme_watch.industry,
                    feedback_note=theme_watch.ai_feedback_note,
                    headline_only=match.headline_only,
                )
                _log_usage(db, "triage", ai_client.triage_model, triage_usage, None, commit=False)
            except AIClientError as exc:
                _record_error(
                    errors,
                    progress,
                    f"[theme:{theme_watch.name}] triage failed for {match.url}: {exc} "
                    "(proceeding to full summarization without the cost-saving triage filter)",
                )
                triage = None
            if triage is not None and not triage.relevant:
                _skip_theme_match(db, match, "triaged_out", triage_reason=triage.reason)
                triaged_out += 1
                progress.update(articles_processed_this_company=position + 1)
                continue

        try:
            result, usage = ai_client.summarize_theme_article(
                company_name=workspace_settings.company_name,
                offering_description=workspace_settings.offering_description,
                theme_name=theme_watch.name,
                query_terms=theme_watch.query_terms,
                article_title=match.title,
                article_description=_theme_grounding_text(match),
                industry=theme_watch.industry,
                feedback_note=theme_watch.ai_feedback_note,
                output_language=workspace_settings.main_language,
                headline_only=match.headline_only,
            )
            _log_usage(db, "summarize", ai_client.model, usage, None, commit=False)
        except AIClientError as exc:
            _skip_theme_match(db, match, "ai_error")
            _record_error(
                errors, progress, f"[theme:{theme_watch.name}] summarization failed for {match.url}: {exc}"
            )
            progress.update(articles_processed_this_company=position + 1)
            continue

        match.summary = result.summary
        match.business_relevance = result.business_relevance
        match.supporting_quote = result.supporting_quote
        match.relevance_score = result.relevance_score
        match.signal_type = result.signal_type
        match.confidence = result.confidence
        match.entities = result.entities
        match.extracted_company_name = result.extracted_company_name
        match.prompt_tokens = usage.prompt_tokens
        match.completion_tokens = usage.completion_tokens
        match.total_tokens = usage.total_tokens

        # Auto-link (no user action) whenever the extracted name matches an existing
        # TargetCompany — metadata only, doesn't create a Signal (see §4.3/§1).
        if result.extracted_company_name:
            existing_company = (
                db.query(TargetCompany)
                .filter(func.lower(TargetCompany.name) == result.extracted_company_name.strip().lower())
                .first()
            )
            if existing_company is not None:
                match.matched_target_company_id = existing_company.id

        # Enforced relevance floor (workspace_settings.theme_match_min_relevance_score):
        # until this existed, every match that survived triage was shown regardless of
        # score, even a 1/5 "tangentially related, no outreach angle" one — the score was
        # only ever used for sort order. This is the direct fix for topic templates
        # surfacing generic industry noise instead of company-specific signals. Folded
        # into the same triaged_out counter as the binary triage skip above (it's the
        # same kind of event — the AI judged this not worth surfacing — just decided by
        # score instead of a yes/no call); the row itself keeps a distinct skip_reason so
        # it stays separately queryable.
        if result.relevance_score < workspace_settings.theme_match_min_relevance_score:
            _skip_theme_match(db, match, "low_relevance")
            triaged_out += 1
            progress.update(articles_processed_this_company=position + 1)
            continue

        db.commit()
        matches_created += 1
        progress.update(articles_processed_this_company=position + 1)

    return matches_created, duplicates_skipped, triaged_out, errors, cancelled


def _process_new_articles(
    db: Session,
    *,
    ai_client: AIClient,
    workspace_settings,
    target_company: TargetCompany,
    new_articles: list[Article],
    progress: IngestionProgress | None = None,
) -> tuple[int, int, int, list[str], bool]:
    progress = progress or _NULL_PROGRESS
    errors: list[str] = []
    signals_created = 0
    duplicates_skipped = 0
    triaged_out = 0
    cancelled = False

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
        # Finer-grained checkpoint than the per-company one in run_ingestion() — a batch
        # can be up to max_articles_per_company_per_run articles deep into potentially
        # slow Mistral calls, so this is where a "Stop" click actually takes effect for
        # the company currently being summarized.
        if progress.should_cancel():
            cancelled = True
            break

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
                    industry=target_company.industry,
                    keywords=target_company.keywords,
                    headline_only=article.is_headline_only,
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
                _skip_article(db, article, "triaged_out", triage_reason=triage.reason)
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
                keywords=target_company.keywords,
                # A copy, not the live list: it's mutated below as new signals are
                # created, and the callee must see the state as of *this* call, not
                # whatever the list looks like by the time it's inspected later.
                recent_signals=list(recent_signal_summaries),
                feedback_note=workspace_settings.ai_feedback_note,
                output_language=workspace_settings.main_language,
                headline_only=article.is_headline_only,
            )
            _log_usage(db, "summarize", ai_client.model, usage, target_company.id, commit=False)
        except AIClientError as exc:
            _skip_article(db, article, "ai_error")
            _record_error(
                errors, progress, f"[{target_company.name}] summarization failed for {article.url}: {exc}"
            )
            progress.update(articles_processed_this_company=position + 1)
            continue

        if not result.company_mentioned:
            # Grounding (news_query.article_mentions_company) and triage both already
            # try to catch this, but the model gets a final say with the full article
            # text in front of it — trust it over fabricating a signal for a company
            # the article doesn't actually cover (see
            # docs/ingestion-reliability-planning.html §5, Fix 3).
            _skip_article(db, article, "company_mismatch")
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

    return signals_created, duplicates_skipped, triaged_out, errors, cancelled


class ArticleNotEligibleError(Exception):
    """Raised when promote_skipped_article is asked to process an article outside the
    one state a manual override applies to."""


def promote_skipped_article(db: Session, article: Article) -> Signal:
    """Admin override for an article the cheap triage pre-filter marked irrelevant (see
    TriageResult in ai_client.py): forces the full summarization call the triage gate
    would otherwise have skipped, and creates a Signal from the result. Only valid for
    skip_reason == "triaged_out" — duplicates and ai_errors have their own remediation
    paths, and an article that already has a Signal has nothing left to promote."""
    if article.skip_reason != "triaged_out":
        raise ArticleNotEligibleError(
            f"Article is not in the triaged-out state (skip_reason={article.skip_reason!r})"
        )

    app_settings = get_settings()
    workspace_settings = get_or_create_workspace_settings(db)
    ai_client = AIClient(
        api_key=resolve_mistral_api_key(workspace_settings, app_settings),
        model=workspace_settings.mistral_model,
        triage_model=workspace_settings.mistral_triage_model,
        embed_model=workspace_settings.mistral_embed_model,
        max_requests_per_second=app_settings.mistral_max_requests_per_second,
        max_retries=app_settings.mistral_max_retries,
    )
    target_company = db.get(TargetCompany, article.target_company_id)
    recent_signal_summaries = _recent_signal_context(db, target_company.id)

    result, usage = ai_client.summarize_article(
        company_name=workspace_settings.company_name,
        offering_description=workspace_settings.offering_description,
        target_company_name=target_company.name,
        article_title=article.title,
        article_description=_grounding_text(article),
        industry=target_company.industry,
        keywords=target_company.keywords,
        recent_signals=recent_signal_summaries,
        feedback_note=workspace_settings.ai_feedback_note,
        output_language=workspace_settings.main_language,
        headline_only=article.is_headline_only,
    )
    _log_usage(db, "summarize", ai_client.model, usage, target_company.id, commit=False)

    if not result.company_mentioned:
        _skip_article(db, article, "company_mismatch")
        raise ArticleNotEligibleError(
            "The AI determined this article isn't actually about the target company"
        )

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
    article.skip_reason = None
    article.triage_reason = None
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


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


def _skip_article(
    db: Session, article: Article, reason: str, *, triage_reason: str | None = None
) -> None:
    """Commits the skip_reason together with any pending (not-yet-committed) usage-log
    rows added earlier for this article, instead of a separate commit per write."""
    article.skip_reason = reason
    article.triage_reason = triage_reason
    db.commit()


def _theme_grounding_text(match: ThemeMatch) -> str:
    """Same rule as _grounding_text: prefer real body text when a provider or enrichment
    supplied one, fall back to the description otherwise. ThemeMatch had no full_content
    field at all while Google News RSS was the only theme provider."""
    text = match.full_content or match.description or ""
    if len(text) > FULL_TEXT_TRUNCATE:
        text = text[:FULL_TEXT_TRUNCATE].rsplit(" ", 1)[0] + "..."
    return text


def _skip_theme_match(
    db: Session, match: ThemeMatch, reason: str, *, triage_reason: str | None = None
) -> None:
    match.skip_reason = reason
    match.triage_reason = triage_reason
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
    article: Article | ThemeMatch, candidates: list, threshold: float
) -> Article | ThemeMatch | None:
    """Duck-typed on .embedding — reused as-is for both Article (per-company path) and
    ThemeMatch (per-theme path, see docs/theme-search-planning.html §6)."""
    norm_a = vector_norm(article.embedding)
    best: Article | ThemeMatch | None = None
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
