from app.models.article import ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.services.news_rate_limiter import has_headroom


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
