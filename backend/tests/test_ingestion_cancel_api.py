import uuid

from app.models.ingestion_run import STATUS_COMPLETED, STATUS_RUNNING, TRIGGER_MANUAL
from app.services.ingestion_runs import create_run


def _signup(client, email, name="User"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": name, "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_cancel_requires_admin(client, db_session):
    admin_headers = _signup(client, "admin@proair.com")
    user_headers = _signup(client, "user@proair.com")
    run = create_run(db_session, trigger=TRIGGER_MANUAL)

    resp = client.post(f"/ingestion/runs/{run.id}/cancel", headers=user_headers)
    assert resp.status_code == 403

    resp = client.post(f"/ingestion/runs/{run.id}/cancel", headers=admin_headers)
    assert resp.status_code == 200


def test_cancel_sets_cancel_requested_on_running_run(client, db_session):
    admin_headers = _signup(client, "admin@proair.com")
    run = create_run(db_session, trigger=TRIGGER_MANUAL)
    assert run.cancel_requested is False

    resp = client.post(f"/ingestion/runs/{run.id}/cancel", headers=admin_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["cancel_requested"] is True
    assert body["status"] == STATUS_RUNNING

    db_session.refresh(run)
    assert run.cancel_requested is True


def test_cancel_is_idempotent_for_an_already_requested_run(client, db_session):
    admin_headers = _signup(client, "admin@proair.com")
    run = create_run(db_session, trigger=TRIGGER_MANUAL)

    first = client.post(f"/ingestion/runs/{run.id}/cancel", headers=admin_headers)
    second = client.post(f"/ingestion/runs/{run.id}/cancel", headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_cancel_missing_run_returns_404(client):
    admin_headers = _signup(client, "admin@proair.com")
    missing_id = uuid.uuid4()

    resp = client.post(f"/ingestion/runs/{missing_id}/cancel", headers=admin_headers)
    assert resp.status_code == 404


def test_cancel_already_finished_run_returns_409(client, db_session):
    admin_headers = _signup(client, "admin@proair.com")
    run = create_run(db_session, trigger=TRIGGER_MANUAL)
    run.status = STATUS_COMPLETED
    db_session.commit()

    resp = client.post(f"/ingestion/runs/{run.id}/cancel", headers=admin_headers)
    assert resp.status_code == 409
