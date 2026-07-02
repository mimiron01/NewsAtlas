import smtplib

import pytest

from app.services.email_client import EmailClient, EmailClientError


def test_send_email_requires_host():
    client = EmailClient(host="", port=587, username="", password="", from_address="a@b.com")
    with pytest.raises(EmailClientError, match="SMTP_HOST"):
        client.send_email(to="rep@proair.com", subject="Hi", html_body="<p>hi</p>")


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        pass

    def sendmail(self, from_address, to_addrs, message):
        FakeSMTP.sent.append((from_address, to_addrs, message))


def test_send_email_success(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    client = EmailClient(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pw",
        from_address="signals@proair.com",
    )
    client.send_email(to="rep@proair.com", subject="New signals", html_body="<p>hi</p>")

    assert len(FakeSMTP.sent) == 1
    from_address, to_addrs, message = FakeSMTP.sent[0]
    assert from_address == "signals@proair.com"
    assert to_addrs == ["rep@proair.com"]
    assert "New signals" in message


def test_send_email_wraps_smtp_errors(monkeypatch):
    class FailingSMTP(FakeSMTP):
        def sendmail(self, *args, **kwargs):
            raise smtplib.SMTPException("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", FailingSMTP)

    client = EmailClient(
        host="smtp.example.com", port=587, username="", password="", from_address="a@b.com"
    )
    with pytest.raises(EmailClientError, match="Failed to send email"):
        client.send_email(to="rep@proair.com", subject="Hi", html_body="<p>hi</p>")
