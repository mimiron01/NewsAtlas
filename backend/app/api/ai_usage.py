from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.ai_usage_log import AIUsageLog
from app.models.target_company import TargetCompany
from app.models.user import User
from app.schemas.ai_usage import AIUsageByCallType, AIUsageByTargetCompany, AIUsageSummary

router = APIRouter(prefix="/ai-usage", tags=["ai-usage"])


def _usage_sum_columns():
    return (
        func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0),
        func.coalesce(func.sum(AIUsageLog.completion_tokens), 0),
        func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
    )


@router.get("/summary", response_model=AIUsageSummary)
def get_usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AIUsageSummary:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(AIUsageLog).filter(AIUsageLog.created_at >= since)
    prompt_sum, completion_sum, total_sum = _usage_sum_columns()

    by_call_type_rows = (
        base.with_entities(AIUsageLog.call_type, func.count(AIUsageLog.id), prompt_sum, completion_sum, total_sum)
        .group_by(AIUsageLog.call_type)
        .all()
    )
    by_call_type = [
        AIUsageByCallType(
            call_type=call_type,
            call_count=count,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=t_tokens,
        )
        for call_type, count, p_tokens, c_tokens, t_tokens in by_call_type_rows
    ]
    # Overall totals are just a sum over the per-call-type rows already fetched above,
    # rather than a second identical aggregate query against the same filtered rows.
    total_calls = sum(row.call_count for row in by_call_type)
    prompt_tokens = sum(row.prompt_tokens for row in by_call_type)
    completion_tokens = sum(row.completion_tokens for row in by_call_type)
    total_tokens = sum(row.total_tokens for row in by_call_type)

    by_company_rows = (
        base.outerjoin(TargetCompany, AIUsageLog.target_company_id == TargetCompany.id)
        .with_entities(AIUsageLog.target_company_id, TargetCompany.name, total_sum)
        .group_by(AIUsageLog.target_company_id, TargetCompany.name)
        .order_by(total_sum.desc())
        .all()
    )
    by_target_company = [
        AIUsageByTargetCompany(target_company_id=tc_id, target_company_name=name, total_tokens=t_tokens)
        for tc_id, name, t_tokens in by_company_rows
    ]

    return AIUsageSummary(
        period_days=days,
        total_calls=total_calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        by_call_type=by_call_type,
        by_target_company=by_target_company,
    )
