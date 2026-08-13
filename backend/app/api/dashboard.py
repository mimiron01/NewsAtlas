from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.article import Article
from app.models.signal import Signal, SignalStatus
from app.models.signal_favorite import SignalFavorite
from app.models.signal_todo import SignalTodo
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardSummary
from app.schemas.signal_todo import SignalTodoWithContext
from app.services.signal_queries import base_signal_query, scope_to_follows, signal_row_to_response
from app.services.theme_match_queries import (
    base_theme_match_query,
    scope_to_theme_follows,
    theme_match_row_to_response,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TOP_SIGNALS_LIMIT = 5
RECENT_FAVORITES_LIMIT = 5
OPEN_TODOS_LIMIT = 5
# Smaller than TOP_SIGNALS_LIMIT: topics are a secondary panel on the dashboard, with the
# full list one click away on the Themes page.
TOP_THEME_MATCHES_LIMIT = 5


@router.get("", response_model=DashboardSummary)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    followed_query = scope_to_follows(
        base_signal_query(db, current_user), db, current_user, include_muted=False
    )

    top_rows = (
        followed_query.filter(Signal.status.in_([SignalStatus.NEW, SignalStatus.REVIEWED]))
        .order_by(Signal.relevance_score.desc().nullslast(), Signal.created_at.desc())
        .limit(TOP_SIGNALS_LIMIT)
        .all()
    )
    top_signals = [signal_row_to_response(*row) for row in top_rows]

    new_signal_count = followed_query.filter(Signal.status == SignalStatus.NEW).count()

    # Surfaced here so "where did my archived/skipped stuff go" has one visible answer
    # instead of being buried in a filter dropdown / an admin-only settings tab a user
    # has to know exists (see docs/archive-dismiss-ux-planning.html).
    archived_signal_count = followed_query.filter(Signal.status == SignalStatus.ARCHIVED).count()
    dismissed_signal_count = followed_query.filter(Signal.status == SignalStatus.DISMISSED).count()
    # Triaged-out articles never became a Signal, so they can't be follow-scoped the same
    # way — and the list endpoint that shows them (/articles/skipped) is admin-only, so a
    # non-admin gets 0 rather than a count for a queue they have no way to open.
    skipped_article_count = (
        db.query(Article).filter(Article.skip_reason == "triaged_out").count()
        if current_user.role == UserRole.ADMIN
        else 0
    )

    favorite_count = (
        db.query(SignalFavorite).filter(SignalFavorite.user_id == current_user.id).count()
    )

    favorites_query = scope_to_follows(
        base_signal_query(db, current_user), db, current_user, include_muted=False
    ).join(SignalFavorite, SignalFavorite.signal_id == Signal.id)
    favorite_rows = (
        favorites_query.filter(SignalFavorite.user_id == current_user.id)
        .order_by(SignalFavorite.created_at.desc())
        .limit(RECENT_FAVORITES_LIMIT)
        .all()
    )
    recent_favorites = [signal_row_to_response(*row) for row in favorite_rows]

    open_todo_count = (
        db.query(SignalTodo)
        .filter(SignalTodo.user_id == current_user.id, SignalTodo.is_done.is_(False))
        .count()
    )

    open_todos_query = (
        db.query(SignalTodo, Article, TargetCompany)
        .join(Signal, SignalTodo.signal_id == Signal.id)
        .join(Article, Signal.article_id == Article.id)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
        .filter(SignalTodo.user_id == current_user.id, SignalTodo.is_done.is_(False))
    )
    open_todos_query = scope_to_follows(open_todos_query, db, current_user, include_muted=True)
    open_todo_rows = (
        open_todos_query.order_by(SignalTodo.created_at.desc()).limit(OPEN_TODOS_LIMIT).all()
    )
    open_todos = [
        SignalTodoWithContext(
            id=todo.id,
            signal_id=todo.signal_id,
            text=todo.text,
            is_done=todo.is_done,
            completed_at=todo.completed_at,
            created_at=todo.created_at,
            article_title=article.title,
            target_company_name=target_company.name,
        )
        for todo, article, target_company in open_todo_rows
    ]

    # Theme matches, scoped and filtered exactly like the signal queries above: only themes
    # this user follows, muted follows excluded, skipped rows (duplicate/triaged_out/
    # ai_error) never shown. A user following no themes gets 0/[] and the frontend hides
    # the topic tiles entirely.
    theme_query = scope_to_theme_follows(
        base_theme_match_query(db, current_user), db, current_user, include_muted=False
    ).filter(ThemeMatch.skip_reason.is_(None))
    new_theme_match_count = theme_query.filter(ThemeMatch.status == SignalStatus.NEW).count()
    top_theme_rows = (
        theme_query.filter(ThemeMatch.status.in_([SignalStatus.NEW, SignalStatus.REVIEWED]))
        .order_by(ThemeMatch.relevance_score.desc().nullslast(), ThemeMatch.fetched_at.desc())
        .limit(TOP_THEME_MATCHES_LIMIT)
        .all()
    )
    top_theme_matches = [theme_match_row_to_response(*row) for row in top_theme_rows]

    return DashboardSummary(
        top_signals=top_signals,
        new_theme_match_count=new_theme_match_count,
        top_theme_matches=top_theme_matches,
        new_signal_count=new_signal_count,
        favorite_count=favorite_count,
        recent_favorites=recent_favorites,
        open_todo_count=open_todo_count,
        open_todos=open_todos,
        archived_signal_count=archived_signal_count,
        dismissed_signal_count=dismissed_signal_count,
        skipped_article_count=skipped_article_count,
    )
