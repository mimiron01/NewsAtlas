from datetime import datetime, timezone

from app.models.ingestion_run import STATUS_COMPLETED, STATUS_FAILED, STATUS_RUNNING, IngestionRun
from app.models.target_company import TargetCompany
from app.schemas.ingestion import IngestionRunResult
from app.services.ingestion import run_ingestion
from app.services.ingestion_runs import (
    ProgressTracker,
    create_run,
    execute_ingestion_run,
    progress_percent,
)
from app.services.news_client import NewsArticle

from tests.test_ingestion import FailingAIClient, FakeAIClient


class _RecordingProgress:
    def __init__(self):
        self.state: dict[str, object] = {}
        self.updates: list[dict[str, object]] = []
        self.errors: list[str] = []

    def update(self, **fields):
        self.updates.append(fields)
        self.state.update(fields)

    def append_error(self, message: str):
        self.errors.append(message)


class FakeNewsClient:
    def __init__(self, articles_by_company: dict[str, list[NewsArticle]]):
        self.articles_by_company = articles_by_company

    def fetch_articles(self, *, name, keywords, since):
        return self.articles_by_company.get(name, [])


def _company(db_session, name: str) -> TargetCompany:
    tc = TargetCompany(name=name, keywords=[name.split()[0]], is_active=True)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    return tc


def _article(title, url):
    return NewsArticle(
        source_name="Reuters", title=title, url=url, description="desc",
        published_at=datetime.now(timezone.utc),
    )


def test_run_ingestion_reports_company_progress(db_session):
    _company(db_session, "Acme Corp")
    _company(db_session, "Globex Corp")
    news = FakeNewsClient(
        {
            "Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")],
            "Globex Corp": [],
        }
    )
    progress = _RecordingProgress()

    run_ingestion(db_session, news_client=news, ai_client=FakeAIClient(), progress=progress)

    assert progress.state["companies_total"] == 2
    assert progress.state["companies_processed"] == 2
    # Companies are processed in query order; the last one touched should be the final
    # company_processed update.
    company_name_updates = [u["current_company_name"] for u in progress.updates if "current_company_name" in u]
    assert company_name_updates == ["Acme Corp", "Globex Corp"]
    assert progress.errors == []


def test_run_ingestion_reports_article_progress_within_a_company(db_session):
    _company(db_session, "Acme Corp")
    news = FakeNewsClient(
        {
            "Acme Corp": [
                _article("Acme raises $10M", "https://example.com/acme-1"),
                _article("Acme opens office", "https://example.com/acme-2"),
            ]
        }
    )
    progress = _RecordingProgress()

    run_ingestion(db_session, news_client=news, ai_client=FakeAIClient(), progress=progress)

    assert progress.state["articles_total_this_company"] == 2
    assert progress.state["articles_processed_this_company"] == 2
    assert progress.state["current_step"] == "summarizing"


def test_run_ingestion_appends_errors_live_as_they_happen(db_session):
    _company(db_session, "Acme Corp")
    news = FakeNewsClient(
        {"Acme Corp": [_article("Acme raises $10M", "https://example.com/acme-funding")]}
    )
    progress = _RecordingProgress()

    run_ingestion(db_session, news_client=news, ai_client=FailingAIClient(), progress=progress)

    assert len(progress.errors) == 1
    assert "summarization failed" in progress.errors[0]


def test_progress_percent_caps_below_100_while_running():
    run = IngestionRun(trigger="manual", status=STATUS_RUNNING, companies_total=4, companies_processed=1,
                        articles_total_this_company=2, articles_processed_this_company=1)
    # (1 + 0.5) / 4 = 37%
    assert progress_percent(run) == 37


def test_progress_percent_is_100_once_finished():
    run = IngestionRun(trigger="manual", status=STATUS_COMPLETED, companies_total=4, companies_processed=4)
    assert progress_percent(run) == 100


def test_progress_percent_is_zero_with_no_active_companies():
    run = IngestionRun(trigger="scheduled", status=STATUS_RUNNING, companies_total=0)
    assert progress_percent(run) == 0


def test_execute_ingestion_run_marks_row_completed(db_session, monkeypatch):
    run = create_run(db_session, trigger="manual")
    monkeypatch.setattr(
        "app.services.ingestion_runs.SessionLocal", lambda: db_session
    )
    fake_result = IngestionRunResult(
        target_companies_processed=1, articles_fetched=1, articles_new=1,
        signals_created=1, errors=[],
    )
    monkeypatch.setattr(
        "app.services.ingestion_runs.run_ingestion", lambda db, progress=None: fake_result
    )
    # execute_ingestion_run closes the session it opens (SessionLocal()) — patched here to
    # return db_session directly so this test can inspect the row afterward without a
    # second, unrelated connection.
    monkeypatch.setattr(db_session, "close", lambda: None)

    execute_ingestion_run(run.id)

    db_session.refresh(run)
    assert run.status == STATUS_COMPLETED
    assert run.signals_created == 1
    assert run.finished_at is not None


def test_execute_ingestion_run_marks_row_failed_on_unexpected_exception(db_session, monkeypatch):
    run = create_run(db_session, trigger="manual")
    monkeypatch.setattr("app.services.ingestion_runs.SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    def _boom(db, progress=None):
        raise RuntimeError("db exploded")

    monkeypatch.setattr("app.services.ingestion_runs.run_ingestion", _boom)

    execute_ingestion_run(run.id)

    db_session.refresh(run)
    assert run.status == STATUS_FAILED
    assert run.fatal_error == "db exploded"


def test_progress_tracker_append_error_accumulates(db_session):
    run = create_run(db_session, trigger="manual")
    tracker = ProgressTracker(db_session, run.id)

    tracker.append_error("first problem")
    tracker.append_error("second problem")

    db_session.refresh(run)
    assert run.errors == ["first problem", "second problem"]
