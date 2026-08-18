from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.signal import SignalResponse
from app.schemas.signal_todo import SignalTodoWithContext
from app.schemas.theme_match import ThemeMatchResponse


class RecentFavoriteResponse(BaseModel):
    """A single entry in the dashboard's "Zuletzt favorisiert" list. Signal and
    ThemeMatch favorites are two different underlying models with different shapes (an
    internal detail page vs. an external article URL), so this flattens both into one
    small, renderer-friendly shape rather than exposing a Signal/ThemeMatch union."""

    kind: Literal["signal", "theme_match"]
    id: UUID
    title: str
    subtitle: str
    # Set only for kind="theme_match" (opens the article in a new tab); a "signal" entry
    # links internally via /signals/{id} instead, which the frontend builds from id.
    url: str | None
    favorited_at: datetime


class DashboardSummary(BaseModel):
    top_signals: list[SignalResponse]
    new_signal_count: int
    favorite_count: int
    recent_favorites: list[RecentFavoriteResponse]
    open_todo_count: int
    open_todos: list[SignalTodoWithContext]
    # Counts backing the "N archived — view them" dashboard card (see
    # docs/archive-dismiss-ux-planning.html). archived/dismissed are Signals the user has
    # moved out of the active feed; skipped_article_count is a third, admin-only bucket of
    # articles the triage pre-filter never turned into a Signal at all. All three were
    # previously buried with no visibility.
    archived_signal_count: int
    dismissed_signal_count: int
    skipped_article_count: int
    # Theme-watch equivalents of new_signal_count/top_signals, follow-scoped and
    # mute-respecting the same way. Both are empty/0 for a user who follows no themes, so
    # the frontend can hide the topic UI entirely rather than showing a permanent zero.
    new_theme_match_count: int = 0
    top_theme_matches: list[ThemeMatchResponse] = []
