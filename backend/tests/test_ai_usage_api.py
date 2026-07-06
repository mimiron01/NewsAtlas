from app.models.ai_usage_log import AIUsageLog
from app.models.target_company import TargetCompany


def _auth_headers(client, email="rep@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_usage_summary_empty(client, db_session):
    headers = _auth_headers(client)
    resp = client.get("/ai-usage/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["total_tokens"] == 0
    assert body["by_call_type"] == []
    assert body["by_target_company"] == []


def test_usage_summary_aggregates_by_call_type_and_company(client, db_session):
    headers = _auth_headers(client)
    tc = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)

    db_session.add_all(
        [
            AIUsageLog(
                call_type="embedding", model="mistral-embed",
                prompt_tokens=10, completion_tokens=0, total_tokens=10,
                target_company_id=tc.id,
            ),
            AIUsageLog(
                call_type="triage", model="mistral-small-latest",
                prompt_tokens=20, completion_tokens=5, total_tokens=25,
                target_company_id=tc.id,
            ),
            AIUsageLog(
                call_type="triage", model="mistral-small-latest",
                prompt_tokens=15, completion_tokens=5, total_tokens=20,
                target_company_id=tc.id,
            ),
            AIUsageLog(
                call_type="summarize", model="mistral-large-latest",
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
                target_company_id=None,
            ),
        ]
    )
    db_session.commit()

    resp = client.get("/ai-usage/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_calls"] == 4
    assert body["prompt_tokens"] == 145
    assert body["completion_tokens"] == 60
    assert body["total_tokens"] == 205

    by_call_type = {row["call_type"]: row for row in body["by_call_type"]}
    assert by_call_type["embedding"]["call_count"] == 1
    assert by_call_type["embedding"]["total_tokens"] == 10
    assert by_call_type["triage"]["call_count"] == 2
    assert by_call_type["triage"]["total_tokens"] == 45
    assert by_call_type["summarize"]["call_count"] == 1
    assert by_call_type["summarize"]["total_tokens"] == 150

    by_company = {row["target_company_name"]: row["total_tokens"] for row in body["by_target_company"]}
    assert by_company["Acme Corp"] == 55
    # Rows with no target_company_id (e.g. a company deleted since) still show up, grouped.
    assert by_company[None] == 150


def test_usage_summary_requires_auth(client):
    resp = client.get("/ai-usage/summary")
    assert resp.status_code == 401
