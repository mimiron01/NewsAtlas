import uuid

from pydantic import BaseModel


class AIUsageByCallType(BaseModel):
    call_type: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AIUsageByTargetCompany(BaseModel):
    target_company_id: uuid.UUID | None
    target_company_name: str | None
    total_tokens: int


class AIUsageSummary(BaseModel):
    period_days: int
    total_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    by_call_type: list[AIUsageByCallType]
    by_target_company: list[AIUsageByTargetCompany]
