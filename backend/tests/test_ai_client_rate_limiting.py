import httpx
import pytest

from app.services.ai_client import AIClient, AIClientError
from app.services.mistral_rate_limiter import MistralRateLimiter


def _response(status_code: int, *, json_body: dict | None = None, headers: dict | None = None):
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    return httpx.Response(
        status_code, headers=headers or {}, json=json_body or {}, request=request
    )


def _chat_ok_body():
    return {
        "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _client(*, max_retries: int = 5, sleeps: list | None = None):
    # A very fast limiter (no meaningful pacing delay) so these tests only measure the
    # retry/backoff behavior, not rate-limiter pacing, and never touch the process-wide
    # shared limiter (which other test modules may have already configured differently).
    limiter = MistralRateLimiter(max_requests_per_second=100_000)
    return AIClient(
        api_key="fake-key",
        model="mistral-large-latest",
        max_retries=max_retries,
        rate_limiter=limiter,
        sleep=(sleeps.append if sleeps is not None else lambda _seconds: None),
    )


def test_post_retries_once_on_429_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _response(429, headers={"retry-after": "0"})
        return _response(200, json_body=_chat_ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    sleeps: list[float] = []
    client = _client(sleeps=sleeps)

    content, usage = client._chat("mistral-large-latest", [], temperature=0.0)

    assert content == "{}"
    assert usage.total_tokens == 2
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_post_honors_retry_after_header(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _response(429, headers={"retry-after": "7"})
        return _response(200, json_body=_chat_ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    sleeps: list[float] = []
    client = _client(sleeps=sleeps)

    client._chat("mistral-large-latest", [], temperature=0.0)

    assert len(sleeps) == 1
    # retry-after is the floor; a little jitter is added on top but it should never sleep less.
    assert sleeps[0] >= 7.0


def test_post_uses_exponential_backoff_without_retry_after_header(monkeypatch):
    def fake_post(url, **kwargs):
        return _response(429)

    monkeypatch.setattr(httpx, "post", fake_post)
    sleeps: list[float] = []
    client = _client(max_retries=3, sleeps=sleeps)

    with pytest.raises(httpx.HTTPStatusError):
        client._post("https://api.mistral.ai/v1/chat/completions", {})

    assert len(sleeps) == 3
    # Roughly doubling each time (base=1s): ~1, ~2, ~4, each with up to 10% jitter.
    assert 1.0 <= sleeps[0] < 1.1
    assert 2.0 <= sleeps[1] < 2.2
    assert 4.0 <= sleeps[2] < 4.4


def test_post_gives_up_after_max_retries(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _response(429)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(max_retries=2, sleeps=[])

    with pytest.raises(httpx.HTTPStatusError):
        client._post("https://api.mistral.ai/v1/chat/completions", {})

    assert len(calls) == 3  # 1 initial attempt + 2 retries


def test_post_retries_on_5xx(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _response(503)
        return _response(200, json_body=_chat_ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(sleeps=[])

    content, _usage = client._chat("mistral-large-latest", [], temperature=0.0)
    assert content == "{}"
    assert len(calls) == 2


def test_post_does_not_retry_non_retryable_4xx(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _response(401, json_body={"message": "invalid API key"})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(sleeps=[])

    with pytest.raises(httpx.HTTPStatusError):
        client._post("https://api.mistral.ai/v1/chat/completions", {})

    assert len(calls) == 1


def test_post_retries_on_network_error_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset", request=httpx.Request("POST", url))
        return _response(200, json_body=_chat_ok_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(sleeps=[])

    content, _usage = client._chat("mistral-large-latest", [], temperature=0.0)
    assert content == "{}"
    assert len(calls) == 2


def test_summarize_article_wraps_exhausted_rate_limit_as_client_error(monkeypatch):
    def fake_post(url, **kwargs):
        return _response(429, headers={"retry-after": "0"})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(max_retries=1, sleeps=[])

    with pytest.raises(AIClientError, match="Mistral summarization failed"):
        client.summarize_article(
            company_name="ProAir",
            offering_description="HVAC services",
            target_company_name="Acme",
            article_title="Acme raises funding",
            article_description="Acme raised $10M",
        )


def test_embed_texts_retries_on_429(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _response(429, headers={"retry-after": "0"})
        return _response(
            200,
            json_body={
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client(sleeps=[])

    vectors, usage = client.embed_texts(["hello"])
    assert vectors == [[1.0, 0.0]]
    assert usage.total_tokens == 3
    assert len(calls) == 2


def test_every_attempt_goes_through_the_rate_limiter(monkeypatch):
    def fake_post(url, **kwargs):
        return _response(429, headers={"retry-after": "0"})

    monkeypatch.setattr(httpx, "post", fake_post)

    acquire_calls = []
    limiter = MistralRateLimiter(max_requests_per_second=100_000)
    original_acquire = limiter.acquire
    limiter.acquire = lambda: (acquire_calls.append(1), original_acquire())[-1]

    client = AIClient(
        api_key="fake-key",
        model="mistral-large-latest",
        max_retries=2,
        rate_limiter=limiter,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client._post("https://api.mistral.ai/v1/chat/completions", {})

    assert len(acquire_calls) == 3  # 1 initial attempt + 2 retries, each paced
