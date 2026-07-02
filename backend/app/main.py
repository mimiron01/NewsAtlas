from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, digest, ingestion, settings, signals, target_companies
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.workspace_settings import WorkspaceSettings
from app.services import scheduler

app_settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if app_settings.enable_scheduler:
        db = SessionLocal()
        try:
            workspace_settings = db.query(WorkspaceSettings).first()
            interval_hours = (
                workspace_settings.ingestion_interval_hours
                if workspace_settings
                else app_settings.ingestion_interval_hours
            )
            send_time = (
                workspace_settings.digest_send_time
                if workspace_settings
                else app_settings.digest_send_time
            )
        finally:
            db.close()
        scheduler.start(interval_hours, send_time)
    yield
    if app_settings.enable_scheduler:
        scheduler.shutdown()


app = FastAPI(title="NewsAtlas API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(target_companies.router)
app.include_router(ingestion.router)
app.include_router(signals.router)
app.include_router(digest.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
