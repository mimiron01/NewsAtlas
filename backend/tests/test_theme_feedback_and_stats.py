import uuid
from datetime import datetime, timedelta, timezone

from app.models.signal import SignalStatus
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.services.feedback import DISMISS_RATE_THRESHOLD, MIN_SAMPLE_SIZE, refresh_theme_feedback_note
from app.services.theme_watch_stats import get_theme_watch_stats

from tests.conftest import auth_headers


def _make_theme(db_session, name="Automotive") -> ThemeWatch:
    theme = ThemeWatch(name=name, query_terms=["EV"])
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def _make_match(
    db_session,
    theme: ThemeWatch,
    *,
    extracted_company_name=None,
    status=SignalStatus.NEW,
    relevance_score=None,
    skip_reason=None,
    fetched_at=None,
) -> ThemeMatch:
    match = ThemeMatch(
        theme_watch_id=theme.id,
        source_name="Example",
        title=f"Article {uuid.uuid4()}",
        url=f"https://example.com/{uuid.uuid4()}",
        extracted_company_name=extracted_company_name,
        status=status,
        relevance_score=relevance_score,
        skip_reason=skip_reason,
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )
    db_session.add(match)
    db_session.commit()
    return match


# --- refresh_theme_feedback_note -----------------------------------------------------


def test_no_note_below_min_sample_size(db_session):
    theme = _make_theme(db_session)
    for _ in range(MIN_SAMPLE_SIZE - 1):
        _make_match(db_session, theme, extracted_company_name="Acme", status=SignalStatus.DISMISSED)
    refresh_theme_feedback_note(db_session, theme)
    assert theme.ai_feedback_note == ""


def test_note_generated_when_dismiss_rate_crosses_threshold(db_session):
    theme = _make_theme(db_session)
    dismissed_count = MIN_SAMPLE_SIZE
    for _ in range(dismissed_count):
        _make_match(db_session, theme, extracted_company_name="Acme", status=SignalStatus.DISMISSED)
    refresh_theme_feedback_note(db_session, theme)
    assert "Acme" in theme.ai_feedback_note
    assert theme.ai_feedback_note != ""


def test_no_note_when_dismiss_rate_below_threshold(db_session):
    theme = _make_theme(db_session)
    # 2 dismissed out of 10 => 20% dismiss rate, below DISMISS_RATE_THRESHOLD.
    assert DISMISS_RATE_THRESHOLD > 0.2
    for _ in range(2):
        _make_match(db_session, theme, extracted_company_name="Acme", status=SignalStatus.DISMISSED)
    for _ in range(8):
        _make_match(db_session, theme, extracted_company_name="Acme", status=SignalStatus.REVIEWED)
    refresh_theme_feedback_note(db_session, theme)
    assert theme.ai_feedback_note == ""


def test_note_generated_when_generic_company_less_matches_frequently_dismissed(db_session):
    # A NULL extracted_company_name means the article was topical/industry news with no
    # single company at its center — exactly the "generic noise, not a company-specific
    # signal" shape users report. This must feed the same learning loop as a named
    # low-value company, not be silently excluded from it.
    theme = _make_theme(db_session)
    for _ in range(MIN_SAMPLE_SIZE):
        _make_match(db_session, theme, extracted_company_name=None, status=SignalStatus.DISMISSED)
    refresh_theme_feedback_note(db_session, theme)
    assert theme.ai_feedback_note != ""
    assert "no specific company" in theme.ai_feedback_note.lower()


def test_no_generic_note_when_company_less_dismiss_rate_below_threshold(db_session):
    theme = _make_theme(db_session)
    for _ in range(2):
        _make_match(db_session, theme, extracted_company_name=None, status=SignalStatus.DISMISSED)
    for _ in range(8):
        _make_match(db_session, theme, extracted_company_name=None, status=SignalStatus.REVIEWED)
    refresh_theme_feedback_note(db_session, theme)
    assert theme.ai_feedback_note == ""


def test_note_combines_named_company_and_generic_dismissal_patterns(db_session):
    theme = _make_theme(db_session)
    for _ in range(MIN_SAMPLE_SIZE):
        _make_match(db_session, theme, extracted_company_name="Acme", status=SignalStatus.DISMISSED)
    for _ in range(MIN_SAMPLE_SIZE):
        _make_match(db_session, theme, extracted_company_name=None, status=SignalStatus.DISMISSED)
    refresh_theme_feedback_note(db_session, theme)
    assert "Acme" in theme.ai_feedback_note
    assert "no specific company" in theme.ai_feedback_note.lower()


def test_note_scoped_to_own_theme_only(db_session):
    theme_a = _make_theme(db_session, name="Automotive")
    theme_b = _make_theme(db_session, name="Fintech")
    for _ in range(MIN_SAMPLE_SIZE):
        _make_match(db_session, theme_a, extracted_company_name="Acme", status=SignalStatus.DISMISSED)
    refresh_theme_feedback_note(db_session, theme_a)
    refresh_theme_feedback_note(db_session, theme_b)
    assert theme_a.ai_feedback_note != ""
    assert theme_b.ai_feedback_note == ""


def test_old_matches_outside_lookback_window_ignored(db_session):
    theme = _make_theme(db_session)
    old = datetime.now(timezone.utc) - timedelta(days=60)
    for _ in range(MIN_SAMPLE_SIZE):
        _make_match(
            db_session,
            theme,
            extracted_company_name="Acme",
            status=SignalStatus.DISMISSED,
            fetched_at=old,
        )
    refresh_theme_feedback_note(db_session, theme)
    assert theme.ai_feedback_note == ""


# --- GET /theme-watches/{id}/stats ----------------------------------------------------


def test_stats_empty_topic(client, db_session):
    headers = auth_headers(client)
    theme_resp = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    )
    theme_id = theme_resp.json()["id"]

    resp = client.get(f"/theme-watches/{theme_id}/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches_last_7d"] == 0
    assert body["matches_last_30d"] == 0
    assert body["dismiss_rate_30d"] is None
    assert body["avg_relevance_score_30d"] is None
    assert body["last_match_at"] is None


def test_stats_reflects_recent_matches_and_dismiss_rate(client, db_session):
    headers = auth_headers(client)
    theme_resp = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers
    )
    theme = db_session.get(ThemeWatch, uuid.UUID(theme_resp.json()["id"]))

    _make_match(db_session, theme, status=SignalStatus.DISMISSED, relevance_score=2)
    _make_match(db_session, theme, status=SignalStatus.REVIEWED, relevance_score=4)
    # Skipped matches (duplicate/triaged_out) shouldn't count toward stats.
    _make_match(db_session, theme, status=SignalStatus.NEW, skip_reason="duplicate")

    resp = client.get(f"/theme-watches/{theme.id}/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches_last_7d"] == 2
    assert body["matches_last_30d"] == 2
    assert body["dismiss_rate_30d"] == 0.5
    assert body["avg_relevance_score_30d"] == 3.0
    assert body["last_match_at"] is not None


def test_stats_requires_following_or_admin(client, db_session):
    headers_a = auth_headers(client)
    theme_resp = client.post(
        "/theme-watches", json={"name": "Automotive", "query_terms": ["EV"]}, headers=headers_a
    )
    theme_id = theme_resp.json()["id"]

    from tests.conftest import signup

    headers_b, _ = signup(client, email="other@proair.com")
    resp = client.get(f"/theme-watches/{theme_id}/stats", headers=headers_b)
    assert resp.status_code == 403


def test_stats_service_function_directly(db_session):
    theme = _make_theme(db_session)
    _make_match(db_session, theme, status=SignalStatus.DISMISSED, relevance_score=1)
    stats = get_theme_watch_stats(db_session, theme.id)
    assert stats.matches_last_30d == 1
    assert stats.dismiss_rate_30d == 1.0
