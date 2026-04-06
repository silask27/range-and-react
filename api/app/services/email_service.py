from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
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


def email_delivery_enabled() -> bool:
    return settings.email_provider == "resend" and bool(settings.resend_api_key) and bool(settings.email_from)


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
    return {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }


def _post_resend(payload: dict[str, Any]) -> EmailDeliveryResult:
    if not email_delivery_enabled():
        detail = "Email delivery is not configured"
        logger.info("Skipping email delivery: %s", detail)
        return EmailDeliveryResult(status="skipped", provider=settings.email_provider or "disabled", skipped=True, detail=detail)

    body = {
        "from": settings.email_from,
        **payload,
    }
    if settings.email_reply_to:
        body["reply_to"] = settings.email_reply_to
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(body).encode("utf-8"),
        headers=_resend_headers(),
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        return EmailDeliveryResult(status="sent", provider="resend", message_id=parsed.get("id"))
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            detail = parsed.get("message") or raw or str(exc)
        except Exception:
            detail = str(exc)
        logger.warning("Resend email send failed: %s", detail)
        return EmailDeliveryResult(status="failed", provider="resend", detail=detail)
    except URLError as exc:
        detail = str(exc.reason)
        logger.warning("Resend email send failed: %s", detail)
        return EmailDeliveryResult(status="failed", provider="resend", detail=detail)


def send_password_reset_email(*, email: str, reset_token: str, expires_at: str, display_name: str | None = None) -> EmailDeliveryResult:
    reset_url = build_password_reset_url(reset_token, email=email)
    first_name = (display_name or "there").strip() or "there"
    hours = "2 hours"
    subject = "Reset your Live Range Lab password"
    text = (
        f"Hi {first_name},\n\n"
        f"Use this link to reset your password: {reset_url}\n\n"
        f"This link expires in {hours}. If you did not request a reset, you can ignore this email.\n\n"
        f"Support: {settings.support_email}\n"
    )
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>Hi {first_name},</p>
      <p>Use the button below to reset your Live Range Lab password.</p>
      <p><a href=\"{reset_url}\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Reset password</a></p>
      <p>This link expires at <strong>{expires_at}</strong>.</p>
      <p>If you did not request a reset, you can safely ignore this email.</p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend({"to": [email], "subject": subject, "html": html, "text": text})


def send_signup_invite_email(*, email: str | None, invite_code: str, organization_name: str | None = None, invited_by_name: str | None = None, expires_at: str | None = None) -> EmailDeliveryResult:
    if not email:
        return EmailDeliveryResult(status="skipped", provider=settings.email_provider or "disabled", skipped=True, detail="Invite has no email address")
    invite_url = build_signup_invite_url(invite_code, email=email)
    org_label = organization_name or settings.app_name
    inviter = (invited_by_name or "your coach").strip() or "your coach"
    expiry_copy = f"This invite expires at {expires_at}." if expires_at else "This invite expires soon."
    subject = f"You are invited to join {org_label} on Live Range Lab"
    text = (
        f"You have been invited by {inviter} to join {org_label} on Live Range Lab.\n\n"
        f"Accept your invite here: {invite_url}\n\n"
        f"Invite code: {invite_code}\n"
        f"{expiry_copy}\n\n"
        f"Support: {settings.support_email}\n"
    )
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>You have been invited by <strong>{inviter}</strong> to join <strong>{org_label}</strong> on Live Range Lab.</p>
      <p><a href=\"{invite_url}\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Accept invite</a></p>
      <p style=\"margin:0\">Invite code: <strong>{invite_code}</strong></p>
      <p>{expiry_copy}</p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend({"to": [email], "subject": subject, "html": html, "text": text})


def send_welcome_email(*, email: str, display_name: str | None = None, organization_names: list[str] | None = None) -> EmailDeliveryResult:
    if not settings.welcome_email_enabled:
        return EmailDeliveryResult(status="skipped", provider=settings.email_provider or "disabled", skipped=True, detail="Welcome email disabled")
    first_name = (display_name or "there").strip() or "there"
    org_copy = ""
    if organization_names:
        org_copy = f" You are now set up for {', '.join(organization_names[:3])}."
    subject = "Welcome to Live Range Lab"
    text = (
        f"Hi {first_name},\n\n"
        f"Welcome to Live Range Lab.{org_copy}\n"
        f"You can log in here: {settings.frontend_url.rstrip('/')}/login\n\n"
        f"Support: {settings.support_email}\n"
    )
    html = f"""
    <div style=\"font-family:Inter,Arial,sans-serif;line-height:1.6;color:#141210\">
      <p>Hi {first_name},</p>
      <p>Welcome to <strong>Live Range Lab</strong>.{org_copy}</p>
      <p><a href=\"{settings.frontend_url.rstrip('/')}/login\" style=\"display:inline-block;padding:12px 18px;background:#E57257;color:#fff;text-decoration:none;border-radius:10px;font-weight:700\">Log in</a></p>
      <p style=\"color:#5f5a52\">Support: {settings.support_email}</p>
    </div>
    """
    return _post_resend({"to": [email], "subject": subject, "html": html, "text": text})
