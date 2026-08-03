import json

import pytest

from app.services.ai_client import AIClientError, SuggestedTopic, TemplateExample

from tests.test_ai_client import _client, _usage


def _suggestion_response(**overrides):
    data = {
        "suggestions": [
            {
                "name": "Automotive",
                "query_terms": ["EV battery", "automotive"],
                "exclude_terms": ["insurance"],
                "rationale": "Fits your EV parts supply offering.",
                "based_on_template_id": "11111111-1111-1111-1111-111111111111",
            }
        ]
    }
    data.update(overrides)
    return data


def test_suggest_topics_requires_api_key():
    client = _client()
    client.api_key = ""
    with pytest.raises(AIClientError, match="MISTRAL_API_KEY"):
        client.suggest_topics(offering_description="HVAC services", available_templates=[])


def test_suggest_topics_returns_grounded_suggestions(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client, "_chat", lambda model, messages, **kw: (json.dumps(_suggestion_response()), _usage())
    )
    templates = [
        TemplateExample(
            id="11111111-1111-1111-1111-111111111111",
            name="Automotive",
            description="EV/battery news",
            category="Industry",
            query_terms=["automotive", "EV"],
            exclude_terms=["insurance"],
        )
    ]
    suggestions, usage = client.suggest_topics(
        offering_description="We sell EV battery components",
        available_templates=templates,
        existing_topic_names=["Fintech"],
    )
    assert len(suggestions) == 1
    assert isinstance(suggestions[0], SuggestedTopic)
    assert suggestions[0].name == "Automotive"
    assert suggestions[0].based_on_template_id == "11111111-1111-1111-1111-111111111111"
    assert usage.total_tokens == 150


def test_suggest_topics_null_template_id_becomes_none(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (
            json.dumps(_suggestion_response(suggestions=[{
                "name": "Niche Topic",
                "query_terms": ["term"],
                "exclude_terms": [],
                "rationale": "Nothing in the library fits.",
                "based_on_template_id": None,
            }])),
            _usage(),
        ),
    )
    suggestions, _usage_out = client.suggest_topics(
        offering_description="Something unusual", available_templates=[]
    )
    assert suggestions[0].based_on_template_id is None


def test_suggest_topics_prompt_includes_template_library_and_exclusions():
    """The prompt itself (not just the response parsing) should carry the grounding
    context — this is what makes the suggestions actually grounded rather than just
    happening to look similar. Asserts on the constructed message content."""
    client = _client()
    captured = {}

    def fake_chat(model, messages, **kw):
        captured["messages"] = messages
        return json.dumps({"suggestions": []}), _usage()

    client._chat = fake_chat
    templates = [
        TemplateExample(
            id="abc",
            name="Automotive",
            description="EV/battery news",
            category="Industry",
            query_terms=["automotive"],
            exclude_terms=[],
        )
    ]
    client.suggest_topics(
        offering_description="We sell EV parts",
        available_templates=templates,
        existing_topic_names=["Already Tracked Topic"],
    )
    user_content = captured["messages"][1]["content"]
    assert "Automotive" in user_content
    assert "Already Tracked Topic" in user_content
