import pytest

from app.services.ai_client import AIClient, AIClientError, MistralUsage, cosine_similarity


def _client():
    return AIClient(api_key="fake-key", model="mistral-large-latest", triage_model="mistral-small-latest")


def _full_response(**overrides):
    data = {
        "summary": "s",
        "business_relevance": "r",
        "supporting_quote": "q",
        "outreach_snippet_email": "email",
        "outreach_snippet_linkedin": "linkedin",
        "outreach_call_opener": "call",
        "relevance_score": 4,
        "signal_type": "funding",
        "confidence": "high",
        "entities": {"amount": "$10M"},
    }
    data.update(overrides)
    return data


def _usage():
    return MistralUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)


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
    import json

    client = _client()
    monkeypatch.setattr(
        client, "_chat", lambda model, messages, **kw: (json.dumps(_full_response()), _usage())
    )
    result, usage = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.summary == "s"
    assert result.business_relevance == "r"
    assert result.outreach_snippet_email == "email"
    assert result.outreach_snippet_linkedin == "linkedin"
    assert result.outreach_call_opener == "call"
    assert result.relevance_score == 4
    assert result.signal_type == "funding"
    assert result.confidence == "high"
    assert result.entities == {"amount": "$10M"}
    assert usage.total_tokens == 150


def test_summarize_article_defaults_to_english_language_directive(monkeypatch):
    import json

    client = _client()
    captured_messages = {}

    def fake_chat(model, messages, **kw):
        captured_messages["messages"] = messages
        return json.dumps(_full_response()), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    system_content = captured_messages["messages"][0]["content"]
    assert "in English" in system_content


def test_summarize_article_honors_output_language(monkeypatch):
    import json

    client = _client()
    captured_messages = {}

    def fake_chat(model, messages, **kw):
        captured_messages["messages"] = messages
        return json.dumps(_full_response()), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
        output_language="de",
    )
    system_content = captured_messages["messages"][0]["content"]
    assert "in German" in system_content
    assert "regardless of what language" in system_content


def test_summarize_article_clamps_out_of_range_score(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (json.dumps(_full_response(relevance_score=99)), _usage()),
    )
    result, _usage_out = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.relevance_score == 5


def test_summarize_article_normalizes_unknown_signal_type(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (
            json.dumps(_full_response(signal_type="not_a_real_type")),
            _usage(),
        ),
    )
    result, _usage_out = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.signal_type == "other"


def test_summarize_article_retries_then_succeeds(monkeypatch):
    import json

    client = _client()
    responses = iter(
        [
            ("not json at all", _usage()),
            (json.dumps(_full_response()), _usage()),
        ]
    )
    monkeypatch.setattr(client, "_chat", lambda model, messages, **kw: next(responses))

    result, _usage_out = client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.summary == "s"


def test_summarize_article_fails_after_max_attempts(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_chat", lambda model, messages, **kw: ("still not json", _usage()))

    with pytest.raises(AIClientError, match="failed after retry"):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_summarize_article_rejects_missing_keys(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client, "_chat", lambda model, messages, **kw: (json.dumps({"summary": "s"}), _usage())
    )

    with pytest.raises(AIClientError):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_summarize_article_includes_industry_and_context_in_prompt(monkeypatch):
    import json

    client = _client()
    captured_messages = []

    def fake_chat(model, messages, **kw):
        captured_messages.append(messages)
        return json.dumps(_full_response()), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.summarize_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
        industry="Manufacturing",
        recent_signals=["Acme hired a new VP of Sales last month."],
        feedback_note="Deprioritize: layoffs",
    )
    user_content = captured_messages[0][1]["content"]
    assert "Manufacturing" in user_content
    assert "Acme hired a new VP of Sales" in user_content
    assert "Deprioritize: layoffs" in user_content


def test_triage_article_relevant(monkeypatch):
    import json

    client = _client()
    monkeypatch.setattr(
        client,
        "_chat",
        lambda model, messages, **kw: (json.dumps({"relevant": True, "reason": "funding news"}), _usage()),
    )
    result, usage = client.triage_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert result.relevant is True
    assert usage.total_tokens == 150


def test_triage_article_not_relevant(monkeypatch):
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
    result, _usage_out = client.triage_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme's team wins local softball league",
        article_description="Nothing business relevant here",
    )
    assert result.relevant is False


def test_triage_article_uses_small_model(monkeypatch):
    client = _client()
    captured = {}

    def fake_chat(model, messages, **kw):
        captured["model"] = model
        captured["max_tokens"] = kw.get("max_tokens")
        import json

        return json.dumps({"relevant": True, "reason": "ok"}), _usage()

    monkeypatch.setattr(client, "_chat", fake_chat)
    client.triage_article(
        company_name="ProAir",
        offering_description="HVAC services",
        target_company_name="Acme",
        article_title="Acme raises funding",
        article_description="Acme raised $10M",
    )
    assert captured["model"] == "mistral-small-latest"
    assert captured["max_tokens"] is not None and captured["max_tokens"] <= 100


def test_embed_texts_requires_api_key():
    client = AIClient(api_key="", model="mistral-large-latest")
    with pytest.raises(AIClientError, match="MISTRAL_API_KEY"):
        client.embed_texts(["hello"])


def test_embed_texts_empty_input_short_circuits():
    client = _client()
    vectors, usage = client.embed_texts([])
    assert vectors == []
    assert usage.total_tokens == 0


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_accepts_precomputed_norm_a():
    from app.services.ai_client import vector_norm

    a = [3.0, 4.0]
    assert cosine_similarity(a, [3.0, 4.0], norm_a=vector_norm(a)) == pytest.approx(1.0)
