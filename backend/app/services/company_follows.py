import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company_follow import CompanyFollow
from app.models.target_company import TargetCompany
from app.schemas.target_company import TargetCompanyResponse
from app.services.target_company_terms import sync_keywords


def get_or_create_company(
    db: Session,
    *,
    name: str,
    industry: str | None,
    created_by: uuid.UUID,
    aliases: list[str] | None = None,
    context_terms: list[str] | None = None,
    exclusion_terms: list[str] | None = None,
    keywords: list[str] | None = None,
    google_news_source_allowlist: list[str] | None = None,
    google_news_source_denylist: list[str] | None = None,
    google_news_country: str | None = None,
    google_news_language: str | None = None,
    google_news_require_name_in_title: bool = False,
) -> TargetCompany:
    """Case-insensitive dedupe by name, shared by self-serve create and admin assignment.

    `keywords` is accepted for callers that still think in the old flat list (the CSV
    importer, admin assignment) and is treated as context terms — the role keywords
    actually played in the Google query. It's ignored when context_terms is given
    explicitly, and the derived column is recomputed from the split fields either way
    (see services/target_company_terms.py).

    google_news_source_allowlist keeps None distinct from []: None means "inherit the
    workspace list", [] means "explicitly unrestricted" (§7.6).
    """
    existing = (
        db.query(TargetCompany)
        .filter(func.lower(TargetCompany.name) == name.strip().lower())
        .first()
    )
    if existing is not None:
        return existing
    company = TargetCompany(
        name=name,
        aliases=aliases or [],
        context_terms=context_terms if context_terms is not None else (keywords or []),
        exclusion_terms=exclusion_terms or [],
        industry=industry,
        created_by=created_by,
        google_news_source_allowlist=google_news_source_allowlist,
        google_news_source_denylist=google_news_source_denylist or [],
        google_news_country=google_news_country,
        google_news_language=google_news_language,
        google_news_require_name_in_title=google_news_require_name_in_title,
    )
    sync_keywords(company)
    db.add(company)
    db.flush()
    return company


def get_follow(
    db: Session, user_id: uuid.UUID, target_company_id: uuid.UUID
) -> CompanyFollow | None:
    return (
        db.query(CompanyFollow)
        .filter(
            CompanyFollow.user_id == user_id,
            CompanyFollow.target_company_id == target_company_id,
        )
        .first()
    )


def ensure_follow(
    db: Session,
    *,
    user_id: uuid.UUID,
    target_company_id: uuid.UUID,
    assigned_by: uuid.UUID,
) -> CompanyFollow:
    follow = get_follow(db, user_id, target_company_id)
    if follow is not None:
        return follow
    follow = CompanyFollow(
        user_id=user_id, target_company_id=target_company_id, assigned_by=assigned_by
    )
    db.add(follow)
    db.flush()
    return follow


def follower_count(db: Session, target_company_id: uuid.UUID) -> int:
    return (
        db.query(CompanyFollow)
        .filter(CompanyFollow.target_company_id == target_company_id)
        .count()
    )


def remove_follow(db: Session, user_id: uuid.UUID, target_company_id: uuid.UUID) -> bool:
    """Deletes the follow row; hard-deletes the underlying company if it was the last
    follower. Returns True if the company was hard-deleted."""
    follow = get_follow(db, user_id, target_company_id)
    if follow is None:
        return False
    db.delete(follow)
    db.flush()
    if follower_count(db, target_company_id) == 0:
        company = db.get(TargetCompany, target_company_id)
        if company is not None:
            db.delete(company)
        return True
    return False


def to_response(
    db: Session, company: TargetCompany, follow: CompanyFollow | None
) -> TargetCompanyResponse:
    return TargetCompanyResponse(
        id=company.id,
        name=company.name,
        keywords=company.keywords,
        aliases=company.aliases,
        context_terms=company.context_terms,
        exclusion_terms=company.exclusion_terms,
        industry=company.industry,
        is_active=company.is_active,
        google_news_source_allowlist=company.google_news_source_allowlist,
        google_news_source_denylist=company.google_news_source_denylist,
        google_news_country=company.google_news_country,
        google_news_language=company.google_news_language,
        google_news_require_name_in_title=company.google_news_require_name_in_title,
        created_by=company.created_by,
        is_muted=follow.is_muted if follow is not None else None,
        follower_count=follower_count(db, company.id),
        backfilled_at=company.backfilled_at,
    )
