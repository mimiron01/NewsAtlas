import os
import uuid
from datetime import datetime, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://newsatlas:newsatlas@localhost:5432/newsatlas_test"
)
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("ENABLE_RATE_LIMITING", "false")
os.environ.setdefault("SIGNUP_INVITE_CODE", "test-invite-code")
os.environ.setdefault("JWT_SECRET", "test-only-secret-key-not-for-production-use-0123456789")
os.environ.setdefault("APP_SECRET_KEY", "test-only-app-secret-key-not-for-production-0123456789")
# bcrypt's real cost factor (12 rounds) buys tests no security value but dominates the
# runtime of every test that signs up a user; a low round count is fine here since
# test JWTs/passwords never protect anything real.
os.environ.setdefault("BCRYPT_ROUNDS", "4")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.theme_follow import ThemeFollow
from app.services.workspace_settings import get_or_create_workspace_settings

# A few modules open their own DB session directly (background tasks, the
# scheduler) instead of going through the `get_db` FastAPI dependency. For test
# isolation these need to be routed through the same per-test connection as
# `db_session` below, or they won't see data written earlier in the same test.
import app.api.target_companies as _target_companies_module
import app.main as _main_module
import app.services.ingestion_runs as _ingestion_runs_module
import app.services.scheduler as _scheduler_module

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)

_SESSION_LOCAL_MODULES = [
    _main_module,
    _target_companies_module,
    _ingestion_runs_module,
    _scheduler_module,
]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create the schema once for the whole test session instead of per test.

    Individual tests get isolation from `db_session`'s rollback below, not
    from recreating tables, so this only pays the DDL cost once.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    """Yield a session bound to a connection-level transaction that is always
    rolled back, so each test is isolated without dropping/recreating tables.

    `join_transaction_mode="create_savepoint"` lets app code's own `db.commit()`
    calls release/reopen a SAVEPOINT instead of ending the outer transaction
    (the standard SQLAlchemy "join a session to an external transaction"
    pattern for test suites).
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")

    originals = [module.SessionLocal for module in _SESSION_LOCAL_MODULES]
    for module in _SESSION_LOCAL_MODULES:
        module.SessionLocal = session_factory

    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        for module, original in zip(_SESSION_LOCAL_MODULES, originals):
            module.SessionLocal = original
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def pytest_collection_modifyitems(items):
    """Auto-mark any test using the `client`/`db_session` fixtures as `integration`,
    so `pytest -m "not integration"` runs the pure-unit subset without needing every
    test to be annotated by hand."""
    for item in items:
        if "client" in item.fixturenames or "db_session" in item.fixturenames:
            item.add_marker(pytest.mark.integration)


# --- Shared test helpers -----------------------------------------------------
#
# These were previously copy-pasted (with small, incidental variations) across a
# dozen-plus test files. Centralizing them here means an auth-flow change only
# needs updating in one place, and new tests don't need to reinvent signup
# boilerplate.


def signup(client, email="rep@proair.com", name="Rep", invite_code="test-invite-code"):
    """Sign up a user and return (auth headers, user id) for tests that need the id."""
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": name, "invite_code": invite_code},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = uuid.UUID(client.get("/auth/me", headers=headers).json()["id"])
    return headers, user_id


def auth_headers(client, email="rep@proair.com"):
    """Sign up a user and return just their auth headers."""
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def admin_headers(client):
    """The first signup becomes admin automatically (see app/api/auth.py)."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "admin@proair.com",
            "password": "password123",
            "name": "Admin",
            "invite_code": "test-invite-code",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def user_headers(client):
    """Sign up an admin first, so the second signup is a regular, non-admin user."""
    client.post(
        "/auth/signup",
        json={
            "email": "admin@proair.com",
            "password": "password123",
            "name": "Admin",
            "invite_code": "test-invite-code",
        },
    )
    resp = client.post(
        "/auth/signup",
        json={
            "email": "user@proair.com",
            "password": "password123",
            "name": "User",
            "invite_code": "test-invite-code",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def enable_backfill(db_session, **overrides):
    settings = get_or_create_workspace_settings(db_session)
    settings.newsdata_enabled = True
    settings.newsdata_backfill_days = 30
    for key, value in overrides.items():
        setattr(settings, key, value)
    db_session.commit()
    return settings


def follow_company(db_session, user_id, target_company_id) -> None:
    db_session.add(CompanyFollow(user_id=user_id, target_company_id=target_company_id))
    db_session.commit()


def follow_theme(db_session, user_id, theme_watch_id, is_muted=False) -> None:
    db_session.add(ThemeFollow(user_id=user_id, theme_watch_id=theme_watch_id, is_muted=is_muted))
    db_session.commit()


def make_signal(db_session, company_name="Acme Corp"):
    """Create a target company + article + signal, the minimal chain a Signal needs."""
    target_company = TargetCompany(name=company_name, keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title="Acme raises $10M",
        url=f"https://example.com/{company_name.lower().replace(' ', '-')}",
        description="desc",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    signal = Signal(
        article_id=article.id,
        summary="Acme raised funding",
        business_relevance="They have budget now",
        outreach_snippet_email="Congrats on the raise...",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal
