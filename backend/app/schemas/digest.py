from pydantic import BaseModel


class DigestRunResult(BaseModel):
    users_emailed: int
    signals_included: int
    # Only counts matches on a follow with include_in_digest=True (opt-in, default off —
    # see docs/topics-ux-improvements-planning.html §4.3), unlike signals_included which
    # counts every new signal regardless of an equivalent opt-in (companies have none).
    theme_matches_included: int = 0
    errors: list[str]
