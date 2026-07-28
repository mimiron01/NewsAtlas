import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company_follow import CompanyFollow
from app.models.target_company import TargetCompany
from app.schemas.target_company import TargetCompanyResponse


def get_or_create_company(
    db: Session,
    *,
    name: str,
    keywords: list[str],
    industry: str | None,
    created_by: uuid.UUID,
    google_news_source_allowlist: list[str] | None = None,
) -> TargetCompany:
    """Case-insensitive dedupe by name, shared by self-serve create and admin assignment."""
    existing = (
        db.query(TargetCompany)
        .filter(func.lower(TargetCompany.name) == name.strip().lower())
        .first()
    )
    if existing is not None:
        return existing
    company = TargetCompany(
        name=name,
        keywords=keywords,
        industry=industry,
        created_by=created_by,
        google_news_source_allowlist=google_news_source_allowlist or [],
    )
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
        industry=company.industry,
        is_active=company.is_active,
        google_news_source_allowlist=company.google_news_source_allowlist,
        created_by=company.created_by,
        is_muted=follow.is_muted if follow is not None else None,
        follower_count=follower_count(db, company.id),
        backfilled_at=company.backfilled_at,
    )
