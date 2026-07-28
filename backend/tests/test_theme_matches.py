import uuid
from datetime import datetime, timezone

from app.models.signal import SignalStatus
from app.models.target_company import TargetCompany
from app.models.theme_follow import ThemeFollow
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch


def _signup(client, email="rep@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    return headers, uuid.UUID(user_id)


def _auth_headers(client):
    headers, _user_id = _signup(client)
    return headers


def _make_theme(db_session, name="Automotive") -> ThemeWatch:
    theme = ThemeWatch(name=name, query_terms=["EV battery"])
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def _make_match(
    db_session, theme: ThemeWatch, *, url="https://example.com/story", extracted_company_name=None
) -> ThemeMatch:
    match = ThemeMatch(
        theme_watch_id=theme.id,
        source_name="Reuters",
        title="Acme Corp raises $10M for EV batteries",
        url=url,
        description="desc",
        published_at=datetime.now(timezone.utc),
        summary="Acme Corp raised funding",
        business_relevance="Relevant",
        relevance_score=4,
        extracted_company_name=extracted_company_name,
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)
    return match


def _follow(db_session, user_id, theme_watch_id) -> None:
    db_session.add(ThemeFollow(user_id=user_id, theme_watch_id=theme_watch_id))
    db_session.commit()


def test_list_theme_matches_scoped_to_followed_themes(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _make_match(db_session, theme)
    _follow(db_session, user_id, theme.id)
    other_theme = _make_theme(db_session, name="Fintech")
    _make_match(db_session, other_theme, url="https://example.com/other")

    resp = client.get("/theme-matches", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["theme_watch_name"] == "Automotive"


def test_list_theme_matches_filters_by_theme_and_status(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    match = _make_match(db_session, theme, url="https://example.com/a")
    dismissed = _make_match(db_session, theme, url="https://example.com/b")
    dismissed.status = SignalStatus.DISMISSED
    db_session.commit()

    resp = client.get(f"/theme-matches?theme_id={theme.id}&status=dismissed", headers=headers)
    assert resp.status_code == 200
    assert [m["id"] for m in resp.json()] == [str(dismissed.id)]


def test_get_theme_match_requires_following(client, db_session):
    headers_a, user_id_a = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    theme = _make_theme(db_session)
    _follow(db_session, user_id_a, theme.id)
    match = _make_match(db_session, theme)

    ok = client.get(f"/theme-matches/{match.id}", headers=headers_a)
    assert ok.status_code == 200

    forbidden = client.get(f"/theme-matches/{match.id}", headers=headers_b)
    assert forbidden.status_code == 404


def test_update_theme_match_status(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    match = _make_match(db_session, theme)

    resp = client.patch(
        f"/theme-matches/{match.id}", json={"status": "dismissed"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"


def test_theme_matches_require_auth(client):
    resp = client.get("/theme-matches")
    assert resp.status_code == 401


def test_track_company_creates_and_follows_company(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    match = _make_match(db_session, theme, extracted_company_name="Acme Corp")

    resp = client.post(f"/theme-matches/{match.id}/track-company", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert body["follower_count"] == 1
    assert body["is_muted"] is False

    db_session.refresh(match)
    assert match.matched_target_company_id == uuid.UUID(body["id"])

    # Now visible in the user's own tracked companies.
    listed = client.get("/target-companies", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Acme Corp"


def test_track_company_dedupes_against_existing_target_company(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    existing = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)
    match = _make_match(db_session, theme, extracted_company_name="acme corp")

    resp = client.post(f"/theme-matches/{match.id}/track-company", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(existing.id)


def test_track_company_fails_without_extracted_company(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    match = _make_match(db_session, theme, extracted_company_name=None)

    resp = client.post(f"/theme-matches/{match.id}/track-company", headers=headers)
    assert resp.status_code == 400


def test_track_company_fails_when_already_matched(client, db_session):
    headers, user_id = _signup(client)
    theme = _make_theme(db_session)
    _follow(db_session, user_id, theme.id)
    tc = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    match = _make_match(db_session, theme, extracted_company_name="Acme Corp")
    match.matched_target_company_id = tc.id
    db_session.commit()

    resp = client.post(f"/theme-matches/{match.id}/track-company", headers=headers)
    assert resp.status_code == 409


def test_track_company_requires_following_the_theme(client, db_session):
    headers_a, user_id_a = _signup(client, email="a@proair.com")
    headers_b, _ = _signup(client, email="b@proair.com")
    theme = _make_theme(db_session)
    _follow(db_session, user_id_a, theme.id)
    match = _make_match(db_session, theme, extracted_company_name="Acme Corp")

    resp = client.post(f"/theme-matches/{match.id}/track-company", headers=headers_b)
    assert resp.status_code == 404
