import pytest

from app.services.ai_client import AIClient, AIClientError


def _client():
    return AIClient(api_key="fake-key", model="mistral-large-latest")


def test_summarize_article_requires_api_key():
    client = AIClient(api_key="", model="mistral-large-latest")
    with pytest.raises(AIClientError, match="MISTRAL_API_KEY"):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_summarize_article_success_first_attempt(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client,
        "_call",
        lambda messages: '{"summary": "s", "business_relevance": "r", "outreach_snippet": "o"}',
    )
    result = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.summary == "s"
    assert result.business_relevance == "r"
    assert result.outreach_snippet == "o"


def test_summarize_article_retries_then_succeeds(monkeypatch):
    client = _client()
    responses = iter(
        [
            "not json at all",
            '{"summary": "s", "business_relevance": "r", "outreach_snippet": "o"}',
        ]
    )
    monkeypatch.setattr(client, "_call", lambda messages: next(responses))

    result = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.summary == "s"


def test_summarize_article_fails_after_max_attempts(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_call", lambda messages: "still not json")

    with pytest.raises(AIClientError, match="failed after retry"):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_summarize_article_rejects_missing_keys(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_call", lambda messages: '{"summary": "s"}')

    with pytest.raises(AIClientError):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )
