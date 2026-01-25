"""
Gmail integration module for ADINA.

Handles OAuth authentication and email sending via Gmail API.
Tokens are stored locally in environment-specified path.
"""

import base64
import json
import os
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, TypedDict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.settings import settings

# Gmail API scopes - send and read
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Daily send limit
DAILY_SEND_LIMIT = 100

# OAuth redirect URI - must match Google Cloud Console configuration
OAUTH_REDIRECT_URI = settings.oauth_redirect_uri

# Resolve credentials directory (relative paths resolved from backend root)
_BACKEND_ROOT = Path(__file__).parent.parent
_CREDENTIALS_DIR = Path(settings.credentials_dir)
if not _CREDENTIALS_DIR.is_absolute():
    _CREDENTIALS_DIR = _BACKEND_ROOT / _CREDENTIALS_DIR
_CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


class GmailConfig:
    """Configuration for Gmail integration."""

    def __init__(self):
        self.credentials_path = _CREDENTIALS_DIR / "gmail_credentials.json"
        self.token_path = _CREDENTIALS_DIR / "gmail_token.json"
        self.daily_limit = int(os.environ.get("GMAIL_DAILY_LIMIT", DAILY_SEND_LIMIT))


class SendResult(TypedDict):
    success: bool
    message_id: Optional[str]
    error: Optional[str]


def get_gmail_config() -> GmailConfig:
    """Get Gmail configuration from environment."""
    return GmailConfig()


def is_connected() -> bool:
    """Check if Gmail is connected (valid token exists)."""
    config = get_gmail_config()
    if not config.token_path.exists():
        return False

    try:
        creds = Credentials.from_authorized_user_file(str(config.token_path), SCOPES)
        return creds.valid or creds.refresh_token is not None
    except Exception:
        return False


def get_credentials() -> Optional[Credentials]:
    """
    Get valid Gmail credentials.

    Returns existing credentials if valid, refreshes if expired,
    or returns None if no valid credentials exist.
    """
    config = get_gmail_config()

    if not config.token_path.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(config.token_path), SCOPES)

        if creds.valid:
            return creds

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(config.token_path, "w") as token_file:
                token_file.write(creds.to_json())
            return creds

        return None
    except Exception:
        return None


def start_oauth_flow() -> dict:
    """
    Start OAuth flow and return authorization URL.

    Returns a dict with:
    - auth_url: URL to redirect user to for authorization
    - state: State token for verification

    The OAuth flow uses a local redirect URI for desktop apps.
    """
    config = get_gmail_config()

    if not config.credentials_path.exists():
        raise FileNotFoundError(
            f"Gmail credentials file not found at {config.credentials_path}. "
            "Please download OAuth credentials from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.credentials_path),
        SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    return {
        "auth_url": auth_url,
        "state": state,
    }


def complete_oauth_flow_local() -> dict:
    """
    Complete OAuth flow using local server (for development).

    Opens a browser window for the user to authorize, then
    captures the callback and saves the token.

    Returns:
        dict with success status and message
    """
    config = get_gmail_config()

    if not config.credentials_path.exists():
        return {
            "success": False,
            "error": f"Gmail credentials file not found at {config.credentials_path}",
        }

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_path),
            SCOPES,
        )

        # This will open a browser and run a local server to capture the callback
        creds = flow.run_local_server(port=8080)

        # Ensure credentials directory exists
        config.token_path.parent.mkdir(parents=True, exist_ok=True)

        # Save the credentials
        with open(config.token_path, "w") as token_file:
            token_file.write(creds.to_json())

        return {
            "success": True,
            "message": "Gmail connected successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def complete_oauth_with_code(code: str, state: Optional[str] = None) -> dict:
    """
    Complete OAuth flow with authorization code.

    Args:
        code: Authorization code from Google
        state: State token for verification (optional)

    Returns:
        dict with success status and message
    """
    config = get_gmail_config()

    if not config.credentials_path.exists():
        return {
            "success": False,
            "error": f"Gmail credentials file not found at {config.credentials_path}",
        }

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_path),
            SCOPES,
            redirect_uri=OAUTH_REDIRECT_URI,
        )

        flow.fetch_token(code=code)
        creds = flow.credentials

        # Ensure credentials directory exists
        config.token_path.parent.mkdir(parents=True, exist_ok=True)

        # Save the credentials
        with open(config.token_path, "w") as token_file:
            token_file.write(creds.to_json())

        return {
            "success": True,
            "message": "Gmail connected successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected. Please connect via /api/gmail/connect first.")

    return build("gmail", "v1", credentials=creds)


def create_message(to: str, subject: str, body: str) -> dict:
    """
    Create a Gmail message object.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        Gmail API message object
    """
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    # Encode as base64url
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    return {"raw": raw}


def send_email(to: str, subject: str, body: str) -> SendResult:
    """
    Send an email via Gmail API.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body

    Returns:
        SendResult with success status, message_id, and any error
    """
    try:
        service = get_gmail_service()
        message = create_message(to, subject, body)

        result = service.users().messages().send(userId="me", body=message).execute()

        return SendResult(
            success=True,
            message_id=result.get("id"),
            error=None,
        )
    except HttpError as e:
        return SendResult(
            success=False,
            message_id=None,
            error=f"Gmail API error: {e.reason}",
        )
    except RuntimeError as e:
        return SendResult(
            success=False,
            message_id=None,
            error=str(e),
        )
    except Exception as e:
        return SendResult(
            success=False,
            message_id=None,
            error=f"Unexpected error: {str(e)}",
        )


def get_connection_status() -> dict:
    """
    Get Gmail connection status.

    Returns:
        dict with connected status, email (if connected), and any errors
    """
    config = get_gmail_config()

    if not config.credentials_path.exists():
        return {
            "connected": False,
            "email": None,
            "error": "Gmail credentials file not configured",
        }

    if not is_connected():
        return {
            "connected": False,
            "email": None,
            "error": None,
        }

    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()

        return {
            "connected": True,
            "email": profile.get("emailAddress"),
            "error": None,
        }
    except HttpError as e:
        if e.resp.status == 403:
            return {
                "connected": False,
                "email": None,
                "error": "Gmail API is not enabled. Please enable the Gmail API in your Google Cloud Console project.",
            }
        return {
            "connected": False,
            "email": None,
            "error": f"Gmail API error: {e.reason}",
        }
    except Exception as e:
        return {
            "connected": False,
            "email": None,
            "error": str(e),
        }


def disconnect() -> dict:
    """
    Disconnect Gmail by removing stored token.

    Returns:
        dict with success status
    """
    config = get_gmail_config()

    try:
        if config.token_path.exists():
            config.token_path.unlink()

        return {
            "success": True,
            "message": "Gmail disconnected",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
