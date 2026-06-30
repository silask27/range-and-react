from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from html import escape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from api.app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    status: str
    provider: str
    skipped: bool = False
    message_id: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip('"').strip("'")


def email_delivery_enabled() -> bool:
    return (
        _clean(settings.email_provider) == "resend"
        and bool(_clean(settings.resend_api_key))
        and bool(_clean(settings.email_from))
    )


def build_password_reset_url(reset_token: str, email: str | None = None) -> str:
    params = {"token": reset_token}
    if email:
        params["email"] = email
    query = urlencode(params)
    return f"{settings.frontend_url.rstrip('/')}{settings.password_reset_path}?{query}"


def build_signup_invite_url(invite_code: str, email: str | None = None) -> str:
    params = {"mode": "signup", "invite_code": invite_code}
    if email:
        params["email"] = email
    query = urlencode(params)
    return f"{settings.frontend_url.rstrip('/')}{settings.signup_invite_accept_path}?{query}"


def _resend_headers() -> dict[str, str]:
    api_key = _clean(settings.resend_api_key)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"range-and-react-backend/{settings.app_version or '1.0'}",
    }


def _post_resend(payload: dict[str, Any]) -> EmailDeliveryResult:
    provider = _clean(settings.email_provider) or "disabled"
    email_from = _clean(settings.email_from)
    reply_to = _clean(settings.email_reply_to)

    if not email_delivery_enabled():
        detail = "Email delivery is not configured"
        logger.info("Skipping email delivery: %s", detail)
        return EmailDeliveryResult(
            status="skipped",
            provider=provider,
            skipped=True,
            detail=detail,
        )

    body = {
        "from": email_from,
        **payload,
    }
    if reply_to:
        body["reply_to"] = reply_to

    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(body).encode("utf-8"),
        headers=_resend_headers(),
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw) if raw else {}
        return EmailDeliveryResult(
            status="sent",
            provider="resend",
            message_id=parsed.get("id"),
        )
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""

        logger.warning(
            "Resend email send failed: status=%s from=%r reply_to=%r payload_keys=%s body=%s",
            getattr(exc, "code", None),
            email_from,
            reply_to,
            sorted(body.keys()),
            raw or str(exc),
        )
        return EmailDeliveryResult(
            status="failed",
            provider="resend",
            detail=raw or str(exc),
        )
    except URLError as exc:
        detail = str(exc.reason)
        logger.warning("Resend email send failed: %s", detail)
        return EmailDeliveryResult(status="failed", provider="resend", detail=detail)


def send_password_reset_email(
    *,
    email: str,
    reset_token: str,
    expires_at: str,
    display_name: str | None = None,
) -> EmailDeliveryResult:
    reset_url = build_password_reset_url(reset_token, email=email)
    first_name = (display_name or "there").strip() or "there"
    subject = "Reset your Range & React password"
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>Hi {first_name},</p>
      <p>Use the button below to reset your Range & React password.</p>
      <p><a href=\"{reset_url}\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Reset password</a></p>
      <p>This link expires at <strong>{expires_at}</strong>.</p>
      <p>If you did not request a reset, you can safely ignore this email.</p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend(
        {
            "to": [email],
            "subject": subject,
            "html": html,
        }
    )


def send_signup_invite_email(
    *,
    email: str | None,
    invite_code: str,
    organization_name: str | None = None,
    invited_by_name: str | None = None,
    expires_at: str | None = None,
) -> EmailDeliveryResult:
    if not email:
        return EmailDeliveryResult(
            status="skipped",
            provider=_clean(settings.email_provider) or "disabled",
            skipped=True,
            detail="Invite has no email address",
        )

    invite_url = build_signup_invite_url(invite_code, email=email)
    org_label = organization_name or settings.app_name
    inviter = (invited_by_name or "your coach").strip() or "your coach"
    expiry_copy = (
        f"This invite expires at {expires_at}." if expires_at else "This invite expires soon."
    )
    subject = f"You are invited to join {org_label} on Range & React"
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>You have been invited by <strong>{inviter}</strong> to join <strong>{org_label}</strong> on Range & React.</p>
      <p><a href=\"{invite_url}\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Accept invite</a></p>
      <p style=\"margin:0\">Invite code: <strong>{invite_code}</strong></p>
      <p>{expiry_copy}</p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend(
        {
            "to": [email],
            "subject": subject,
            "html": html,
        }
    )


def send_welcome_email(
    *,
    email: str,
    display_name: str | None = None,
    organization_names: list[str] | None = None,
) -> EmailDeliveryResult:
    if not settings.welcome_email_enabled:
        return EmailDeliveryResult(
            status="skipped",
            provider=_clean(settings.email_provider) or "disabled",
            skipped=True,
            detail="Welcome email disabled",
        )

    first_name = (display_name or "there").strip() or "there"
    org_copy = ""
    if organization_names:
        org_copy = f" You are now set up for {', '.join(organization_names[:3])}."

    subject = "Welcome to Range & React"
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>Hi {first_name},</p>
      <p>Welcome to <strong>Range &amp; React</strong>.{org_copy}</p>
      <p><a href=\"{settings.frontend_url.rstrip('/')}/login\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Log in</a></p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend(
        {
            "to": [email],
            "subject": subject,
            "html": html,
        }
    )


def send_accountability_digest_email(*, email: str, digest: dict[str, Any], display_name: str | None = None) -> EmailDeliveryResult:
    first_name = escape((display_name or "coach").strip() or "coach")
    summary = digest.get("summary", {}) if isinstance(digest, dict) else {}
    period = digest.get("period", {}) if isinstance(digest, dict) else {}
    cohort = digest.get("cohort", {}) if isinstance(digest, dict) else {}
    cohort_name = str(cohort.get("name") or "").strip() if isinstance(cohort, dict) else ""

    def stat(label: str, key: str) -> str:
        return f"<li><strong>{escape(label)}:</strong> {escape(str(summary.get(key, 0)))}</li>"

    def rows(items: list[dict[str, Any]], *, empty: str, formatter) -> str:
        if not items:
            return f"<p>{escape(empty)}</p>"
        return "<ul>" + "".join(f"<li>{formatter(item)}</li>" for item in items[:5]) + "</ul>"

    weakest_members = rows(
        digest.get("weakest_members") or [],
        empty="No scored member hands in this period.",
        formatter=lambda item: f"{escape(str(item.get('display_name') or item.get('email') or 'Member'))}: {escape(str(item.get('avg_overall_score') or 'unscored'))} over {escape(str(item.get('hands') or 0))} hands",
    )
    missed_members = rows(
        digest.get("missed_members") or [],
        empty="Every active member trained during this period.",
        formatter=lambda item: escape(str(item.get("display_name") or item.get("email") or "Member")),
    )
    weak_spots = rows(
        digest.get("weak_spots") or [],
        empty="Not enough completed hands to identify weak spots.",
        formatter=lambda item: f"{escape(str(item.get('label') or 'Spot'))}: {escape(str(item.get('avg_overall_score') or 'unscored'))} across {escape(str(item.get('hands') or 0))} hands",
    )
    overdue = rows(
        digest.get("overdue_assignments") or [],
        empty="No overdue assignments.",
        formatter=lambda item: f"{escape(str(item.get('title') or 'Assignment'))}: {escape(str((item.get('progress') or {}).get('progress_count', 0)))} / {escape(str((item.get('progress') or {}).get('repetition_target', item.get('repetition_target', 0))))} reps",
    )

    subject = f"Weekly Range & React cohort summary: {cohort_name}" if cohort_name else "Weekly Range & React accountability digest"
    intro = (
        f"Here is the Range &amp; React accountability snapshot for <strong>{escape(cohort_name)}</strong> over the last {escape(str(period.get('days', 7)))} days."
        if cohort_name
        else f"Here is the Range &amp; React accountability snapshot for the last {escape(str(period.get('days', 7)))} days."
    )
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>Hi {first_name},</p>
      <p>{intro}</p>
      <ul>
        {stat("Active members", "active_members")}
        {stat("Members trained", "members_trained")}
        {stat("Members missed", "members_missed")}
        {stat("Completed hands", "completed_hands")}
        {stat("Active assignments", "active_assignments")}
        {stat("Overdue assignments", "overdue_assignments")}
      </ul>
      <h3>Members needing attention</h3>
      {weakest_members}
      <h3>Members who did not train</h3>
      {missed_members}
      <h3>Weakest current spots</h3>
      {weak_spots}
      <h3>Overdue assignments</h3>
      {overdue}
      <p><a href=\"{settings.frontend_url.rstrip('/')}/admin\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Open coach dashboard</a></p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend({"to": [email], "subject": subject, "html": html})
