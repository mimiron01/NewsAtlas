import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Query as SAQuery, Session

from app.models.target_company import TargetCompany
from app.models.theme_follow import ThemeFollow
from app.models.theme_match import ThemeMatch
from app.models.theme_match_favorite import ThemeMatchFavorite
from app.models.theme_watch import ThemeWatch
from app.models.user import User, UserRole
from app.schemas.theme_match import ThemeMatchResponse

# Mirrors signal_queries.py's scope_to_follows/base_signal_query/signal_row_to_response,
# including the per-user favorite annotation (see SignalFavorite/ThemeMatchFavorite). No
# open-todo annotation — that concept doesn't have a theme-match equivalent.


def scope_to_theme_follows(query: SAQuery, db: Session, user: User, *, include_muted: bool) -> SAQuery:
    follows = db.query(ThemeFollow.theme_watch_id).filter(ThemeFollow.user_id == user.id)
    if not include_muted:
        follows = follows.filter(ThemeFollow.is_muted.is_(False))
    return query.filter(ThemeWatch.id.in_(follows.scalar_subquery()))


def base_theme_match_query(db: Session, current_user: User) -> SAQuery:
    """Joins ThemeWatch (required) and TargetCompany (optional outer join, since
    matched_target_company_id is nullable — most matches have no linked company), and
    annotates each row with the current user's favorite flag via a correlated subquery,
    same shape as base_signal_query."""
    favorited_expr = (
        db.query(ThemeMatchFavorite.id)
        .filter(
            ThemeMatchFavorite.theme_match_id == ThemeMatch.id,
            ThemeMatchFavorite.user_id == current_user.id,
        )
        .correlate(ThemeMatch)
        .exists()
    )
    return (
        db.query(ThemeMatch, ThemeWatch, TargetCompany, favorited_expr)
        .join(ThemeWatch, ThemeMatch.theme_watch_id == ThemeWatch.id)
        .outerjoin(TargetCompany, ThemeMatch.matched_target_company_id == TargetCompany.id)
    )


def theme_match_row_to_response(
    match: ThemeMatch,
    theme: ThemeWatch,
    matched_company: TargetCompany | None,
    is_favorited: bool = False,
) -> ThemeMatchResponse:
    return ThemeMatchResponse(
        id=match.id,
        status=match.status,
        summary=match.summary,
        business_relevance=match.business_relevance,
        supporting_quote=match.supporting_quote,
        relevance_score=match.relevance_score,
        signal_type=match.signal_type,
        confidence=match.confidence,
        entities=match.entities,
        fetched_at=match.fetched_at,
        title=match.title,
        url=match.url,
        source_name=match.source_name,
        published_at=match.published_at,
        source=match.source,
        headline_only=match.headline_only,
        theme_watch_id=theme.id,
        theme_watch_name=theme.name,
        extracted_company_name=match.extracted_company_name,
        matched_target_company_id=matched_company.id if matched_company is not None else None,
        matched_target_company_name=matched_company.name if matched_company is not None else None,
        is_favorited=bool(is_favorited),
    )


def accessible_theme_match_row(
    db: Session, match_id: uuid.UUID, current_user: User, scope: str | None = None
):
    query = base_theme_match_query(db, current_user).filter(ThemeMatch.id == match_id)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = scope_to_theme_follows(query, db, current_user, include_muted=True)
    return query.first()


def get_accessible_theme_match(db: Session, match_id: uuid.UUID, current_user: User) -> ThemeMatch:
    """Raises 404 (not 403) if the match doesn't exist or the user doesn't follow its
    theme — same anti-existence-leak convention as get_accessible_signal."""
    row = accessible_theme_match_row(db, match_id, current_user)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme match not found")
    return row[0]
