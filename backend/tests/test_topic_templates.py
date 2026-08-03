import json

from app.services.workspace_settings import get_or_create_workspace_settings

from tests.conftest import admin_headers as _admin_headers
from tests.conftest import auth_headers, signup, user_headers

# NOTE: the test DB schema is created via Base.metadata.create_all (see conftest.py),
# not via `alembic upgrade head` — so the seed templates inserted by the
# d4e5f6a7b8c9 migration's data migration never exist in these tests. Every test here
# creates its own template(s) through the admin API instead of assuming pre-seeded rows.


def _create_template(client, headers, **overrides):
    payload = {
        "name": "Automotive",
        "description": "EV/battery news",
        "category": "Industry",
        "query_terms": ["EV battery", "automotive"],
        "exclude_terms": ["insurance"],
    }
    payload.update(overrides)
    resp = client.post("/topic-templates", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Gallery listing -----------------------------------------------------------------


def test_list_topic_templates_returns_active_templates(client):
    admin = _admin_headers(client)
    _create_template(client, admin)

    resp = client.get("/topic-templates", headers=admin)
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "Automotive" in names


def test_list_topic_templates_requires_auth(client):
    resp = client.get("/topic-templates")
    assert resp.status_code == 401


# --- Apply flow ------------------------------------------------------------------------


def test_apply_template_creates_theme_with_template_terms(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin)

    resp = client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=admin)
    assert resp.status_code == 201
    theme = resp.json()
    assert theme["name"] == template["name"]
    assert theme["query_terms"] == template["query_terms"]
    assert theme["exclude_terms"] == template["exclude_terms"]
    assert theme["created_from_template_id"] == template["id"]
    assert theme["follower_count"] == 1


def test_apply_template_respects_overrides(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin)

    resp = client.post(
        f"/topic-templates/{template['id']}/apply",
        json={"name": "My Automotive Watch", "query_terms": ["custom term"]},
        headers=admin,
    )
    assert resp.status_code == 201
    theme = resp.json()
    assert theme["name"] == "My Automotive Watch"
    assert theme["query_terms"] == ["custom term"]
    # exclude_terms wasn't overridden, so it still comes from the template.
    assert theme["exclude_terms"] == template["exclude_terms"]


def test_apply_template_goes_through_duplicate_confirmation(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin)
    headers_b, _ = signup(client, email="b@proair.com")

    first = client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=admin)
    assert first.status_code == 201

    conflict = client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=headers_b)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "duplicate_name"

    merged = client.post(
        f"/topic-templates/{template['id']}/apply",
        json={"confirm_merge": True},
        headers=headers_b,
    )
    assert merged.status_code == 201
    assert merged.json()["id"] == first.json()["id"]


def test_apply_template_respects_active_ceiling(client, db_session):
    admin = _admin_headers(client)
    template = _create_template(client, admin)
    settings = get_or_create_workspace_settings(db_session)
    settings.max_active_theme_watches = 0
    db_session.commit()

    resp = client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=admin)
    assert resp.status_code == 400


def test_apply_nonexistent_template_404s(client):
    headers = auth_headers(client)
    resp = client.post(
        "/topic-templates/00000000-0000-0000-0000-000000000000/apply", json={}, headers=headers
    )
    assert resp.status_code == 404


# --- Admin CRUD --------------------------------------------------------------------


def test_non_admin_cannot_create_template(client):
    headers = user_headers(client)
    resp = client.post(
        "/topic-templates",
        json={"name": "Custom", "query_terms": ["term"]},
        headers=headers,
    )
    assert resp.status_code == 403


def test_admin_can_create_update_and_delete_template(client):
    admin = _admin_headers(client)

    template = _create_template(client, admin, name="Custom Template", category="Custom")
    assert template["is_active"] is True

    update_resp = client.patch(
        f"/topic-templates/{template['id']}", json={"is_active": False}, headers=admin
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False

    # Deactivated templates drop out of the public gallery...
    gallery = client.get("/topic-templates", headers=admin).json()
    assert not any(t["id"] == template["id"] for t in gallery)
    # ...but admins can still see them via the full list.
    all_templates = client.get("/topic-templates/all", headers=admin).json()
    assert any(t["id"] == template["id"] for t in all_templates)

    delete_resp = client.delete(f"/topic-templates/{template['id']}", headers=admin)
    assert delete_resp.status_code == 204


def test_applying_inactive_template_is_rejected(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin, name="Inactive One")
    client.patch(f"/topic-templates/{template['id']}", json={"is_active": False}, headers=admin)

    resp = client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=admin)
    assert resp.status_code == 400


# --- Performance (admin-only) -------------------------------------------------------


def test_template_performance_requires_admin(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin)
    non_admin = user_headers(client)

    resp = client.get(f"/topic-templates/{template['id']}/performance", headers=non_admin)
    assert resp.status_code == 403


def test_template_performance_reflects_adoption_count(client):
    admin = _admin_headers(client)
    template = _create_template(client, admin)

    before = client.get(f"/topic-templates/{template['id']}/performance", headers=admin).json()
    assert before["adoption_count"] == 0

    client.post(f"/topic-templates/{template['id']}/apply", json={}, headers=admin)

    after = client.get(f"/topic-templates/{template['id']}/performance", headers=admin).json()
    assert after["adoption_count"] == 1
    assert after["matches_total"] == 0
    assert after["dismiss_rate"] is None


# --- AI-suggested topics (GET /theme-watches/suggestions) --------------------------


def _enable_ai(db_session, monkeypatch, offering_description="We sell EV parts"):
    settings = get_or_create_workspace_settings(db_session)
    settings.offering_description = offering_description
    db_session.commit()
    monkeypatch.setattr("app.api.theme_watches.resolve_mistral_api_key", lambda ws, app_settings: "fake-key")


def test_suggestions_empty_without_offering_description(client, db_session, monkeypatch):
    headers = auth_headers(client)
    monkeypatch.setattr("app.api.theme_watches.resolve_mistral_api_key", lambda ws, app_settings: "fake-key")
    resp = client.get("/theme-watches/suggestions", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_suggestions_returns_grounded_topics(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_ai(db_session, monkeypatch)

    from app.services.ai_client import MistralUsage

    def fake_chat(self, model, messages, **kw):
        content = json.dumps(
            {
                "suggestions": [
                    {
                        "name": "Automotive",
                        "query_terms": ["EV"],
                        "exclude_terms": [],
                        "rationale": "Matches your offering.",
                        "based_on_template_id": None,
                    }
                ]
            }
        )
        return content, MistralUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    monkeypatch.setattr("app.services.ai_client.AIClient._chat", fake_chat)

    resp = client.get("/theme-watches/suggestions", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Automotive"
    assert body[0]["based_on_template_id"] is None


def test_suggestions_never_creates_a_topic(client, db_session, monkeypatch):
    headers = auth_headers(client)
    _enable_ai(db_session, monkeypatch)
    from app.services.ai_client import MistralUsage

    monkeypatch.setattr(
        "app.services.ai_client.AIClient._chat",
        lambda self, model, messages, **kw: (
            json.dumps({"suggestions": []}),
            MistralUsage(),
        ),
    )
    client.get("/theme-watches/suggestions", headers=headers)
    assert client.get("/theme-watches", headers=headers).json() == []
