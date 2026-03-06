"""
outlook_service.py – Microsoft / Outlook OAuth service for ADINA.

Uses MSAL (Microsoft Authentication Library) to implement OAuth 2.0
authorization code flow for Microsoft 365 / Outlook mail sending.

Environment variables required:
  OUTLOOK_CLIENT_ID     – Azure app client ID
  OUTLOOK_CLIENT_SECRET – Azure app client secret
  OUTLOOK_REDIRECT_URI  – OAuth callback URL registered in Azure

Tokens are stored in the email_accounts table (Fernet-encrypted).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

OUTLOOK_SCOPES = [
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "offline_access",
]

AUTHORITY = "https://login.microsoftonline.com/common"
GRAPH_API_SEND = "https://graph.microsoft.com/v1.0/me/sendMail"


# ---------------------------------------------------------------------------
# Encryption helpers (re-used from gmail_service pattern)
# ---------------------------------------------------------------------------

def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        from app.settings import settings
        key = settings.gmail_oauth_encryption_key  # reuse same Fernet key
        if not key:
            return None
        raw = key.encode() if isinstance(key, str) else key
        return Fernet(raw)
    except Exception as exc:
        logger.error("Could not initialise Fernet for Outlook: %s", exc)
        return None


def _encrypt(fernet, value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def _decrypt(fernet, value: str) -> str:
    return fernet.decrypt(value.encode()).decode()


# ---------------------------------------------------------------------------
# MSAL availability check
# ---------------------------------------------------------------------------

def _get_msal():
    try:
        import msal
        return msal
    except ImportError:
        return None


def is_configured() -> bool:
    from app.settings import settings
    return bool(
        settings.outlook_client_id
        and settings.outlook_client_secret
        and settings.outlook_redirect_uri
    )


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def build_auth_url(user_key: str) -> Optional[str]:
    """Build Microsoft OAuth consent URL. Returns None if not configured."""
    msal = _get_msal()
    if not msal:
        logger.warning("msal not installed; cannot build Outlook auth URL")
        return None

    from app.settings import settings
    if not is_configured():
        return None

    app = msal.ConfidentialClientApplication(
        client_id=settings.outlook_client_id,
        client_credential=settings.outlook_client_secret,
        authority=AUTHORITY,
    )
    auth_url = app.get_authorization_request_url(
        scopes=OUTLOOK_SCOPES,
        redirect_uri=settings.outlook_redirect_uri,
        state=user_key,
    )
    return auth_url


def exchange_code(db, code: str, user_key: str) -> Optional[str]:
    """Exchange OAuth code for tokens, store encrypted. Returns email or None."""
    msal = _get_msal()
    if not msal:
        logger.error("msal not installed")
        return None

    from app.settings import settings
    from app.models import EmailAccount

    if not is_configured():
        logger.error("Outlook OAuth not configured")
        return None

    fernet = _get_fernet()
    if not fernet:
        logger.error("GMAIL_OAUTH_ENCRYPTION_KEY not set; cannot store Outlook tokens")
        return None

    app = msal.ConfidentialClientApplication(
        client_id=settings.outlook_client_id,
        client_credential=settings.outlook_client_secret,
        authority=AUTHORITY,
    )
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=OUTLOOK_SCOPES,
        redirect_uri=settings.outlook_redirect_uri,
    )

    if "error" in result:
        logger.error("Outlook token exchange error for user %s: %s – %s",
                     user_key, result["error"], result.get("error_description"))
        return None

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")

    # Get email address via Graph
    email_address = _get_email_from_graph(access_token)

    now = datetime.now(timezone.utc)
    expiry_secs = result.get("expires_in", 3600)
    expiry = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + expiry_secs, tz=timezone.utc
    )

    access_enc = _encrypt(fernet, access_token)
    refresh_enc = _encrypt(fernet, refresh_token) if refresh_token else None

    # Deactivate any previous Outlook account for this user
    existing_accounts = (
        db.query(EmailAccount)
        .filter(EmailAccount.user_key == user_key, EmailAccount.provider == "outlook")
        .all()
    )
    for acc in existing_accounts:
        db.delete(acc)

    account = EmailAccount(
        user_key=user_key,
        provider="outlook",
        email_address=email_address,
        access_token_encrypted=access_enc,
        refresh_token_encrypted=refresh_enc,
        token_expiry=expiry,
        is_active=0,
        created_at=now,
        updated_at=now,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    logger.info("Stored Outlook tokens for user %s (%s)", user_key, email_address)
    return email_address


def _get_email_from_graph(access_token: str) -> Optional[str]:
    try:
        import requests
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("mail") or resp.json().get("userPrincipalName")
    except Exception as exc:
        logger.warning("Could not fetch Outlook profile: %s", exc)
    return None


def _refresh_token_if_needed(db, account) -> Optional[str]:
    """Refresh access token if expired. Returns fresh access token or None."""
    msal = _get_msal()
    if not msal:
        return None

    from app.settings import settings
    fernet = _get_fernet()
    if not fernet or not account.refresh_token_encrypted:
        return None

    try:
        refresh_token = _decrypt(fernet, account.refresh_token_encrypted)
    except Exception:
        return None

    msal_app = msal.ConfidentialClientApplication(
        client_id=settings.outlook_client_id,
        client_credential=settings.outlook_client_secret,
        authority=AUTHORITY,
    )
    result = msal_app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=OUTLOOK_SCOPES,
    )
    if "error" in result:
        logger.error("Outlook token refresh failed: %s", result.get("error_description"))
        return None

    new_access = result.get("access_token", "")
    new_refresh = result.get("refresh_token", refresh_token)
    now = datetime.now(timezone.utc)

    account.access_token_encrypted = _encrypt(fernet, new_access)
    account.refresh_token_encrypted = _encrypt(fernet, new_refresh)
    account.token_expiry = datetime.fromtimestamp(
        now.timestamp() + result.get("expires_in", 3600), tz=timezone.utc
    )
    account.updated_at = now
    db.commit()
    return new_access


# ---------------------------------------------------------------------------
# Send email via Graph API
# ---------------------------------------------------------------------------

def send_email(db, account, to_email: str, subject: str, body: str) -> dict:
    """Send email via Microsoft Graph API."""
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "requests not installed"}

    fernet = _get_fernet()
    if not fernet:
        return {"success": False, "error": "Encryption key not configured"}

    try:
        access_token = _decrypt(fernet, account.access_token_encrypted)
    except Exception as exc:
        return {"success": False, "error": f"Token decryption failed: {exc}"}

    # Check expiry and refresh if needed
    expiry = account.token_expiry
    if expiry:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            refreshed = _refresh_token_if_needed(db, account)
            if refreshed:
                access_token = refreshed
            else:
                return {"success": False, "error": "Outlook token expired and refresh failed"}

    message_payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": "true",
    }

    try:
        resp = requests.post(
            GRAPH_API_SEND,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=message_payload,
            timeout=15,
        )
        if resp.status_code == 202:
            return {"success": True, "message_id": None}
        else:
            return {"success": False, "error": f"Graph API error {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
