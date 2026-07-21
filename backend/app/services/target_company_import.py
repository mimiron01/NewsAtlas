"""CSV bulk-import for target companies (see docs/v1-release-roadmap.html §3 — the
Salesforce Account export use case). Column mapping is resolved by the caller (the
frontend's column-mapping preview step) rather than guessed here, so this module only
deals with parsing the resolved columns and applying the same create/dedupe rules the
single-add endpoint uses.
"""
import csv
import io
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.target_company import TargetCompany
from app.schemas.target_company import (
    TargetCompanyCreate,
    TargetCompanyImportError,
    TargetCompanyImportSkipped,
)

# Expected scale is small (a Salesforce Account list export), so a hard ceiling well
# above any real workspace's needs is enough to stop an oversized file from mass-creating
# companies that would then blow through news-provider rate limits on the next
# ingestion run.
MAX_IMPORT_ROWS = 500

# Classic CSV-injection prefixes: if this file is ever re-exported and opened in
# Excel/Sheets, a cell starting with one of these is interpreted as a formula by the
# spreadsheet app. Neutralize on the way in with a leading apostrophe rather than only
# relying on whoever re-exports it later to know to sanitize on the way out.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


class CsvImportError(Exception):
    """File-level problem (bad encoding, missing column, too many rows) that fails the
    whole import before any row is processed — distinct from a per-row error/skip."""


def _sanitize_csv_value(value: str) -> str:
    stripped = value.strip()
    if stripped and stripped[0] in _FORMULA_PREFIXES:
        return f"'{stripped}"
    return stripped


def parse_target_company_csv(
    content: bytes, *, name_column: str, industry_column: str | None
) -> list[dict[str, str | None]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("File is not valid UTF-8 text") from exc

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    if name_column not in fieldnames:
        raise CsvImportError(f"Column {name_column!r} not found in the CSV header")
    if industry_column is not None and industry_column not in fieldnames:
        raise CsvImportError(f"Column {industry_column!r} not found in the CSV header")

    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise CsvImportError(
            f"CSV has {len(rows)} rows, exceeding the {MAX_IMPORT_ROWS}-row import limit"
        )
    return rows


def import_target_companies(
    db: Session,
    *,
    rows: list[dict[str, str | None]],
    name_column: str,
    industry_column: str | None,
    created_by: uuid.UUID,
) -> tuple[list[TargetCompany], list[TargetCompanyImportSkipped], list[TargetCompanyImportError]]:
    """Applies the same name-required/case-insensitive-dedupe rules the single-add
    endpoint uses, per row. Rows are independent: one invalid row is reported and
    skipped rather than failing the whole batch, and a row is either fully created
    (added to the session) or reported — never both."""
    existing_names = {name.lower() for (name,) in db.query(TargetCompany.name).all()}
    created: list[TargetCompany] = []
    skipped: list[TargetCompanyImportSkipped] = []
    errors: list[TargetCompanyImportError] = []
    seen_in_batch: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # row 1 is the header row
        raw_name = (row.get(name_column) or "").strip()
        if not raw_name:
            errors.append(TargetCompanyImportError(row=idx, reason="Missing company name"))
            continue
        name = _sanitize_csv_value(raw_name)

        raw_industry = row.get(industry_column) if industry_column else None
        industry = _sanitize_csv_value(raw_industry) if raw_industry else None

        key = name.lower()
        if key in existing_names or key in seen_in_batch:
            skipped.append(TargetCompanyImportSkipped(row=idx, name=name, reason="duplicate"))
            continue

        try:
            validated = TargetCompanyCreate(name=name, industry=industry, keywords=[])
        except ValidationError as exc:
            errors.append(TargetCompanyImportError(row=idx, reason=exc.errors()[0]["msg"]))
            continue

        company = TargetCompany(
            name=validated.name,
            keywords=validated.keywords,
            industry=validated.industry,
            created_by=created_by,
        )
        db.add(company)
        seen_in_batch.add(key)
        created.append(company)

    db.flush()
    return created, skipped, errors
