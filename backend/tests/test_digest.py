from datetime import datetime, timezone

from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.digest_log import DigestLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.user import User
from app.services.digest import send_daily_digest
from app.services.email_client import EmailClientError


class FakeEmailClient:
    def __init__(self, fail_for: set[str] | None = None):
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


def _make_signal(db_session, title="Acme raises funding") -> Signal:
    target_company = TargetCompany(name="Acme Corp", keywords=[])
    db_session.add(target_company)
    db_session.commit()
    db_session.refresh(target_company)

    article = Article(
        target_company_id=target_company.id,
        source_name="Reuters",
        title=title,
        url=f"https://example.com/{title.replace(' ', '-').lower()}",
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
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    return signal


def _follow(db_session, user, signal, *, is_muted=False) -> None:
    article = db_session.get(Article, signal.article_id)
    db_session.add(
        CompanyFollow(
            user_id=user.id, target_company_id=article.target_company_id, is_muted=is_muted
        )
    )
    db_session.commit()


def test_send_daily_digest_no_new_signals_sends_nothing(db_session):
    _make_user(db_session)
    result = send_daily_digest(db_session, email_client=FakeEmailClient())
    assert result.users_emailed == 0
    assert result.signals_included == 0
    assert result.errors == []


def test_send_daily_digest_emails_all_users_and_marks_signals(db_session):
    user_a = _make_user(db_session, "a@proair.com")
    user_b = _make_user(db_session, "b@proair.com")
    signal = _make_signal(db_session)
    _follow(db_session, user_a, signal)
    _follow(db_session, user_b, signal)

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 2
    assert result.signals_included == 1
    assert result.errors == []
    assert len(fake_email.sent) == 2
    recipients = {to for to, _subject, _body in fake_email.sent}
    assert recipients == {user_a.email, user_b.email}

    db_session.refresh(signal)
    assert signal.emailed_at is not None

    digest_logs = db_session.query(DigestLog).all()
    assert len(digest_logs) == 2

    _to, _subject, html_body = fake_email.sent[0]
    assert "Manage email preferences" in html_body
    assert "Acme raises funding" in html_body
    assert all(text_body and "Acme raises funding" in text_body for text_body in fake_email.text_bodies)
    assert all("Manage email preferences" in text_body for text_body in fake_email.text_bodies)


def test_send_daily_digest_skips_already_emailed_signals(db_session):
    user = _make_user(db_session)
    signal = _make_signal(db_session)
    _follow(db_session, user, signal)

    send_daily_digest(db_session, email_client=FakeEmailClient())
    second_result = send_daily_digest(db_session, email_client=FakeEmailClient())

    assert second_result.users_emailed == 0
    assert second_result.signals_included == 0


def test_send_daily_digest_continues_after_one_user_fails(db_session):
    user_a = _make_user(db_session, "a@proair.com")
    user_b = _make_user(db_session, "b@proair.com")
    signal = _make_signal(db_session)
    _follow(db_session, user_a, signal)
    _follow(db_session, user_b, signal)

    fake_email = FakeEmailClient(fail_for={"a@proair.com"})
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 1
    assert len(result.errors) == 1
    assert user_a.email in result.errors[0]


def test_send_daily_digest_skips_users_not_following_or_muted(db_session):
    following_user = _make_user(db_session, "following@proair.com")
    muted_user = _make_user(db_session, "muted@proair.com")
    not_following_user = _make_user(db_session, "other@proair.com")
    signal = _make_signal(db_session)
    _follow(db_session, following_user, signal)
    _follow(db_session, muted_user, signal, is_muted=True)

    fake_email = FakeEmailClient()
    result = send_daily_digest(db_session, email_client=fake_email)

    assert result.users_emailed == 1
    recipients = {to for to, _subject, _body in fake_email.sent}
    assert recipients == {following_user.email}
    assert not_following_user.email not in recipients
    assert muted_user.email not in recipients

    db_session.refresh(signal)
    assert signal.emailed_at is not None
