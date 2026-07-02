from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ingestion import IngestionRunResult
from app.services.ingestion import run_ingestion

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/run-now", response_model=IngestionRunResult)
def run_now(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> IngestionRunResult:
    return run_ingestion(db)
