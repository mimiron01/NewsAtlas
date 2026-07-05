from pydantic import BaseModel


class IngestionRunResult(BaseModel):
    target_companies_processed: int
    articles_fetched: int
    articles_new: int
    signals_created: int
    duplicates_skipped: int = 0
    triaged_out: int = 0
    errors: list[str]
