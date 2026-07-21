from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.article import Article
from app.models.signal import Signal, SignalStatus
from app.models.signal_favorite import SignalFavorite
from app.models.signal_todo import SignalTodo
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardSummary
from app.schemas.signal_todo import SignalTodoWithContext
from app.services.signal_queries import base_signal_query, scope_to_follows, signal_row_to_response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TOP_SIGNALS_LIMIT = 8
RECENT_FAVORITES_LIMIT = 5
OPEN_TODOS_LIMIT = 5


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

    # Two separate "skipped" systems (see docs/v1-release-roadmap.html §2.4), surfaced
    # here so "where did my skipped stuff go" has one visible answer instead of being
    # buried in a filter dropdown / an admin-only settings tab a user has to know exists.
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

    return DashboardSummary(
        top_signals=top_signals,
        new_signal_count=new_signal_count,
        favorite_count=favorite_count,
        recent_favorites=recent_favorites,
        open_todo_count=open_todo_count,
        open_todos=open_todos,
        dismissed_signal_count=dismissed_signal_count,
        skipped_article_count=skipped_article_count,
    )
