from datetime import datetime, timedelta, timezone

from app.models.article import Article, ArticleSource
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal, SignalStatus
from app.models.signal_favorite import SignalFavorite
from app.models.target_company import TargetCompany
from app.models.theme_match import ThemeMatch
from app.models.theme_match_favorite import ThemeMatchFavorite
from app.models.theme_watch import ThemeWatch

from tests.conftest import follow_company, follow_theme, signup


def _make_signal(
    db_session, company_name="Acme Corp", relevance_score=None, status=SignalStatus.NEW
) -> Signal:
    target_company = TargetCompany(name=company_name, keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title=f"{company_name} news",
        url=f"https://example.com/{company_name.lower().replace(' ', '-')}-{relevance_score}-{status}",
        description="desc",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    signal = Signal(
        article_id=article.id,
        summary="summary",
        business_relevance="relevance",
        outreach_snippet_email="snippet",
        relevance_score=relevance_score,
        status=status,
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal


def test_dashboard_requires_auth(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 401


def test_dashboard_empty_state(client, db_session):
    headers, _user_id = signup(client)
    resp = client.get("/dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "top_signals": [],
        "new_signal_count": 0,
        "favorite_count": 0,
        "recent_favorites": [],
        "open_todo_count": 0,
        "open_todos": [],
        "new_theme_match_count": 0,
        "top_theme_matches": [],
        "archived_signal_count": 0,
        "dismissed_signal_count": 0,
        "skipped_article_count": 0,
    }


def test_dashboard_top_signals_ranked_by_relevance_then_recency(client, db_session):
    headers, user_id = signup(client)
    low = _make_signal(db_session, company_name="LowCo", relevance_score=2)
    high = _make_signal(db_session, company_name="HighCo", relevance_score=5)
    unscored = _make_signal(db_session, company_name="UnscoredCo", relevance_score=None)
    for s in (low, high, unscored):
        article = db_session.get(Article, s.article_id)
        follow_company(db_session, user_id, article.target_company_id)

    resp = client.get("/dashboard", headers=headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(high.id), str(low.id), str(unscored.id)]


def test_dashboard_excludes_archived_and_dismissed_from_top_signals(client, db_session):
    headers, user_id = signup(client)
    new_signal = _make_signal(db_session, company_name="NewCo", status=SignalStatus.NEW)
    archived = _make_signal(db_session, company_name="ArchivedCo", status=SignalStatus.ARCHIVED)
    dismissed = _make_signal(db_session, company_name="DismissedCo", status=SignalStatus.DISMISSED)
    for s in (new_signal, archived, dismissed):
        article = db_session.get(Article, s.article_id)
        follow_company(db_session, user_id, article.target_company_id)

    resp = client.get("/dashboard", headers=headers)
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(new_signal.id)]
    assert resp.json()["new_signal_count"] == 1


def test_dashboard_excludes_muted_companies(client, db_session):
    headers, user_id = signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    db_session.add(
        CompanyFollow(user_id=user_id, target_company_id=article.target_company_id, is_muted=True)
    )
    db_session.commit()

    resp = client.get("/dashboard", headers=headers)
    assert resp.json()["top_signals"] == []
    assert resp.json()["new_signal_count"] == 0


def test_dashboard_recent_favorites_and_favorite_count(client, db_session):
    headers, user_id = signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

    client.post(f"/signals/{signal.id}/favorite", headers=headers)

    resp = client.get("/dashboard", headers=headers)
    body = resp.json()
    assert body["favorite_count"] == 1
    assert len(body["recent_favorites"]) == 1
    assert body["recent_favorites"][0]["id"] == str(signal.id)
    assert body["recent_favorites"][0]["kind"] == "signal"


def test_dashboard_recent_favorites_includes_theme_matches(client, db_session):
    """A favorited Themen-Signal shows up in "Zuletzt favorisiert" alongside favorited
    Signals — recent_favorites used to only ever hold Signal favorites, leaving a
    favorited theme match with nowhere to appear."""
    headers, user_id = signup(client)
    match = _make_theme_match(db_session, title="A German startup raised a Series B")
    follow_theme(db_session, user_id, match.theme_watch_id)

    client.post(f"/theme-matches/{match.id}/favorite", headers=headers)

    resp = client.get("/dashboard", headers=headers)
    body = resp.json()
    # favorite_count stays Signal-only (see docs/dashboard-favorites-todos-planning.html)
    assert body["favorite_count"] == 0
    assert len(body["recent_favorites"]) == 1
    entry = body["recent_favorites"][0]
    assert entry["kind"] == "theme_match"
    assert entry["id"] == str(match.id)
    assert entry["title"] == match.title
    assert entry["subtitle"] == "Startups DE"
    assert entry["url"] == match.url


def test_dashboard_recent_favorites_merges_signals_and_theme_matches_by_recency(client, db_session):
    headers, user_id = signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)
    match = _make_theme_match(db_session, title="A German startup raised a Series B")
    follow_theme(db_session, user_id, match.theme_watch_id)

    client.post(f"/signals/{signal.id}/favorite", headers=headers)
    client.post(f"/theme-matches/{match.id}/favorite", headers=headers)

    # Backdate the signal favorite so the merge's recency ordering doesn't depend on the
    # two requests above happening to land in different timestamp ticks.
    signal_favorite = db_session.query(SignalFavorite).filter(SignalFavorite.signal_id == signal.id).one()
    theme_favorite = (
        db_session.query(ThemeMatchFavorite).filter(ThemeMatchFavorite.theme_match_id == match.id).one()
    )
    signal_favorite.created_at = theme_favorite.created_at - timedelta(minutes=5)
    db_session.commit()

    body = client.get("/dashboard", headers=headers).json()
    # The theme match was favorited more recently, so it's the more recent entry.
    kinds = [entry["kind"] for entry in body["recent_favorites"]]
    assert kinds == ["theme_match", "signal"]


def test_dashboard_open_todos_and_count(client, db_session):
    headers, user_id = signup(client)
    signal = _make_signal(db_session)
    article = db_session.get(Article, signal.article_id)
    follow_company(db_session, user_id, article.target_company_id)

    resp1 = client.post(f"/signals/{signal.id}/todos", json={"text": "open task"}, headers=headers)
    resp2 = client.post(f"/signals/{signal.id}/todos", json={"text": "done task"}, headers=headers)
    client.patch(f"/todos/{resp2.json()['id']}", json={"is_done": True}, headers=headers)

    resp = client.get("/dashboard", headers=headers)
    body = resp.json()
    assert body["open_todo_count"] == 1
    assert len(body["open_todos"]) == 1
    assert body["open_todos"][0]["id"] == resp1.json()["id"]
    assert body["open_todos"][0]["target_company_name"] == "Acme Corp"


def test_dashboard_scoped_to_followed_companies_only(client, db_session):
    headers, user_id = signup(client)
    followed = _make_signal(db_session, company_name="Acme Corp")
    followed_article = db_session.get(Article, followed.article_id)
    follow_company(db_session, user_id, followed_article.target_company_id)
    _make_signal(db_session, company_name="Globex")

    resp = client.get("/dashboard", headers=headers)
    ids = [s["id"] for s in resp.json()["top_signals"]]
    assert ids == [str(followed.id)]


def test_dashboard_dismissed_signal_count_scoped_to_follows(client, db_session):
    headers, user_id = signup(client)
    dismissed = _make_signal(db_session, company_name="Acme Corp", status=SignalStatus.DISMISSED)
    dismissed_article = db_session.get(Article, dismissed.article_id)
    follow_company(db_session, user_id, dismissed_article.target_company_id)
    # Not followed, so it shouldn't count for this user.
    _make_signal(db_session, company_name="Globex", status=SignalStatus.DISMISSED)

    resp = client.get("/dashboard", headers=headers)
    assert resp.json()["dismissed_signal_count"] == 1


def test_dashboard_archived_signal_count_scoped_to_follows(client, db_session):
    headers, user_id = signup(client)
    archived = _make_signal(db_session, company_name="Acme Corp", status=SignalStatus.ARCHIVED)
    archived_article = db_session.get(Article, archived.article_id)
    follow_company(db_session, user_id, archived_article.target_company_id)
    # Not followed, so it shouldn't count for this user.
    _make_signal(db_session, company_name="Globex", status=SignalStatus.ARCHIVED)

    resp = client.get("/dashboard", headers=headers)
    assert resp.json()["archived_signal_count"] == 1


def test_dashboard_skipped_article_count_admin_only(client, db_session):
    target_company = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)
    db_session.add(
        Article(
            target_company_id=target_company.id,
            source_name="Reuters",
            title="Low relevance story",
            url="https://example.com/low-relevance",
            skip_reason="triaged_out",
        )
    )
    db_session.commit()

    # First signup in a fresh workspace is auto-promoted to admin.
    admin_headers, _ = signup(client, email="admin@proair.com")
    admin_resp = client.get("/dashboard", headers=admin_headers)
    assert admin_resp.json()["skipped_article_count"] == 1

    user_headers, _ = signup(client, email="rep@proair.com")
    user_resp = client.get("/dashboard", headers=user_headers)
    assert user_resp.json()["skipped_article_count"] == 0


# --- Theme matches on the dashboard ------------------------------------------------


def _make_theme_match(
    db_session,
    theme_name="Startups DE",
    title="A German startup raised a Series B",
    relevance_score=None,
    status=SignalStatus.NEW,
    skip_reason=None,
) -> ThemeMatch:
    theme = db_session.query(ThemeWatch).filter(ThemeWatch.name == theme_name).first()
    if theme is None:
        theme = ThemeWatch(name=theme_name, query_terms=["Startup"])
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(theme)

    match = ThemeMatch(
        theme_watch_id=theme.id,
        source=ArticleSource.GOOGLE_NEWS_RSS,
        source_name="Handelsblatt",
        title=title,
        url=f"https://example.com/{abs(hash((title, status, skip_reason)))}",
        description="desc",
        summary="summary",
        relevance_score=relevance_score,
        status=status,
        skip_reason=skip_reason,
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)
    return match


def test_dashboard_counts_theme_matches_for_followed_themes(client, db_session):
    headers, user_id = signup(client)
    match = _make_theme_match(db_session, relevance_score=5)
    follow_theme(db_session, user_id, match.theme_watch_id)

    body = client.get("/dashboard", headers=headers).json()

    assert body["new_theme_match_count"] == 1
    assert len(body["top_theme_matches"]) == 1
    assert body["top_theme_matches"][0]["theme_watch_name"] == "Startups DE"


def test_dashboard_hides_theme_matches_of_unfollowed_themes(client, db_session):
    headers, _user_id = signup(client)
    _make_theme_match(db_session)

    body = client.get("/dashboard", headers=headers).json()

    assert body["new_theme_match_count"] == 0
    assert body["top_theme_matches"] == []


def test_dashboard_excludes_muted_themes(client, db_session):
    headers, user_id = signup(client)
    match = _make_theme_match(db_session)
    follow_theme(db_session, user_id, match.theme_watch_id, is_muted=True)

    body = client.get("/dashboard", headers=headers).json()

    assert body["new_theme_match_count"] == 0


def test_dashboard_excludes_skipped_theme_matches(client, db_session):
    """Duplicates/triaged-out/ai_error rows are bookkeeping, not something a user should
    see counted as a new match."""
    headers, user_id = signup(client)
    kept = _make_theme_match(db_session, title="Kept story")
    follow_theme(db_session, user_id, kept.theme_watch_id)
    _make_theme_match(db_session, title="Dropped story", skip_reason="triaged_out")

    body = client.get("/dashboard", headers=headers).json()

    assert body["new_theme_match_count"] == 1
    assert [m["title"] for m in body["top_theme_matches"]] == ["Kept story"]


def test_dashboard_orders_theme_matches_by_relevance(client, db_session):
    headers, user_id = signup(client)
    low = _make_theme_match(db_session, title="Low relevance", relevance_score=2)
    follow_theme(db_session, user_id, low.theme_watch_id)
    _make_theme_match(db_session, title="High relevance", relevance_score=5)

    body = client.get("/dashboard", headers=headers).json()

    assert [m["title"] for m in body["top_theme_matches"]] == ["High relevance", "Low relevance"]
