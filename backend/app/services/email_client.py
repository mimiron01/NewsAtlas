import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailClientError(Exception):
    """Raised when an email can't be sent."""


class EmailClient:
    """Thin wrapper around SMTP so the concrete provider (SendGrid, Postmark,
    AWS SES, etc.) is just a credential swap in configuration.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.timeout = timeout

    def send_email(self, *, to: str, subject: str, html_body: str) -> None:
        if not self.host:
            raise EmailClientError("SMTP_HOST is not configured")

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.from_address
        message["To"] = to
        message.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(self.from_address, [to], message.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailClientError(f"Failed to send email to {to}: {exc}") from exc
