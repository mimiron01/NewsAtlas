import pytest

from app.services.ai_client import AIClient, AIClientError, ThemeArticleResult

from tests.test_ai_client import _client, _usage


def _theme_response(**overrides):
    data = {
        "extracted_company_name": "Acme Corp",
        "summary": "s",
        "business_relevance": "r",
        "supporting_quote": "q",
        "relevance_score": 4,
        "signal_type": "funding",
        "confidence": "high",
        "entities": {"amount": "$10M"},
    }
    data.update(overrides)
    return data


def test_summarize_theme_article_success(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client, "_chat", lambda model, messages, **kw: (json.dumps(_theme_response()), _usage())
    )
    result, usage = client.summarize_theme_article(
        company_name="ProAir",
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery", "Series B"],
        article_title="Acme Corp raises funding",
        article_description="Acme Corp raised $10M",
    )
    assert isinstance(result, ThemeArticleResult)
    assert result.extracted_company_name == "Acme Corp"
    assert result.summary == "s"
    assert result.relevance_score == 4
    assert usage.total_tokens == 150


def test_summarize_theme_article_null_company_becomes_none(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (json.dumps(_theme_response(extracted_company_name=None)), _usage()),
    )
    result, _usage_out = client.summarize_theme_article(
        company_name="ProAir",
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery"],
        article_title="EV sales up 20% industry-wide",
        article_description="Broad industry trend piece.",
    )
    assert result.extracted_company_name is None


def test_summarize_theme_article_blank_company_becomes_none(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (json.dumps(_theme_response(extracted_company_name="  ")), _usage()),
    )
    result, _usage_out = client.summarize_theme_article(
        company_name="ProAir",
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery"],
        article_title="EV sales up 20% industry-wide",
        article_description="Broad industry trend piece.",
    )
    assert result.extracted_company_name is None


def test_summarize_theme_article_includes_theme_context_in_prompt(monkeypatch):
    import json

    client = _client()
    captured_messages = []

    def fake_chat(model, messages, **kw):
        captured_messages.append(messages)
        return json.dumps(_theme_response()), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.summarize_theme_article(
        company_name="ProAir",
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery", "Series B"],
        article_title="Acme Corp raises funding",
        article_description="Acme Corp raised $10M",
        industry="Manufacturing",
    )
    user_content = captured_messages[0][1]["content"]
    assert "Automotive" in user_content
    assert "EV battery" in user_content
    assert "Manufacturing" in user_content


def test_summarize_theme_article_requires_api_key():
    client = AIClient(api_key="", model="mistral-large-latest")
    with pytest.raises(AIClientError, match="MISTRAL_API_KEY"):
        client.summarize_theme_article(
            company_name="ProAir",
            offering_description="HVAC services",
            theme_name="Automotive",
            query_terms=["EV battery"],
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_triage_theme_article_relevant(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (json.dumps({"relevant": True, "reason": "funding news"}), _usage()),
    )
    result, usage = client.triage_theme_article(
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery"],
        article_title="Acme Corp raises funding",
        article_description="Acme Corp raised $10M",
    )
    assert result.relevant is True
    assert usage.total_tokens == 150


def test_triage_theme_article_not_relevant(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (
            json.dumps({"relevant": False, "reason": "unrelated sports news"}),
            _usage(),
        ),
    )
    result, _usage_out = client.triage_theme_article(
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery"],
        article_title="Local softball league results",
        article_description="Nothing business relevant here",
    )
    assert result.relevant is False


def test_triage_theme_article_uses_small_model(monkeypatch):
    client = _client()
    captured = {}

    def fake_chat(model, messages, **kw):
        captured["model"] = model
        captured["max_tokens"] = kw.get("max_tokens")
        import json

        return json.dumps({"relevant": True, "reason": "ok"}), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.triage_theme_article(
        offering_description="HVAC services",
        theme_name="Automotive",
        query_terms=["EV battery"],
        article_title="Acme Corp raises funding",
        article_description="Acme Corp raised $10M",
    )
    assert captured["model"] == "mistral-small-latest"
    assert captured["max_tokens"] is not None and captured["max_tokens"] <= 100
