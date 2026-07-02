from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.digest import DigestRunResult
from app.services.digest import send_daily_digest

router = APIRouter(prefix="/digest", tags=["digest"])


@router.post("/send-now", response_model=DigestRunResult)
def send_now(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> DigestRunResult:
    return send_daily_digest(db)
