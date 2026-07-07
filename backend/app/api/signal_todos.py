import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.article import Article
from app.models.signal import Signal
from app.models.signal_todo import SignalTodo
from app.models.target_company import TargetCompany
from app.models.user import User
from app.schemas.signal_todo import (
    SignalTodoCreate,
    SignalTodoResponse,
    SignalTodoUpdate,
    SignalTodoWithContext,
)
from app.services.signal_queries import get_accessible_signal, scope_to_follows

router = APIRouter(tags=["signal-todos"])


def _get_own_todo(db: Session, todo_id: uuid.UUID, current_user: User) -> SignalTodo:
    todo = (
        db.query(SignalTodo)
        .filter(SignalTodo.id == todo_id, SignalTodo.user_id == current_user.id)
        .first()
    )
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo


@router.get("/signals/{signal_id}/todos", response_model=list[SignalTodoResponse])
def list_signal_todos(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SignalTodoResponse]:
    get_accessible_signal(db, signal_id, current_user)
    todos = (
        db.query(SignalTodo)
        .filter(SignalTodo.signal_id == signal_id, SignalTodo.user_id == current_user.id)
        .order_by(SignalTodo.created_at.asc())
        .all()
    )
    return [SignalTodoResponse.model_validate(todo) for todo in todos]


@router.post(
    "/signals/{signal_id}/todos",
    response_model=SignalTodoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_todo(
    signal_id: uuid.UUID,
    payload: SignalTodoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalTodoResponse:
    get_accessible_signal(db, signal_id, current_user)
    todo = SignalTodo(signal_id=signal_id, user_id=current_user.id, text=payload.text)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return SignalTodoResponse.model_validate(todo)


@router.patch("/todos/{todo_id}", response_model=SignalTodoResponse)
def update_todo(
    todo_id: uuid.UUID,
    payload: SignalTodoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalTodoResponse:
    todo = _get_own_todo(db, todo_id, current_user)
    if payload.text is not None:
        todo.text = payload.text
    if payload.is_done is not None:
        todo.is_done = payload.is_done
        todo.completed_at = datetime.now(timezone.utc) if payload.is_done else None
    db.commit()
    db.refresh(todo)
    return SignalTodoResponse.model_validate(todo)


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    todo = _get_own_todo(db, todo_id, current_user)
    db.delete(todo)
    db.commit()


@router.get("/todos", response_model=list[SignalTodoWithContext])
def list_my_todos(
    open_only: bool | None = Query(default=None, alias="open"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SignalTodoWithContext]:
    query = (
        db.query(SignalTodo, Article, TargetCompany)
        .join(Signal, SignalTodo.signal_id == Signal.id)
        .join(Article, Signal.article_id == Article.id)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
        .filter(SignalTodo.user_id == current_user.id)
    )
    query = scope_to_follows(query, db, current_user, include_muted=True)
    if open_only is True:
        query = query.filter(SignalTodo.is_done.is_(False))
    elif open_only is False:
        query = query.filter(SignalTodo.is_done.is_(True))
    rows = query.order_by(SignalTodo.created_at.desc()).all()
    return [
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
        for todo, article, target_company in rows
    ]
