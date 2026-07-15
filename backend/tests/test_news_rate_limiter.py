from datetime import datetime, timedelta, timezone

from app.models.article import ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.services.news_rate_limiter import (
    HeadroomStatus,
    check_headroom,
    has_headroom,
    wait_for_minute_headroom,
)


def _log(db_session, source=ArticleSource.NEWSDATA, requests_used=1, call_type="latest"):
    db_session.add(NewsSourceUsageLog(source=source, call_type=call_type, requests_used=requests_used))
    db_session.commit()


def test_has_headroom_true_when_no_usage_logged(db_session):
    assert has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=5, per_day_limit=10
    )


def test_has_headroom_false_once_per_day_limit_reached(db_session):
    for _ in range(3):
        _log(db_session)
    assert not has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=3
    )


def test_has_headroom_false_once_per_minute_limit_reached(db_session):
    for _ in range(2):
        _log(db_session)
    assert not has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=2, per_day_limit=None
    )


def test_has_headroom_sums_requests_used_not_row_count(db_session):
    _log(db_session, requests_used=5)
    assert not has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=5
    )
    assert has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=6
    )


def test_has_headroom_ignores_rate_limited_marker_rows(db_session):
    """A 'rate_limited' row (requests_used=0, logged when a call was skipped) must not
    itself count toward the limit — otherwise a source stuck at its limit would never be
    distinguishable from one that's actually still making real calls."""
    _log(db_session, requests_used=0, call_type="rate_limited")
    assert has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=1
    )


def test_has_headroom_is_per_source(db_session):
    for _ in range(5):
        _log(db_session, source=ArticleSource.NEWSDATA)
    assert not has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=5
    )
    assert has_headroom(
        db_session, ArticleSource.GOOGLE_NEWS_RSS, per_minute_limit=None, per_day_limit=5
    )


def test_has_headroom_treats_unset_limit_as_unlimited(db_session):
    for _ in range(100):
        _log(db_session)
    assert has_headroom(
        db_session, ArticleSource.NEWSDATA, per_minute_limit=None, per_day_limit=None
    )
    assert has_headroom(db_session, ArticleSource.NEWSDATA, per_minute_limit=0, per_day_limit=0)


def test_check_headroom_reports_minute_limited_distinctly_from_day_limited(db_session):
    for _ in range(2):
        _log(db_session, source=ArticleSource.GOOGLE_NEWS_RSS)
    assert check_headroom(
        db_session, ArticleSource.GOOGLE_NEWS_RSS, per_minute_limit=2, per_day_limit=1000
    ) is HeadroomStatus.MINUTE_LIMITED


def test_check_headroom_reports_day_limited_even_when_minute_limit_also_configured(db_session):
    for _ in range(2):
        _log(db_session, source=ArticleSource.GOOGLE_NEWS_RSS)
    # Day limit is checked first: once it's exhausted, waiting out the minute window
    # wouldn't help anyway, so the caller needs to know it's the day ceiling that's hit.
    assert check_headroom(
        db_session, ArticleSource.GOOGLE_NEWS_RSS, per_minute_limit=1000, per_day_limit=2
    ) is HeadroomStatus.DAY_LIMITED


def test_check_headroom_ok_when_under_both_limits(db_session):
    assert check_headroom(
        db_session, ArticleSource.GOOGLE_NEWS_RSS, per_minute_limit=5, per_day_limit=10
    ) is HeadroomStatus.OK


def test_wait_for_minute_headroom_skips_waiting_when_limit_unset(db_session):
    assert wait_for_minute_headroom(
        db_session,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=None,
        should_cancel=lambda: False,
        sleep=lambda seconds: (_ for _ in ()).throw(AssertionError("should never sleep")),
    )


def test_wait_for_minute_headroom_returns_true_once_the_window_frees_up(db_session):
    """Simulates real time passing (without an actual 60s test sleep) by aging the
    logged request past the trailing-minute window inside the fake sleep callback —
    exactly what would happen for real once enough wall-clock time elapses."""
    log = NewsSourceUsageLog(source=ArticleSource.GOOGLE_NEWS_RSS, call_type="latest", requests_used=1)
    db_session.add(log)
    db_session.commit()

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        log.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db_session.commit()

    acquired = wait_for_minute_headroom(
        db_session,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=1,
        should_cancel=lambda: False,
        sleep=fake_sleep,
    )

    assert acquired
    assert len(sleep_calls) == 1


def test_wait_for_minute_headroom_stops_immediately_when_cancelled(db_session):
    _log(db_session, source=ArticleSource.GOOGLE_NEWS_RSS)
    acquired = wait_for_minute_headroom(
        db_session,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=1,
        should_cancel=lambda: True,
        sleep=lambda seconds: (_ for _ in ()).throw(AssertionError("should never sleep")),
    )
    assert not acquired


def test_wait_for_minute_headroom_gives_up_once_the_safety_cap_is_reached(db_session):
    _log(db_session, source=ArticleSource.GOOGLE_NEWS_RSS)  # never ages out in this test

    fake_now = [0.0]

    def fake_clock() -> float:
        return fake_now[0]

    def fake_sleep(seconds: float) -> None:
        fake_now[0] += seconds

    acquired = wait_for_minute_headroom(
        db_session,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=1,
        should_cancel=lambda: False,
        poll_interval_seconds=2.0,
        max_wait_seconds=5.0,
        sleep=fake_sleep,
        clock=fake_clock,
    )
    assert not acquired
