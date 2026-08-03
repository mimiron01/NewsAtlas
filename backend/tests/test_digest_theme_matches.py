from app.models.theme_follow import ThemeFollow
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.models.user import User
from app.services.digest import send_daily_digest
from app.services.email_client import EmailClientError


class FakeEmailClient:
    def __init__(self, fail_for=None):
        self.fail_for = fail_for or set()
        self.sent: list[tuple[str, str, str]] = []
        self.text_bodies: list[str] = []

    def send_email(self, *, to, subject, html_body, text_body=None):
        if to in self.fail_for:
            raise EmailClientError("simulated failure")
        self.sent.append((to, subject, html_body))
        self.text_bodies.append(text_body)


def _make_user(db_session, email="rep@proair.com") -> User:
    user = User(email=email, password_hash="x", name="Rep")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_theme(db_session, name="Automotive") -> ThemeWatch:
    theme = ThemeWatch(name=name, query_terms=["EV"])
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def _make_match(db_session, theme, title="EV sales surge") -> ThemeMatch:
    match = ThemeMatch(
        theme_watch_id=theme.id,
        source_name="Example",
        title=title,
        url=f"https://example.com/{title.replace(' ', '-').lower()}",
        summary="summary",
        relevance_score=4,
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)
    return match


def _follow(db_session, user, theme, *, include_in_digest=False, is_muted=False) -> None:
    db_session.add(
        ThemeFollow(
            user_id=user.id,
            theme_watch_id=theme.id,
            is_muted=is_muted,
            include_in_digest=include_in_digest,
        )
    )
    db_session.commit()


def test_theme_matches_excluded_by_default(db_session):
    """See docs/topics-ux-improvements-planning.html §4.3: no existing digest changes
    shape without an explicit opt-in."""
    user = _make_user(db_session)
    theme = _make_theme(db_session)
    _make_match(db_session, theme)
    _follow(db_session, user, theme, include_in_digest=False)

    result = send_daily_digest(db_session, email_client=FakeEmailClient())

    assert result.users_emailed == 0
    assert result.theme_matches_included == 0


def test_opted_in_topic_matches_are_emailed_and_stamped(db_session):
    user = _make_user(db_session)
    theme = _make_theme(db_session)
    match = _make_match(db_session, theme)
    _follow(db_session, user, theme, include_in_digest=True)

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 1
    assert result.theme_matches_included == 1
    assert len(fake_email.sent) == 1
    _to, subject, html_body = fake_email.sent[0]
    assert "1 new signal" in subject
    assert "EV sales surge" in html_body
    assert "New topic matches" in html_body

    db_session.refresh(match)
    assert match.emailed_at is not None


def test_muted_follow_excludes_topic_matches_even_if_opted_in(db_session):
    user = _make_user(db_session)
    theme = _make_theme(db_session)
    _make_match(db_session, theme)
    _follow(db_session, user, theme, include_in_digest=True, is_muted=True)

    result = send_daily_digest(db_session, email_client=FakeEmailClient())
    assert result.users_emailed == 0


def test_non_opted_in_follower_never_sees_others_opt_in(db_session):
    user_a = _make_user(db_session, "a@proair.com")
    user_b = _make_user(db_session, "b@proair.com")
    theme = _make_theme(db_session)
    _make_match(db_session, theme)
    _follow(db_session, user_a, theme, include_in_digest=True)
    _follow(db_session, user_b, theme, include_in_digest=False)

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 1
    recipients = {to for to, _subject, _body in fake_email.sent}
    assert recipients == {user_a.email}


def test_unopted_topic_match_is_not_stamped_and_survives_for_future_opt_in(db_session):
    """A match nobody has opted into yet should remain available — not silently marked
    "sent" to nobody — so opting in later still surfaces it."""
    user = _make_user(db_session)
    theme = _make_theme(db_session)
    match = _make_match(db_session, theme)
    _follow(db_session, user, theme, include_in_digest=False)

    send_daily_digest(db_session, email_client=FakeEmailClient())
    db_session.refresh(match)
    assert match.emailed_at is None

    # Now opt in and re-run — the same match should surface this time.
    follow = db_session.query(ThemeFollow).filter(ThemeFollow.user_id == user.id).one()
    follow.include_in_digest = True
    db_session.commit()

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)
    assert result.theme_matches_included == 1
    assert len(fake_email.sent) == 1


def test_digest_includes_both_signals_and_topic_matches_in_one_email(db_session, monkeypatch):
    from tests.test_digest import _make_signal
    from tests.test_digest import _follow as _follow_company

    user = _make_user(db_session)
    signal = _make_signal(db_session)
    _follow_company(db_session, user, signal)
    theme = _make_theme(db_session)
    _make_match(db_session, theme)
    _follow(db_session, user, theme, include_in_digest=True)

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 1
    assert result.signals_included == 1
    assert result.theme_matches_included == 1
    _to, subject, html_body = fake_email.sent[0]
    assert "2 new signal" in subject
    assert "Acme raises funding" in html_body
    assert "EV sales surge" in html_body
