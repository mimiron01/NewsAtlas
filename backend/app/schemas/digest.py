from pydantic import BaseModel


class DigestRunResult(BaseModel):
    users_emailed: int
    signals_included: int
    errors: list[str]
