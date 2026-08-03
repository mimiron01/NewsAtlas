import html
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.digest_log import DigestLog
from app.models.signal import Signal
from app.models.target_company import TargetCompany
from app.models.theme_follow import ThemeFollow
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
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
        .order_by(Signal.relevance_score.desc().nullslast(), Signal.created_at.asc())
        .all()
    )


def _new_theme_match_rows(db: Session):
    """Mirrors _new_signal_rows, but only matches are ever candidates here — inclusion in
    any particular user's digest is still gated on that user's own
    ThemeFollow.include_in_digest (opt-in, default off — see
    docs/topics-ux-improvements-planning.html §4.3), checked in send_daily_digest."""
    return (
        db.query(ThemeMatch, ThemeWatch)
        .join(ThemeWatch, ThemeMatch.theme_watch_id == ThemeWatch.id)
        .filter(ThemeMatch.emailed_at.is_(None), ThemeMatch.skip_reason.is_(None))
        .order_by(ThemeMatch.relevance_score.desc().nullslast(), ThemeMatch.fetched_at.asc())
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


def _render_theme_matches_html(rows: list[tuple[ThemeMatch, ThemeWatch]], frontend_base_url: str) -> str:
    if not rows:
        return ""
    items_html = []
    for match, theme in rows:
        score_badge = (
            f'<span style="background:#eef2fc;color:#2757c7;font-size:11px;font-weight:600;'
            f'padding:2px 8px;border-radius:10px;margin-left:8px;">'
            f"score {match.relevance_score}/5</span>"
            if match.relevance_score is not None
            else ""
        )
        items_html.append(
            f"""
            <div style="margin-bottom:24px;padding:16px;border:1px solid #e2e5ea;border-radius:8px;">
              <div style="font-size:12px;color:#5b6270;text-transform:uppercase;">
                {html.escape(theme.name)}{score_badge}
              </div>
              <h3 style="margin:4px 0;">
                <a href="{html.escape(match.url)}">{html.escape(match.title)}</a>
              </h3>
              <p>{html.escape(match.summary or '')}</p>
              <p style="margin-top:8px;">
                <a href="{html.escape(frontend_base_url)}/themes">View in NewsAtlas &rarr;</a>
              </p>
            </div>
            """
        )
    return (
        '<h2 style="margin-top:32px;">New topic matches</h2>' + "".join(items_html)
    )


def _render_theme_matches_text(rows: list[tuple[ThemeMatch, ThemeWatch]], frontend_base_url: str) -> list[str]:
    if not rows:
        return []
    lines = ["", "New topic matches", ""]
    for match, theme in rows:
        score_suffix = f" (score {match.relevance_score}/5)" if match.relevance_score is not None else ""
        lines.extend(
            [
                f"{theme.name}{score_suffix}",
                f"{match.title} ({match.url})",
                match.summary or "",
                f"View in NewsAtlas: {frontend_base_url}/themes",
                "",
            ]
        )
    return lines


def _render_digest_html(
    rows: list[tuple[Signal, Article, TargetCompany]],
    frontend_base_url: str,
    theme_rows: list[tuple[ThemeMatch, ThemeWatch]] | None = None,
) -> str:
    items_html = []
    for signal, article, target_company in rows:
        score_badge = (
            f'<span style="background:#eef2fc;color:#2757c7;font-size:11px;font-weight:600;'
            f'padding:2px 8px;border-radius:10px;margin-left:8px;">'
            f"score {signal.relevance_score}/5</span>"
            if signal.relevance_score is not None
            else ""
        )
        limited_detail_badge = (
            '<span style="background:#faf1d8;color:#8a6216;font-size:11px;font-weight:600;'
            'padding:2px 8px;border-radius:10px;margin-left:8px;">limited detail</span>'
            if article.is_headline_only
            else ""
        )
        items_html.append(
            f"""
            <div style="margin-bottom:24px;padding:16px;border:1px solid #e2e5ea;border-radius:8px;">
              <div style="font-size:12px;color:#5b6270;text-transform:uppercase;">
                {html.escape(target_company.name)}{score_badge}{limited_detail_badge}
              </div>
              <h3 style="margin:4px 0;">
                <a href="{html.escape(article.url)}">{html.escape(article.title)}</a>
              </h3>
              <p>{html.escape(signal.summary)}</p>
              <p><strong>Why it matters:</strong> {html.escape(signal.business_relevance)}</p>
              <div style="background:#f5f6f8;border-left:3px solid #2757c7;padding:10px 14px;margin-top:8px;">
                <strong>Outreach snippet:</strong><br>{html.escape(signal.outreach_snippet_email)}
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
        f"{_render_theme_matches_html(theme_rows or [], frontend_base_url)}"
        '<p style="margin-top:24px;padding-top:16px;border-top:1px solid #e2e5ea;'
        'font-size:12px;color:#5b6270;">'
        f'You\'re receiving this because you have a NewsAtlas account. '
        f'<a href="{preferences_url}">Manage email preferences</a>'
        "</p>"
        "</body></html>"
    )


def _render_digest_text(
    rows: list[tuple[Signal, Article, TargetCompany]],
    frontend_base_url: str,
    theme_rows: list[tuple[ThemeMatch, ThemeWatch]] | None = None,
) -> str:
    lines = ["Your daily NewsAtlas signals", ""]
    for signal, article, target_company in rows:
        score_suffix = f" (score {signal.relevance_score}/5)" if signal.relevance_score is not None else ""
        limited_detail_suffix = " [limited detail]" if article.is_headline_only else ""
        lines.extend(
            [
                f"{target_company.name}{score_suffix}{limited_detail_suffix}",
                f"{article.title} ({article.url})",
                signal.summary,
                f"Why it matters: {signal.business_relevance}",
                f"Outreach snippet: {signal.outreach_snippet_email}",
                f"View in NewsAtlas: {frontend_base_url}/signals/{signal.id}",
                "",
            ]
        )
    lines.extend(_render_theme_matches_text(theme_rows or [], frontend_base_url))
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
    theme_rows = _new_theme_match_rows(db)
    if not rows and not theme_rows:
        return DigestRunResult(users_emailed=0, signals_included=0, theme_matches_included=0, errors=[])

    users = db.query(User).all()
    errors: list[str] = []
    users_emailed = 0
    # Only matches actually included in at least one user's email get stamped — a topic
    # nobody has opted into yet stays available so opting in later still surfaces its
    # backlog, rather than being silently marked "sent" to nobody (see
    # docs/topics-ux-improvements-planning.html §4.3).
    included_theme_match_ids: set = set()

    for user in users:
        followed_company_ids = {
            follow.target_company_id
            for follow in db.query(CompanyFollow).filter(
                CompanyFollow.user_id == user.id, CompanyFollow.is_muted.is_(False)
            )
        }
        user_rows = [row for row in rows if row[2].id in followed_company_ids]

        digest_theme_ids = {
            follow.theme_watch_id
            for follow in db.query(ThemeFollow).filter(
                ThemeFollow.user_id == user.id,
                ThemeFollow.is_muted.is_(False),
                ThemeFollow.include_in_digest.is_(True),
            )
        }
        user_theme_rows = [row for row in theme_rows if row[1].id in digest_theme_ids]

        if not user_rows and not user_theme_rows:
            continue

        html_body = _render_digest_html(user_rows, app_settings.frontend_base_url, user_theme_rows)
        text_body = _render_digest_text(user_rows, app_settings.frontend_base_url, user_theme_rows)
        total_count = len(user_rows) + len(user_theme_rows)
        subject = f"NewsAtlas: {total_count} new signal{'s' if total_count != 1 else ''}"
        try:
            email_client.send_email(
                to=user.email, subject=subject, html_body=html_body, text_body=text_body
            )
        except EmailClientError as exc:
            errors.append(f"{user.email}: {exc}")
            continue
        signal_ids = [signal.id for signal, _article, _target_company in user_rows]
        db.add(DigestLog(user_id=user.id, signal_ids=signal_ids))
        users_emailed += 1
        included_theme_match_ids.update(match.id for match, _theme in user_theme_rows)

    now = datetime.now(timezone.utc)
    for signal, _article, _target_company in rows:
        signal.emailed_at = now
    for match, _theme in theme_rows:
        if match.id in included_theme_match_ids:
            match.emailed_at = now

    db.commit()

    return DigestRunResult(
        users_emailed=users_emailed,
        signals_included=len(rows),
        theme_matches_included=len(included_theme_match_ids),
        errors=errors,
    )
