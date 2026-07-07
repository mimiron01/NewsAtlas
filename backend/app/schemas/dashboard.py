from pydantic import BaseModel

from app.schemas.signal import SignalResponse
from app.schemas.signal_todo import SignalTodoWithContext


class DashboardSummary(BaseModel):
    top_signals: list[SignalResponse]
    new_signal_count: int
    favorite_count: int
    recent_favorites: list[SignalResponse]
    open_todo_count: int
    open_todos: list[SignalTodoWithContext]
