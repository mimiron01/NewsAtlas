from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class WorkspaceSettings(Base, UUIDPrimaryKeyMixin):
    """Single-row table holding the shared workspace configuration (MVP is single-tenant)."""

    __tablename__ = "workspace_settings"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    offering_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    digest_send_time: Mapped[str] = mapped_column(String(5), nullable=False, default="07:00")
    ingestion_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # Caps how many of a company's newest-fetched (by published_at), genuinely-new
    # articles get embedded/triaged/summarized per ingestion run — bounds AI spend from
    # a single busy company or an overly broad keyword list. 0 disables the cap
    # (unlimited), matching the newsdata_backfill_days "0 = off" convention below.
    max_articles_per_company_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    # Same "0 = unlimited" cap, but for ThemeWatch ingestion (see
    # docs/theme-search-planning.html §9) — a theme's query is inherently broader than a
    # named company's keyword list, so it needs its own budget rather than sharing this one.
    max_articles_per_theme_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    # Ceiling on total active ThemeWatch rows per workspace, enforced in POST
    # /theme-watches — uncapped concurrent themes is a bigger cost blast radius than
    # uncapped companies ever was, since each one fans out into more candidate articles.
    max_active_theme_watches: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Cooldown bookkeeping for the manual trigger endpoints, independent of caller identity
    # (see api/ingestion.py, api/digest.py) — prevents any user from hammering paid external
    # APIs or spamming digest emails by repeatedly calling the manual trigger.
    last_manual_ingestion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_manual_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Same cooldown pattern for the "create signal anyway" override on a triaged-out
    # article (see api/articles.py) — that endpoint forces a full, paid Mistral
    # summarization call per click, so it needs the same anti-looping guard as the
    # other two manual triggers above.
    last_manual_signal_promotion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Short, rule-based steering note derived from dismissed-signal patterns (no LLM call
    # involved in computing it — see services/feedback.py) and injected into future
    # summarization prompts to bias away from categories users keep dismissing.
    ai_feedback_note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # The workspace-wide standard UI/AI language ("en" / "de"). Individual users may
    # override it via users.preferred_language; Mistral is instructed to always write
    # Signal content in this language regardless of the source article's language (see
    # services/ai_client.py).
    main_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # --- Admin-configurable Mistral integration settings (see api/settings.py) ---
    # Empty string means "no in-app override" — the effective key falls back to the
    # MISTRAL_API_KEY env var (app/core/config.py) so existing .env-based deployments
    # keep working until an admin explicitly sets/rotates a key here.
    mistral_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mistral_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-large-latest")
    mistral_triage_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-small-latest")
    mistral_embed_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-embed")
    mistral_triage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mistral_dedupe_similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.90)

    # --- News source toggles + enforced rate limits (see api/settings.py, services/news_rate_limiter.py) ---
    # Every source (including NewsAPI.org, for symmetry) gets an enable toggle and a
    # per-minute/per-day request ceiling that services/news_rate_limiter.py actually
    # enforces before a call goes out, not just an after-the-fact usage log.
    newsapi_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    newsapi_max_requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    google_news_rss_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    google_news_rss_country: Mapped[str] = mapped_column(String(8), nullable=False, default="US")
    google_news_rss_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    # Google publishes no official quota for this feed — this is a self-imposed politeness
    # ceiling to avoid being rate-limited/blocked, not a mapping to a real plan tier.
    google_news_rss_max_requests_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20
    )
    # Appends a Google `when:` freshness operator derived from the run's lookback window
    # (see news_query.google_when_operator). On by default because the feed ranks by
    # all-time relevance and is measurably stale-skewed without it; the toggle exists
    # because Google documents none of this and the operator's interaction with site:
    # clauses can only be confirmed empirically (docs/google-news-quality-planning.html §6.2).
    google_news_time_operator_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Workspace-wide *default* trusted domains for Google News RSS. An entity (company or
    # theme) that sets its own allowlist replaces this list rather than extending it; NULL
    # on the entity means "inherit this" (see TargetCompany.google_news_source_allowlist
    # and docs/google-news-quality-planning.html §7.6).
    google_news_source_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # Domains never accepted anywhere in the workspace, emitted as -site:. Unioned with
    # each entity's own denylist rather than overridden by it — the asymmetry with the
    # allowlist above is deliberate (§7.6).
    google_news_source_denylist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # --- Article enrichment (docs/google-news-quality-planning.html §9) ---
    # The only features in the app that make the backend fetch a URL chosen by a third
    # party, so both are off by default and admin-gated; see services/safe_fetch.py for
    # the SSRF guards that apply when they're on.
    # Resolution turns a news.google.com redirect into the publisher URL (enables
    # cross-source dedupe and durable digest links); snippet fetching additionally reads
    # the publisher's own description so Google News rows stop being headline-only.
    google_news_resolve_urls_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    google_news_fetch_snippets_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Ceilings on enrichment work per ingestion run. 0 = unlimited, same convention as the
    # other caps, but leaving these at 0 with enrichment on is not recommended: a run's
    # duration then depends on how fast other people's web servers are.
    max_enrichment_fetches_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_enrichment_seconds_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=120)

    # "single" issues one compound query per company; "split" additionally issues an
    # identity-only query and merges the results, so a company's context terms can't hide
    # a story that doesn't happen to mention them. Costs one extra request per company
    # per run against a self-imposed 20/min ceiling, so it stays opt-in.
    google_news_query_strategy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="single"
    )

    # Which providers theme watches may use by default (per-theme override lives on
    # ThemeWatch.news_sources). Defaults to Google News RSS alone, which is exactly the
    # behaviour themes had before multi-provider support, so nothing changes until an
    # admin opts in — a broad topical query against a paid provider is the most expensive
    # request shape in the system (docs/google-news-quality-planning.html §11.3).
    theme_news_sources: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=lambda: ["google_news_rss"]
    )
    # Per-source ceiling on how many requests one ingestion run may spend on themes.
    # Companies are processed before themes, so they already have natural priority on a
    # shared daily quota; this stops a themes-heavy workspace draining what's left.
    # 0 = unlimited, matching the convention used by the other caps above.
    max_theme_requests_per_run_per_source: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    newsdata_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Same in-app-override-wins-over-env-var pattern as mistral_api_key (see
    # resolve_newsdata_api_key/get_newsdata_api_key_status below).
    newsdata_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    newsdata_full_content_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    newsdata_use_native_dedupe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 0 disables historical backfill entirely; N > 0 pulls the last N days of archive
    # coverage when a target company is created (see services/newsdata_backfill.py).
    newsdata_backfill_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # An admin sets these to match whatever ceiling their actual paid plan tier allows —
    # the value is a workspace policy, not a code constant, since NewsData.io plans vary.
    newsdata_max_requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    newsdata_max_requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
