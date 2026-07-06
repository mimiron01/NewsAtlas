from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import (
    admin,
    ai_usage,
    auth,
    digest,
    ingestion,
    news_usage,
    settings,
    signals,
    target_companies,
)
from app.core.body_limit import MaxBodySizeMiddleware
from app.core.config import assert_secure_for_production, get_settings
from app.core.limiter import limiter
from app.core.logging_config import configure_logging
from app.db.session import SessionLocal
from app.models.workspace_settings import WorkspaceSettings
from app.services import scheduler

configure_logging()

app_settings = get_settings()
assert_secure_for_production(app_settings)


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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(MaxBodySizeMiddleware, max_bytes=app_settings.max_request_body_bytes)

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
app.include_router(ai_usage.router)
app.include_router(news_usage.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
