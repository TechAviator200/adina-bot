"""
smtp_service.py – SMTP-based email sending for Yahoo and custom mailboxes.

Credentials are Fernet-encrypted at rest in the email_accounts table.
Supports TLS (port 587 STARTTLS) and SSL (port 465).
"""
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


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
        logger.error("Could not initialise Fernet for SMTP: %s", exc)
        return None


def _encrypt(fernet, value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def _decrypt(fernet, value: str) -> str:
    return fernet.decrypt(value.encode()).decode()


def test_smtp_connection(host: str, port: int, username: str, password: str) -> dict:
    """
    Test SMTP credentials by opening a connection and logging in.
    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                server.login(username, password)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
        return {"success": True}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Authentication failed. Check username/password or app password."}
    except smtplib.SMTPConnectError as exc:
        return {"success": False, "error": f"Could not connect to {host}:{port} — {exc}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def send_email(db, account, to_email: str, subject: str, body: str) -> dict:
    """Send email via SMTP using encrypted credentials stored in account row."""
    fernet = _get_fernet()
    if not fernet:
        return {"success": False, "error": "Encryption key not configured"}

    try:
        username = _decrypt(fernet, account.smtp_username_encrypted)
        password = _decrypt(fernet, account.smtp_password_encrypted)
    except Exception as exc:
        return {"success": False, "error": f"Credential decryption failed: {exc}"}

    host = account.smtp_host
    port = account.smtp_port or 587
    from_addr = account.email_address or username

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(username, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        return {"success": True, "message_id": None}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "SMTP authentication failed"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
