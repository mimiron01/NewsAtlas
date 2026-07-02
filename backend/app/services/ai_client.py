import json

import httpx
from pydantic import BaseModel, ValidationError

_SYSTEM_PROMPT = (
    "You are a sales-intelligence assistant. Given a news article about a company our "
    "sales team is targeting, and a description of our own company's offering, respond "
    "with a JSON object containing exactly these keys:\n"
    '- "summary": 2-4 plain-language sentences summarizing the article.\n'
    '- "business_relevance": why this news matters for outreach to the target company, '
    "and how it connects to our offering.\n"
    '- "outreach_snippet": a short, ready-to-send paragraph referencing the news, suitable '
    "for a cold outreach email or LinkedIn message.\n"
    "Respond with ONLY the JSON object and no other text."
)

_RETRY_PROMPT = (
    "Your previous response was not valid JSON matching the required schema. Reply again "
    "with ONLY a JSON object containing exactly the keys: summary, business_relevance, "
    "outreach_snippet."
)


class AIClientError(Exception):
    """Raised when the AI provider can't be reached or returns an unusable response."""


class AISummaryResult(BaseModel):
    summary: str
    business_relevance: str
    outreach_snippet: str


class AIClient:
    """Thin wrapper around Mistral's chat completions API.

    Isolated here so the summarization prompt/response contract stays separate from
    the ingestion orchestration, and so a different model provider could be swapped
    in later.
    """

    BASE_URL = "https://api.mistral.ai/v1/chat/completions"
    MAX_ATTEMPTS = 2

    def __init__(self, api_key: str, model: str, timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def summarize_article(
        self,
        *,
        company_name: str,
        offering_description: str,
        target_company_name: str,
        article_title: str,
        article_description: str | None,
    ) -> AISummaryResult:
        if not self.api_key:
            raise AIClientError("MISTRAL_API_KEY is not configured")

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Our company: {company_name}\n"
                    f"Our offering: {offering_description or '(not provided)'}\n\n"
                    f"Target company: {target_company_name}\n"
                    f"Article title: {article_title}\n"
                    f"Article description: {article_description or '(no description available)'}"
                ),
            },
        ]

        last_error: Exception | None = None
        for _ in range(self.MAX_ATTEMPTS):
            content: str | None = None
            try:
                content = self._call(messages)
                data = json.loads(content)
                return AISummaryResult.model_validate(data)
            except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if content is not None:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": _RETRY_PROMPT})

        raise AIClientError(f"Mistral summarization failed after retry: {last_error}")

    def _call(self, messages: list[dict]) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        response = httpx.post(self.BASE_URL, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"]
