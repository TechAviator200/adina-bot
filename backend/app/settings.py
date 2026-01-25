import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Compute absolute path to backend/.env from this file's location
# This file is at backend/app/settings.py, so backend/ is parent.parent
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _BACKEND_DIR / ".env"

# Explicitly load .env if it exists (production-safe: no error if missing)
if _DOTENV_PATH.exists():
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    logger.debug("Loaded .env from %s", _DOTENV_PATH)


class Settings(BaseSettings):
    database_url: str = "sqlite:///./adina.db"
    debug: bool = False
    demo_mode: bool = False
    credentials_dir: str = "credentials"
    oauth_redirect_uri: str = "http://127.0.0.1:8000/oauth/callback"
    api_key: Optional[str] = None
    hunter_api_key: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    disable_api_key_auth: bool = False  # Set DISABLE_API_KEY_AUTH=true for local dev only

    class Config:
        extra = "ignore"  # Ignore extra env vars not defined in Settings


settings = Settings()

# Log which keys are configured (never log actual values)
logger.debug(
    "Settings loaded: API_KEY set? %s, HUNTER_API_KEY set? %s, GOOGLE_CSE_API_KEY set? %s, GOOGLE_CSE_CX set? %s",
    settings.api_key is not None,
    settings.hunter_api_key is not None,
    settings.google_cse_api_key is not None,
    settings.google_cse_cx is not None,
)
