import json
import logging
import math

import httpx
from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger("newsatlas.ai_client")

_SIGNAL_TYPES = (
    "funding",
    "leadership_change",
    "expansion",
    "hiring_surge",
    "layoffs",
    "product_launch",
    "partnership",
    "competitor_mention",
    "other",
)

_SYSTEM_PROMPT = (
    "You are a sales-intelligence assistant. Given a news article about a company our "
    "sales team is targeting, a description of our own company's offering, and optional "
    "context about recent prior signals for the same target company, respond with a JSON "
    "object containing exactly these keys:\n"
    '- "summary": 2-4 plain-language sentences summarizing the article.\n'
    '- "business_relevance": why this news matters for outreach to the target company, '
    "and how it connects to our offering. If prior-signal context is given, note whether "
    "this continues a trend rather than repeating it as an isolated fact.\n"
    '- "supporting_quote": a short verbatim excerpt (max ~25 words) from the article '
    "description that directly supports business_relevance. Empty string if the "
    "description doesn't contain a usable quote.\n"
    '- "outreach_snippet_email": a short, ready-to-send paragraph referencing the news, '
    "suitable for a cold outreach email.\n"
    '- "outreach_snippet_linkedin": a shorter, more casual version suitable for a LinkedIn '
    "connection message.\n"
    '- "outreach_call_opener": a single spoken sentence a rep could use to open a cold call '
    "referencing this news.\n"
    '- "relevance_score": integer 1-5. 5 = a clear, immediate buying trigger directly tied '
    "to our offering that warrants outreach today; 1 = tangentially related background "
    "news with no clear outreach angle.\n"
    f'- "signal_type": one of {list(_SIGNAL_TYPES)}.\n'
    '- "confidence": one of ["low", "medium", "high"] — how confident you are that '
    "business_relevance is accurately grounded in the article text.\n"
    '- "entities": an object with any of these keys you can confidently extract from the '
    'article: "amount" (string, e.g. a funding/deal size), "people" (array of strings, '
    '"name (title)"), "tags" (array of short lowercase keyword strings). Omit keys you '
    "can't confidently fill; use {} if none apply.\n"
    "Respond with ONLY the JSON object and no other text."
)

_RETRY_PROMPT = (
    "Your previous response was not valid JSON matching the required schema. Reply again "
    "with ONLY a JSON object containing exactly the required keys."
)

_TRIAGE_SYSTEM_PROMPT = (
    "You are a fast relevance filter for a sales-intelligence pipeline. Given a news "
    "article about a company our sales team is targeting and a description of our own "
    "company's offering, decide whether the article is worth a full analysis. Respond "
    "with ONLY a JSON object: "
    '{"relevant": true|false, "reason": "<max 10 words>"}. '
    "Answer false only for articles with no plausible business/outreach angle at all "
    "(e.g. pure sports/celebrity/local-interest noise that happened to match a keyword)."
)


class AIClientError(Exception):
    """Raised when the AI provider can't be reached or returns an unusable response."""


class MistralUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AISummaryResult(BaseModel):
    summary: str
    business_relevance: str
    supporting_quote: str = ""
    outreach_snippet_email: str
    outreach_snippet_linkedin: str = ""
    outreach_call_opener: str = ""
    relevance_score: int = 3
    signal_type: str = "other"
    confidence: str = "medium"
    entities: dict = {}

    @field_validator("relevance_score")
    @classmethod
    def _clamp_score(cls, value: int) -> int:
        return max(1, min(5, value))

    @field_validator("signal_type")
    @classmethod
    def _normalize_signal_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower().replace(" ", "_")
        if normalized in _SIGNAL_TYPES:
            return normalized
        logger.warning("Mistral returned unrecognized signal_type %r; coercing to 'other'", value)
        return "other"

    @field_validator("confidence")
    @classmethod
    def _normalize_confidence(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized in ("low", "medium", "high"):
            return normalized
        logger.warning("Mistral returned unrecognized confidence %r; coercing to 'medium'", value)
        return "medium"


class TriageResult(BaseModel):
    relevant: bool
    reason: str = ""


def _sum_usage(a: MistralUsage, b: MistralUsage) -> MistralUsage:
    return MistralUsage(
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
        total_tokens=a.total_tokens + b.total_tokens,
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class AIClient:
    """Thin wrapper around Mistral's chat completions and embeddings APIs.

    Isolated here so the prompt/response contract stays separate from the ingestion
    orchestration, and so a different model provider could be swapped in later.

    Token-usage optimization is a deliberate design constraint, not an afterthought:
    - `triage_article` uses a small/cheap model with a tight token budget to filter out
      low-value articles *before* the expensive `summarize_article` call runs at all.
    - `embed_texts` batches every new article for a target company into one embeddings
      request instead of one call per article.
    - `summarize_article` returns every field a rep needs (score, type, multi-channel
      outreach, entities) from a single call rather than issuing several follow-up calls.
    """

    BASE_URL = "https://api.mistral.ai/v1"
    MAX_ATTEMPTS = 2

    def __init__(
        self,
        api_key: str,
        model: str,
        triage_model: str = "mistral-small-latest",
        embed_model: str = "mistral-embed",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.model = model
        self.triage_model = triage_model
        self.embed_model = embed_model
        self.timeout = timeout

    def summarize_article(
        self,
        *,
        company_name: str,
        offering_description: str,
        target_company_name: str,
        article_title: str,
        article_description: str | None,
        industry: str | None = None,
        recent_signals: list[str] | None = None,
        feedback_note: str | None = None,
    ) -> tuple[AISummaryResult, MistralUsage]:
        if not self.api_key:
            raise AIClientError("MISTRAL_API_KEY is not configured")

        context_lines = [
            f"Our company: {company_name}",
            f"Our offering: {offering_description or '(not provided)'}",
            "",
            f"Target company: {target_company_name}",
        ]
        if industry:
            context_lines.append(f"Target industry: {industry}")
        context_lines.append(f"Article title: {article_title}")
        context_lines.append(
            f"Article description: {article_description or '(no description available)'}"
        )
        if recent_signals:
            context_lines.append("")
            context_lines.append("Recent prior signals for this target company (most recent first):")
            context_lines.extend(f"- {line}" for line in recent_signals)
        if feedback_note:
            context_lines.append("")
            context_lines.append(f"Steering note from user feedback: {feedback_note}")

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(context_lines)},
        ]

        last_error: Exception | None = None
        # Every attempt that reaches Mistral is a real, billed call — including ones that
        # come back malformed — so usage is accumulated across attempts rather than only
        # keeping the last one, to keep ai_usage_logs an accurate cost record.
        cumulative_usage = MistralUsage()
        for _ in range(self.MAX_ATTEMPTS):
            content: str | None = None
            try:
                content, usage = self._chat(self.model, messages, temperature=0.3)
                cumulative_usage = _sum_usage(cumulative_usage, usage)
                data = json.loads(content)
                return AISummaryResult.model_validate(data), cumulative_usage
            except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if content is not None:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": _RETRY_PROMPT})

        raise AIClientError(f"Mistral summarization failed after retry: {last_error}")

    def triage_article(
        self,
        *,
        company_name: str,
        offering_description: str,
        target_company_name: str,
        article_title: str,
        article_description: str | None,
    ) -> tuple[TriageResult, MistralUsage]:
        """Cheap pre-filter using the small model. Failures fail open (treat as relevant)
        so a triage-model hiccup never silently drops a potentially valuable signal —
        it just costs one extra full-model call instead."""
        if not self.api_key:
            raise AIClientError("MISTRAL_API_KEY is not configured")

        messages = [
            {"role": "system", "content": _TRIAGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Our offering: {offering_description or '(not provided)'}\n"
                    f"Target company: {target_company_name}\n"
                    f"Article title: {article_title}\n"
                    f"Article description: {article_description or '(no description available)'}"
                ),
            },
        ]
        try:
            content, usage = self._chat(
                self.triage_model, messages, temperature=0.0, max_tokens=60
            )
            data = json.loads(content)
            return TriageResult.model_validate(data), usage
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as exc:
            raise AIClientError(f"Mistral triage failed: {exc}")

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], MistralUsage]:
        """Batches all given texts into a single embeddings request."""
        if not self.api_key:
            raise AIClientError("MISTRAL_API_KEY is not configured")
        if not texts:
            return [], MistralUsage()

        headers = self._headers()
        payload = {"model": self.embed_model, "input": texts}
        try:
            response = httpx.post(
                f"{self.BASE_URL}/embeddings", headers=headers, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            body = response.json()
            # Sort by the response's own index rather than trusting array order, so a
            # provider that reorders results doesn't silently attach the wrong embedding
            # to the wrong article.
            items = sorted(body["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AIClientError(f"Mistral embeddings request failed: {exc}")
        usage_body = body.get("usage", {})
        usage = MistralUsage(
            prompt_tokens=usage_body.get("prompt_tokens", 0),
            completion_tokens=0,
            total_tokens=usage_body.get("total_tokens", usage_body.get("prompt_tokens", 0)),
        )
        return vectors, usage

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        return _cosine_similarity(a, b)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int | None = None,
    ) -> tuple[str, MistralUsage]:
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = httpx.post(
            f"{self.BASE_URL}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        usage_body = body.get("usage", {})
        usage = MistralUsage(
            prompt_tokens=usage_body.get("prompt_tokens", 0),
            completion_tokens=usage_body.get("completion_tokens", 0),
            total_tokens=usage_body.get("total_tokens", 0),
        )
        return content, usage
