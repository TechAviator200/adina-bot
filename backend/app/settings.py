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
    snov_client_id: Optional[str] = None
    snov_client_secret: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    serpapi_api_key: Optional[str] = None
    serpapi_cache_ttl_days: int = 7
    disable_api_key_auth: bool = False  # Set DISABLE_API_KEY_AUTH=true for local dev only

    # Cost controls
    low_cost_mode: bool = True  # Caps discover at 20, no auto enrichment
    cache_ttl_serpapi_hours: int = 24
    cache_ttl_places_days: int = 30
    cache_ttl_hunter_days: int = 14

    # Google Places API (for company detail enrichment on click)
    google_places_api_key: Optional[str] = None

    # Gmail OAuth (DB-backed, per-user)
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None  # e.g. https://your-backend/api/gmail/auth/callback
    gmail_oauth_encryption_key: Optional[str] = None  # Fernet key (32-byte url-safe base64)

    @property
    def resolved_credentials_dir(self) -> Path:
        """Resolve credentials directory with fallback for Render free tier.
        
        If the configured credentials_dir points to /data/credentials but /data
        is not available (Render free tier), fall back to /tmp/credentials.
        """
        # Resolve the configured path
        credentials_path = Path(self.credentials_dir)
        if not credentials_path.is_absolute():
            # Relative to backend root
            backend_root = Path(__file__).resolve().parent.parent
            credentials_path = backend_root / credentials_path
        
        # Check if /data/credentials is requested but /data is not available
        if str(credentials_path).startswith('/data/') and not Path('/data').exists():
            logger.warning("/data directory not available (Render free tier), falling back to /tmp/credentials")
            credentials_path = Path('/tmp/credentials')
        
        return credentials_path

    class Config:
        extra = "ignore"  # Ignore extra env vars not defined in Settings


settings = Settings()

# Log which keys are configured (never log actual values)
logger.debug(
    "Settings loaded: API_KEY set? %s, HUNTER_API_KEY set? %s, SNOV_CLIENT_ID set? %s, GOOGLE_CSE_API_KEY set? %s, GOOGLE_CSE_CX set? %s, SERPAPI_API_KEY set? %s",
    settings.api_key is not None,
    settings.hunter_api_key is not None,
    settings.snov_client_id is not None,
    settings.google_cse_api_key is not None,
    settings.google_cse_cx is not None,
    settings.serpapi_api_key is not None,
)
