from pydantic import BaseModel

from app.schemas.signal import SignalResponse
from app.schemas.signal_todo import SignalTodoWithContext
from app.schemas.theme_match import ThemeMatchResponse


class DashboardSummary(BaseModel):
    top_signals: list[SignalResponse]
    new_signal_count: int
    favorite_count: int
    recent_favorites: list[SignalResponse]
    open_todo_count: int
    open_todos: list[SignalTodoWithContext]
    # Counts backing the "N skipped — review them" dashboard card (see
    # docs/v1-release-roadmap.html §2.4) — two separate "skipped" systems today:
    # articles the triage pre-filter never turned into a Signal at all, and Signals a
    # user explicitly dismissed. Both were previously buried with no visibility.
    dismissed_signal_count: int
    skipped_article_count: int
    # Theme-watch equivalents of new_signal_count/top_signals, follow-scoped and
    # mute-respecting the same way. Both are empty/0 for a user who follows no themes, so
    # the frontend can hide the topic UI entirely rather than showing a permanent zero.
    new_theme_match_count: int = 0
    top_theme_matches: list[ThemeMatchResponse] = []
