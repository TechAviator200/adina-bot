"""
gmail_service.py – DB-backed Gmail OAuth service with per-user encrypted token storage.

Design:
- Tokens are stored in the `gmail_tokens` table, keyed by `user_key` (default "local_user").
- Tokens are Fernet-encrypted at rest using GMAIL_OAUTH_ENCRYPTION_KEY.
- Token refresh is automatic when access tokens expire.
- Multiple users are supported via the x-user-key request header.

This module does NOT read any files at import time.
"""
import base64 as _b64
import email.mime.text
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

DEFAULT_USER_KEY = "local_user"


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance if GMAIL_OAUTH_ENCRYPTION_KEY is set, else None."""
    try:
        from cryptography.fernet import Fernet
        from app.settings import settings
        key = settings.gmail_oauth_encryption_key
        if not key:
            return None
        raw = key.encode() if isinstance(key, str) else key
        return Fernet(raw)
    except Exception as exc:
        logger.error("Could not initialise Fernet: %s", exc)
        return None


def _encrypt(fernet, value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def _decrypt(fernet, value: str) -> str:
    return fernet.decrypt(value.encode()).decode()


# ---------------------------------------------------------------------------
# Token storage / retrieval
# ---------------------------------------------------------------------------

def _get_token_row(db, user_key: str):
    from app.models import GmailToken
    return db.query(GmailToken).filter(GmailToken.user_key == user_key).first()


def get_credentials(db, user_key: str):
    """Return valid google.oauth2.credentials.Credentials or None."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from app.settings import settings
    except ImportError:
        logger.warning("google-auth not installed; cannot get credentials")
        return None

    row = _get_token_row(db, user_key)
    if not row:
        return None

    fernet = _get_fernet()
    if not fernet:
        logger.error("GMAIL_OAUTH_ENCRYPTION_KEY not set; cannot decrypt tokens for user %s", user_key)
        return None

    try:
        access_token = _decrypt(fernet, row.access_token_encrypted)
        refresh_token = (
            _decrypt(fernet, row.refresh_token_encrypted)
            if row.refresh_token_encrypted
            else None
        )
    except Exception as exc:
        logger.error("Token decryption failed for user %s: %s", user_key, exc)
        return None

    expiry = row.token_expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    creds.expiry = expiry

    # Auto-refresh if expired
    if creds.expired and refresh_token:
        try:
            creds.refresh(Request())
            # Persist updated token
            row.access_token_encrypted = _encrypt(fernet, creds.token)
            row.token_expiry = creds.expiry
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("Refreshed access token for user %s", user_key)
        except Exception as exc:
            logger.error("Token refresh failed for user %s: %s", user_key, exc)
            return None

    return creds


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def build_auth_url(user_key: str) -> Optional[str]:
    """Build Google consent screen URL. Returns None if OAuth is not configured."""
    try:
        from google_auth_oauthlib.flow import Flow
        from app.settings import settings
    except ImportError:
        return None

    if not settings.google_client_id or not settings.google_client_secret:
        return None

    redirect_uri = settings.google_redirect_uri or settings.oauth_redirect_uri

    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=user_key,
        prompt="consent",
    )
    return auth_url


def exchange_code(db, code: str, user_key: str) -> Optional[str]:
    """Exchange OAuth code for tokens, store encrypted. Returns email or None."""
    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        from app.settings import settings
        from app.models import GmailToken
    except ImportError as exc:
        logger.error("Missing dependency for exchange_code: %s", exc)
        return None

    if not settings.google_client_id or not settings.google_client_secret:
        logger.error("Google OAuth credentials not configured")
        return None

    fernet = _get_fernet()
    if not fernet:
        logger.error("GMAIL_OAUTH_ENCRYPTION_KEY not set; cannot store tokens")
        return None

    redirect_uri = settings.google_redirect_uri or settings.oauth_redirect_uri
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    try:
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as exc:
        logger.error("OAuth code exchange failed for user %s: %s", user_key, exc)
        return None

    # Retrieve Gmail email address
    try:
        svc = build("gmail", "v1", credentials=creds)
        profile = svc.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "")
    except Exception as exc:
        logger.warning("Could not retrieve Gmail profile for user %s: %s", user_key, exc)
        email_address = ""

    access_enc = _encrypt(fernet, creds.token)
    refresh_enc = _encrypt(fernet, creds.refresh_token) if creds.refresh_token else ""
    now = datetime.now(timezone.utc)

    existing = _get_token_row(db, user_key)
    if existing:
        existing.access_token_encrypted = access_enc
        existing.refresh_token_encrypted = refresh_enc
        existing.scope = " ".join(creds.scopes or [])
        existing.token_expiry = creds.expiry
        existing.email_address = email_address
        existing.updated_at = now
    else:
        from app.models import GmailToken
        db.add(GmailToken(
            user_key=user_key,
            provider="google",
            access_token_encrypted=access_enc,
            refresh_token_encrypted=refresh_enc,
            scope=" ".join(creds.scopes or []),
            token_expiry=creds.expiry,
            email_address=email_address,
            created_at=now,
            updated_at=now,
        ))
    db.commit()
    logger.info("Stored Gmail tokens for user %s (%s)", user_key, email_address)
    return email_address


def disconnect(db, user_key: str) -> bool:
    """Delete stored tokens for user_key. Returns True if a row was deleted."""
    row = _get_token_row(db, user_key)
    if row:
        db.delete(row)
        db.commit()
        logger.info("Disconnected Gmail for user %s", user_key)
        return True
    return False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_status(db, user_key: str) -> dict:
    """Return {connected: bool, email: str|None, source: 'db'|'file'}."""
    row = _get_token_row(db, user_key)
    if row:
        return {"connected": True, "email": row.email_address, "source": "db"}
    return {"connected": False, "email": None, "source": "db"}


# ---------------------------------------------------------------------------
# Send email
# ---------------------------------------------------------------------------

def send_email(db, user_key: str, to_email: str, subject: str, body: str) -> dict:
    """Send an email from the authenticated Gmail account for user_key."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("google-api-python-client not installed")

    creds = get_credentials(db, user_key)
    if not creds:
        raise ValueError(f"No valid Gmail credentials for user '{user_key}'. Please connect Gmail first.")

    msg = email.mime.text.MIMEText(body)
    msg["to"] = to_email
    msg["subject"] = subject
    raw = _b64.urlsafe_b64encode(msg.as_bytes()).decode()

    svc = build("gmail", "v1", credentials=creds)
    result = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"success": True, "message_id": result.get("id")}
