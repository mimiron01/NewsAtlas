from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, settings, target_companies
from app.core.config import get_settings

app_settings = get_settings()

app = FastAPI(title="NewsAtlas API", version="0.1.0")

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
