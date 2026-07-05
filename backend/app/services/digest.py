import html
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.article import Article
from app.models.digest_log import DigestLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.digest import DigestRunResult
from app.services.email_client import EmailClient, EmailClientError


def _new_signal_rows(db: Session):
    return (
        db.query(Signal, Article, TargetCompany)
        .join(Article, Signal.article_id == Article.id)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
        .filter(Signal.emailed_at.is_(None))
        .order_by(Signal.created_at.asc())
        .all()
    )


def _preheader_text(rows: list[tuple[Signal, Article, TargetCompany]]) -> str:
    company_names = []
    for _signal, _article, target_company in rows:
        if target_company.name not in company_names:
            company_names.append(target_company.name)
    preview = ", ".join(company_names[:3])
    if len(company_names) > 3:
        preview += ", ..."
    count = len(rows)
    return f"{count} new signal{'s' if count != 1 else ''}: {preview}"


def _render_digest_html(rows: list[tuple[Signal, Article, TargetCompany]], frontend_base_url: str) -> str:
    items_html = []
    for signal, article, target_company in rows:
        items_html.append(
            f"""
            <div style="margin-bottom:24px;padding:16px;border:1px solid #e2e5ea;border-radius:8px;">
              <div style="font-size:12px;color:#5b6270;text-transform:uppercase;">
                {html.escape(target_company.name)}
              </div>
              <h3 style="margin:4px 0;">
                <a href="{html.escape(article.url)}">{html.escape(article.title)}</a>
              </h3>
              <p>{html.escape(signal.summary)}</p>
              <p><strong>Why it matters:</strong> {html.escape(signal.business_relevance)}</p>
              <div style="background:#f5f6f8;border-left:3px solid #2757c7;padding:10px 14px;margin-top:8px;">
                <strong>Outreach snippet:</strong><br>{html.escape(signal.outreach_snippet)}
              </div>
              <p style="margin-top:8px;">
                <a href="{html.escape(frontend_base_url)}/signals/{signal.id}">View in NewsAtlas &rarr;</a>
              </p>
            </div>
            """
        )
    preheader = html.escape(_preheader_text(rows))
    preferences_url = html.escape(f"{frontend_base_url}/settings/profile")
    return (
        '<html><body style="font-family:sans-serif;color:#1a1d23;">'
        f'<span style="display:none;max-height:0;overflow:hidden;">{preheader}</span>'
        "<h2>Your daily NewsAtlas signals</h2>"
        f"{''.join(items_html)}"
        '<p style="margin-top:24px;padding-top:16px;border-top:1px solid #e2e5ea;'
        'font-size:12px;color:#5b6270;">'
        f'You\'re receiving this because you have a NewsAtlas account. '
        f'<a href="{preferences_url}">Manage email preferences</a>'
        "</p>"
        "</body></html>"
    )


def _render_digest_text(rows: list[tuple[Signal, Article, TargetCompany]], frontend_base_url: str) -> str:
    lines = ["Your daily NewsAtlas signals", ""]
    for signal, article, target_company in rows:
        lines.extend(
            [
                f"{target_company.name}",
                f"{article.title} ({article.url})",
                signal.summary,
                f"Why it matters: {signal.business_relevance}",
                f"Outreach snippet: {signal.outreach_snippet}",
                f"View in NewsAtlas: {frontend_base_url}/signals/{signal.id}",
                "",
            ]
        )
    lines.append(f"Manage email preferences: {frontend_base_url}/settings/profile")
    return "\n".join(lines)


def send_daily_digest(db: Session, email_client: EmailClient | None = None) -> DigestRunResult:
    app_settings = get_settings()
    email_client = email_client or EmailClient(
        host=app_settings.smtp_host,
        port=app_settings.smtp_port,
        username=app_settings.smtp_user,
        password=app_settings.smtp_password,
        from_address=app_settings.smtp_from_address,
    )

    rows = _new_signal_rows(db)
    if not rows:
        return DigestRunResult(users_emailed=0, signals_included=0, errors=[])

    html_body = _render_digest_html(rows, app_settings.frontend_base_url)
    text_body = _render_digest_text(rows, app_settings.frontend_base_url)
    subject = f"NewsAtlas: {len(rows)} new signal{'s' if len(rows) != 1 else ''}"

    users = db.query(User).all()
    signal_ids = [signal.id for signal, _article, _target_company in rows]
    errors: list[str] = []
    users_emailed = 0

    for user in users:
        try:
            email_client.send_email(
                to=user.email, subject=subject, html_body=html_body, text_body=text_body
            )
        except EmailClientError as exc:
            errors.append(f"{user.email}: {exc}")
            continue
        db.add(DigestLog(user_id=user.id, signal_ids=signal_ids))
        users_emailed += 1

    if users_emailed > 0:
        now = datetime.now(timezone.utc)
        for signal, _article, _target_company in rows:
            signal.emailed_at = now

    db.commit()

    return DigestRunResult(
        users_emailed=users_emailed, signals_included=len(rows), errors=errors
    )
