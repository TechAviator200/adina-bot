"""
Adina Bot API - Backend Server

Required Environment Variables:
------------------------------
- API_KEY: Secret key for authenticating API requests (required in production)
- DATABASE_URL: SQLite/Postgres connection string (default: sqlite:///./adina.db)
- HUNTER_API_KEY: Hunter.io API key for lead discovery (optional)
- OAUTH_REDIRECT_URI: OAuth callback URL (default: http://127.0.0.1:8000/oauth/callback)
- DEMO_MODE: Set to "true" to disable email sending (default: false)
- DISABLE_API_KEY_AUTH: Set to "true" to skip API key checks for local dev only (default: false)

API Key Authentication:
----------------------
All /api/* endpoints require the `x-api-key` header (lowercase).
The header value must match the API_KEY environment variable.

curl examples:
    # Health check (no auth required)
    curl http://127.0.0.1:8000/health

    # Get leads (requires API key)
    curl -H "x-api-key: your-api-key" http://127.0.0.1:8000/api/leads

    # Upload leads CSV
    curl -X POST -H "x-api-key: your-api-key" \
         -F "file=@leads.csv" http://127.0.0.1:8000/api/leads/upload

Local Development:
-----------------
To disable API key auth for local development, set:
    DISABLE_API_KEY_AUTH=true

WARNING: Never set DISABLE_API_KEY_AUTH=true in production!
"""
import csv
import hashlib
import io
import json
import logging
import os
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional as _Optional

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, text

from app.settings import settings
from app.db import Base, engine, get_db
from app.models import Lead, SentEmail, DailyEmailCount, CompanyDiscoveryCache, PlacesCache, HunterCache, GmailToken
from app.schemas import (
    HealthResponse,
    ReadinessCheck,
    ReadinessResponse,
    LeadRead,
    UploadResponse,
    StatusResponse,
    StatusCount,
    DraftResponse,
    ScoreResponse,
    ApprovalResponse,
    ReplyDraftRequest,
    ReplyDraftResponse,
    SendReplyRequest,
    SaveDraftRequest,
    GmailConnectResponse,
    GmailConnectRequest,
    GmailSendResponse,
    BatchSendRequest,
    BatchSendResponse,
    BatchSendError,
    SentEmailRead,
    WorkflowSendResponse,
    ContactEmailUpdate,
    ContactEmailResponse,
    LeadStatusUpdate,
    LeadStatusResponse,
    PullLeadsRequest,
    PullLeadsResponse,
    DiscoverLeadsRequest,
    DiscoverLeadsResponse,
    DiscoveredLead,
    # Company discovery schemas
    CompanyDiscoverRequest,
    CompanyDiscoverResponse,
    DiscoveredCompany,
    CompanyContactsRequest,
    CompanyContactsResponse,
    ExecutiveContact,
    ImportCompaniesRequest,
    ImportCompaniesResponse,
    # Profile schemas
    LeadProfile,
    ProfileContact,
)
from app.agent.outbound import draft_outreach_email
from app.agent.scoring import score_lead, get_quality_label, has_negative_signal
from app.agent.responses import classify_reply, draft_followup_with_context
# Gmail is optional - app must not crash if google libs are missing
try:
    from app import gmail
except ImportError:
    gmail = None  # type: ignore

# DB-backed Gmail service (per-user, encrypted tokens — preferred over file-based)
try:
    from app import gmail_service
except ImportError:
    gmail_service = None  # type: ignore

# Google CSE is optional - app must not crash if google libs are missing
try:
    from services.google_cse_service import GoogleCSEService
except ImportError:
    GoogleCSEService = None  # type: ignore

# Hunter.io service for lead discovery
try:
    from services.hunter_service import HunterService
except ImportError:
    HunterService = None  # type: ignore

# Snov.io service for lead discovery
try:
    from services.snov_service import SnovService
except ImportError:
    SnovService = None  # type: ignore

# SerpAPI service for company discovery
try:
    from services.serpapi_service import SerpAPIService
except ImportError:
    SerpAPIService = None  # type: ignore

# Response playbook for templates
from app.utils.response_playbook import RESPONSE_PLAYBOOK
from app.utils.knowledge_pack import KNOWLEDGE_PACK

logger = logging.getLogger(__name__)

if GoogleCSEService is None:
    logger.warning(
        "Google CSE disabled: google libraries not installed"
    )

if HunterService is None:
    logger.warning(
        "Hunter.io disabled: service not available"
    )

if SnovService is None:
    logger.warning(
        "Snov.io disabled: service not available"
    )

if SerpAPIService is None:
    logger.warning(
        "SerpAPI disabled: service not available"
    )

if gmail is None:
    logger.warning(
        "Gmail disabled: google libraries not installed"
    )


# ---------------------------------------------------------------------------
# Per-user helpers
# ---------------------------------------------------------------------------

def get_user_key(request: Request) -> str:
    """Extract user identity from x-user-key header; default 'local_user'."""
    return request.headers.get("x-user-key", "local_user")


def _gmail_status_for_user(db, user_key: str) -> dict:
    """Return {connected, email} — DB service first, fall back to file-based.
    Never surfaces internal file/config errors to the caller; returns a clean
    not-connected dict instead so the UI shows a neutral state."""
    if gmail_service is not None:
        st = gmail_service.get_status(db, user_key)
        if st["connected"]:
            return st
    # File-based fallback: only propagate if actually connected (ignore config errors)
    if gmail is not None:
        st = gmail.get_connection_status()
        if st.get("connected"):
            return st
    return {"connected": False, "email": None}


def _is_gmail_connected(db, user_key: str) -> bool:
    return _gmail_status_for_user(db, user_key)["connected"]


def _send_email_for_user(db, user_key: str, to: str, subject: str, body: str) -> dict:
    """Send via DB-backed service if connected, fall back to file-based."""
    if gmail_service is not None:
        st = gmail_service.get_status(db, user_key)
        if st["connected"]:
            try:
                return gmail_service.send_email(db, user_key, to, subject, body)
            except Exception as exc:
                logger.error("DB gmail send failed for user %s: %s", user_key, exc)
                return {"success": False, "error": str(exc)}
    if gmail is not None and gmail.is_connected():
        return gmail.send_email(to=to, subject=subject, body=body)
    return {"success": False, "error": "Gmail not connected. Connect in Settings first."}


# ---------------------------------------------------------------------------
# Description resolution helpers (priority chain for "About" section)
# ---------------------------------------------------------------------------

def _scrape_website_description(url: str) -> _Optional[str]:
    """
    Scrape a company's meta description or H1 from their website.
    Returns None on failure or if the result is too short to be useful.
    Uses a short timeout (5s) so it doesn't block the profile endpoint.
    """
    try:
        import requests as _requests
        if not url.startswith("http"):
            url = f"https://{url}"
        resp = _requests.get(
            url, timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AdinaBot/1.0)"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        html = resp.text

        # Try <meta name="description" content="..."> (both attribute orderings)
        m = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']{20,500})["\']',
            html, re.IGNORECASE
        )
        if not m:
            m = re.search(
                r'<meta\s+content=["\']([^"\']{20,500})["\']\s+name=["\']description["\']',
                html, re.IGNORECASE
            )
        if m:
            return m.group(1).strip()[:400]

        # Fall back to first <h1>
        h = re.search(r'<h1[^>]*>([^<]{5,200})</h1>', html, re.IGNORECASE)
        if h:
            text = re.sub(r'\s+', ' ', h.group(1)).strip()
            if len(text) >= 10:
                return text[:200]

        return None
    except Exception:
        return None


def _get_icp_description(industry: _Optional[str]) -> _Optional[str]:
    """
    Return a context-aware ICP description from knowledge_pack.
    Tries to match the lead's industry to an ideal_customer entry; falls back
    to the ADINA one_liner.
    """
    one_liner = KNOWLEDGE_PACK.get("one_liner", "")
    ideal_customers = KNOWLEDGE_PACK.get("ideal_customers", [])

    if industry:
        industry_lower = industry.lower()
        for ic in ideal_customers:
            if industry_lower in ic.lower():
                return ic

    return one_liner or None


def _resolve_description(lead, db) -> _Optional[str]:
    """
    Priority chain for the "About" section:
    1. lead.notes (internal CSV notes — source of truth)
    2. lead.company_description (cached scrape or previously stored external description)
    3. Live website scrape (lazy; result cached in company_description on first success)
    4. ICP description from knowledge_pack (industry-matched ideal customer profile)
    """
    # 1. Internal notes are the operator's source of truth
    if lead.notes and lead.notes.strip():
        return lead.notes.strip()

    # 2. Previously cached external description
    if lead.company_description and lead.company_description.strip():
        return lead.company_description.strip()

    # 3. Live scrape (cached on success)
    if lead.website:
        scraped = _scrape_website_description(lead.website)
        if scraped:
            lead.company_description = scraped
            try:
                db.commit()
            except Exception:
                db.rollback()
            return scraped

    # 4. ICP fallback from knowledge_pack
    return _get_icp_description(lead.industry)


def run_db_migrations(engine) -> None:
    """Add new columns to existing tables if they don't exist (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE leads ADD COLUMN phone VARCHAR",
        "ALTER TABLE leads ADD COLUMN linkedin_url VARCHAR",
        "ALTER TABLE leads ADD COLUMN contacts_json TEXT",
        "ALTER TABLE leads ADD COLUMN company_description TEXT",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
                logger.info("Migration applied: %s", stmt)
            except Exception:
                # Column already exists — safe to ignore
                conn.rollback()


# Create database tables (with error handling for production)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    run_db_migrations(engine)
except Exception as e:
    logger.error("Failed to create database tables: %s", e)
    # In production, we might want to exit or handle this differently
    # For now, log the error but continue

app = FastAPI(title="Adina Bot API")


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting Adina Bot API...")
    
    # Log configuration
    logger.info("OAUTH_REDIRECT_URI = %s", settings.oauth_redirect_uri)
    logger.info("CREDENTIALS_DIR = %s", settings.resolved_credentials_dir)
    logger.info("DEMO_MODE = %s", settings.demo_mode)
    logger.info("DATABASE_URL = %s", settings.database_url.replace(settings.database_url.split('@')[0].split('//')[1].split(':')[0], '***') if '@' in settings.database_url else settings.database_url)
    
    # Try to create database tables and run migrations
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
        run_db_migrations(engine)
    except Exception as e:
        logger.error("Failed to create database tables: %s", e)
        logger.warning("Application will continue, but database operations may fail")
    
    logger.info("Adina Bot API startup complete")

# CORS middleware for frontend

# CORS origins for local dev and deployed frontend
_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    # Add your deployed frontend domain below:
    "https://adina-bot.onrender.com",
]
_frontend_url = os.environ.get("FRONTEND_URL")
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Skip auth for CORS preflight requests
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response
    if request.url.path.startswith("/api/"):
        # Allow bypassing auth for local development only
        if settings.disable_api_key_auth:
            logger.warning("API key auth disabled (DISABLE_API_KEY_AUTH=true)")
        else:
            # Check API_KEY is configured
            if not settings.api_key:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "API_KEY environment variable not configured on server"},
                )
            # Check x-api-key header (lowercase)
            key = request.headers.get("x-api-key")
            if not key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing x-api-key header. Include header: x-api-key: <your-api-key>"},
                )
            if key != settings.api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key. Check that x-api-key header matches API_KEY env var."},
                )
    response = await call_next(request)
    return response


@app.get("/console", response_class=HTMLResponse)
def operator_console():
    """Serve the operator console UI."""
    html_path = Path(__file__).parent / "console.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/ready")
def readiness_check():
    return {"status": "ready"}


@app.get("/api/config")
def get_config():
    return {
        "demo_mode": settings.demo_mode,
        "oauth_redirect_uri": settings.oauth_redirect_uri,
    }


_KNOWLEDGE_PACK_PATH = Path(__file__).parent / "knowledge_pack.json"


@app.get("/api/templates")
def get_templates():
    """Return outreach response templates from the playbook in defined order."""
    templates = RESPONSE_PLAYBOOK.get("followup_templates", {})
    # Explicit ordering as defined in materials
    INTENT_ORDER = ["positive", "neutral", "objection", "deferral", "negative"]
    result = []
    for intent in INTENT_ORDER:
        if intent not in templates:
            continue
        config = templates[intent]
        template_text = config.get("template", "")
        if not template_text and "templates_by_objection" in config:
            template_text = config["templates_by_objection"].get("default", "")
        result.append({
            "intent": intent,
            "tone": config.get("tone", ""),
            "template": template_text,
            "cta": config.get("cta", ""),
        })
    return result


# Outreach templates from the email response playbook PDF
OUTREACH_TEMPLATES = [
    {
        "id": "close_friends",
        "name": "Close Friends/Former Colleagues",
        "subject": "Quick favor?",
        "body": """Hey [Name],

I officially launched my consulting firm, ADINA & Co., this month. I have built a team that works with growth stage founders as an operational co-founder to build and run the systems behind the business so they can focus on growth instead of day-to-day execution.

Right now, we are looking to connect with founders in [CHOOSE 3: healthtech, wellness and beauty, creative, or service based] businesses who are scaling but are feeling overwhelmed operationally.

If anyone comes to mind who could use hands-on operational leadership right now, I would really appreciate an introduction. Even one name helps.

Warmly,
Ify""",
    },
    {
        "id": "professional_network",
        "name": "Professional Network",
        "subject": "Can you help me grow ADINA & Co.?",
        "body": """Hi [Name],

Hope you're well! I wanted to share that my team and I recently launched our consulting firm, ADINA & Co.

We work with growth-stage founders as an operational co-founder to build and run the systems behind the business so they can focus on growth instead of day-to-day execution.

Given your network in [industry or community], I thought you might know a few founders who are scaling but struggling to keep operations running effectively as the business grows. If anyone comes to mind, I would really appreciate an introduction.

If helpful, I am happy to share a brief overview you can forward along.

Thanks,
Ify""",
    },
    {
        "id": "direct_prospect",
        "name": "Direct to Prospect",
        "subject": "Is your business being slowed down?",
        "body": """Hi [Name],

I came across [Company Name] and was impressed by [specific thing - recent growth/expansion/product launch].

At ADINA, we work with growth-stage companies at the point where execution starts to overwhelm leadership and team capacity. As the business grows, decisions bottleneck, teams slow down, and the systems that got them here aren't built for where they're going.

Our team steps in as an operational co-founder to build and run the systems that allow companies to scale without adding leadership or team burden.

If you are open to it, I would welcome a brief conversation to understand where things stand operationally and see if there is a fit.

Here is my calendar if you would like to grab 30 minutes: [link]

Best,
Ify""",
    },
    {
        "id": "direct_prospect_b2b",
        "name": "Direct to Prospect (B2B)",
        "subject": "Is your business being slowed down?",
        "body": """Hi [Name],

I came across [Company Name] and was impressed by [specific thing].

At ADINA, we work with growth-stage founders at the point where they've become the bottleneck in their business. As the company grows, decisions pile up waiting for their approval, execution slows down, and the systems that got them here aren't built for where they're going.

Our team steps in as an operational co-founder to build and run the systems that allow founders to scale without being stuck in every decision.

I'd welcome a brief conversation to understand where you are operationally and see if there's a fit. Here's my calendar if 30 minutes works: [link]

Best,
Ify""",
    },
    {
        "id": "qualifying",
        "name": "Qualifying Email",
        "subject": "Addressing [Prospect's Company]'s [key challenge]",
        "body": """Hi [Prospect Name],

I really enjoyed our conversation yesterday about how [Prospect's Company] is tackling [key challenge]. The way you're approaching [specific challenge mentioned by prospect] is particularly impressive.

From what you shared, it sounds like finding solutions for [Priority 1], [Priority 2], and [Priority 3] is top of mind right now. I'm excited about the possibility of [product/service] helping you achieve those goals through:

• [Solution 1] that specifically addresses [related challenge 1]
• [Solution 2] which could optimize [related challenge 2]
• [Solution 3] to help you streamline [related challenge 3]

To make sure I'm giving you the most relevant information, I'd love to set up a quick call to dive deeper into your unique needs. Would you be open to a brief chat on [available dates and times]?

Thanks again for your time.

Best,
[Your Name]""",
    },
    {
        "id": "closing",
        "name": "Closing the Sale",
        "subject": "Let's get started, [Prospect Name]! Agreement attached.",
        "body": """Hi [Prospect Name],

I'm thrilled to be taking this next step with you and [Prospect's Company].

You'll find the agreement attached for your review. Feel free to reach out if you have any questions or would like to discuss any specific details.

Once you've signed, we'll start the onboarding process and get you up and running with [product/service] as smoothly as possible.

We're truly invested in your success, and I can't wait to see the amazing things we'll achieve together.

Best,
[Your Name]""",
    },
    {
        "id": "followup",
        "name": "Follow-up Email",
        "subject": "Checking in on your [product/service] experience",
        "body": """Hi [Customer Name],

I hope you've been enjoying [product/service].

I'm reaching out to see how things are going since you started using [product/service]. Have you had a chance to fully explore [highlight some features]? Are you noticing any positive impact yet?

I'm eager to make sure you're getting the most out of [product/service]. Feel free to ask if you have any questions or need help with anything.

Best,
[Your Name]""",
    },
]


@app.get("/api/outreach-templates")
def get_outreach_templates():
    """Return outreach email templates from the ADINA playbook."""
    return OUTREACH_TEMPLATES


@app.get("/api/readiness", response_model=ReadinessResponse)
def readiness_check(db: Session = Depends(get_db)):
    """Verify core dependencies are operational."""
    # 1. Database
    try:
        db.execute(text("SELECT 1"))
        db_check = ReadinessCheck(ok=True)
    except Exception as e:
        db_check = ReadinessCheck(ok=False, error=str(e))

    # 2. Knowledge pack
    try:
        data = json.loads(_KNOWLEDGE_PACK_PATH.read_text())
        if not isinstance(data, dict):
            raise ValueError("knowledge_pack.json is not a JSON object")
        kp_check = ReadinessCheck(ok=True)
    except FileNotFoundError:
        kp_check = ReadinessCheck(ok=False, error="knowledge_pack.json not found")
    except (json.JSONDecodeError, ValueError) as e:
        kp_check = ReadinessCheck(ok=False, error=str(e))

    # 3. Gmail (informational — not required for readiness)
    if gmail is None:
        gmail_check = ReadinessCheck(ok=True, error="Gmail libraries not available")
    else:
        config = gmail.get_gmail_config()
        if config.token_path.exists():
            gmail_check = ReadinessCheck(ok=True)
        elif config.credentials_path.exists():
            gmail_check = ReadinessCheck(ok=True, error="Token missing — Gmail not yet connected")
        else:
            gmail_check = ReadinessCheck(ok=True, error="No credentials configured")

    ready = db_check.ok and kp_check.ok
    return ReadinessResponse(
        ready=ready,
        database=db_check,
        knowledge_pack=kp_check,
        gmail=gmail_check,
    )


from typing import List, Optional


def parse_employees(value: str) -> Optional[int]:
    """Parse employee count from string. Handles ranges like '1-10', '11-50', etc."""
    value = value.strip()
    if not value:
        return None

    # Handle range format: "1-10" -> 6, "11-50" -> 30, "51-200" -> 125
    if "-" in value:
        try:
            parts = value.split("-")
            low = int(parts[0].strip())
            high = int(parts[1].strip())
            return (low + high) // 2
        except (ValueError, IndexError):
            return None

    # Handle plain numeric
    try:
        return int(value)
    except ValueError:
        return None


def normalize_stage(stage: str) -> Optional[str]:
    """Normalize stage value. Single letter stages like 'A' become 'Series A'."""
    stage = stage.strip()
    if not stage:
        return None
    # If it's a single letter (A, B, C, etc.), treat as Series X
    if len(stage) == 1 and stage.isalpha():
        return f"Series {stage.upper()}"
    return stage


@app.post("/api/leads/upload", response_model=UploadResponse)
async def upload_leads(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    # Normalize headers: lowercase and strip whitespace
    if reader.fieldnames:
        normalized_fieldnames = [f.lower().strip() for f in reader.fieldnames]
        reader.fieldnames = normalized_fieldnames

    inserted = 0
    skipped = 0
    total_rows_parsed = 0

    for row in reader:
        # Normalize row keys to lowercase
        row = {k.lower().strip(): v for k, v in row.items()}

        company = row.get("company", "").strip()

        # Skip duplicate header rows where company == "company"
        if company.lower() == "company":
            continue

        total_rows_parsed += 1

        # Validation: company is required
        if not company:
            skipped += 1
            continue

        # Industry: default to "Unknown" if missing
        industry = row.get("industry", "").strip() or "Unknown"

        employees = parse_employees(row.get("employees", ""))
        stage = normalize_stage(row.get("stage", ""))

        # Map linkedin_url to source_url and set source="linkedin"
        linkedin_url = row.get("linkedin_url", "").strip()
        source = "linkedin" if linkedin_url else None
        source_url = linkedin_url or None

        lead = Lead(
            company=company,
            industry=industry,
            location=row.get("location", "").strip() or None,
            employees=employees,
            stage=stage,
            website=row.get("website", "").strip() or None,
            notes=row.get("notes", "").strip() or None,
            contact_name=row.get("contact_name", "").strip() or None,
            contact_role=row.get("contact_role", "").strip() or None,
            contact_email=row.get("contact_email", "").strip() or None,
            source=source,
            source_url=source_url,
        )
        db.add(lead)
        inserted += 1

    db.commit()

    return UploadResponse(
        inserted=inserted, skipped=skipped, total_rows_parsed=total_rows_parsed
    )


@app.get("/api/leads", response_model=List[LeadRead])
def get_leads(db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.created_at.desc()).limit(200).all()
    return leads


@app.post("/api/leads/pull", response_model=PullLeadsResponse)
def pull_leads(request: PullLeadsRequest, db: Session = Depends(get_db)):
    hunter = HunterService()
    added = 0

    for domain in request.domains:
        try:
            people = hunter.domain_search(domain)
        except Exception as e:
            logger.error("Hunter API error for domain %s: %s", domain, e)
            raise HTTPException(status_code=502, detail=f"Hunter API error: {e}")

        if not people:
            continue

        # Deduplicate: skip if a lead with this domain/website already exists
        existing = db.query(Lead).filter(Lead.website.ilike(f"%{domain}%")).first()
        if existing:
            # Update contacts_json on existing lead if it's empty
            if not existing.contacts_json and people:
                contacts_list = [
                    {
                        "name": p.get("name") or "Unknown",
                        "title": p.get("job_title"),
                        "email": p.get("email"),
                        "linkedin_url": p.get("linkedin_url"),
                        "source": "hunter",
                    }
                    for p in people
                ]
                existing.contacts_json = json.dumps(contacts_list)
                db.commit()
            continue

        # Build full contacts list for contacts_json
        contacts_list = [
            {
                "name": p.get("name") or "Unknown",
                "title": p.get("job_title"),
                "email": p.get("email"),
                "linkedin_url": p.get("linkedin_url"),
                "source": "hunter",
            }
            for p in people
        ]

        # Primary contact: first one with an email
        primary = next((p for p in people if p.get("email")), people[0])
        company_name = primary.get("company_name") or domain

        lead = Lead(
            company=company_name,
            industry="Unknown",
            contact_name=primary.get("name"),
            contact_role=primary.get("job_title"),
            contact_email=primary.get("email"),
            contacts_json=json.dumps(contacts_list),
            source="hunter",
            website=f"https://{domain}",
            status="new",
        )
        db.add(lead)
        added += 1

    db.commit()
    return PullLeadsResponse(new_leads_added=added)


@app.post("/api/leads/discover", response_model=DiscoverLeadsResponse)
def discover_leads(request: DiscoverLeadsRequest, db: Session = Depends(get_db)):
    """
    Discover potential leads using Google Custom Search Engine.

    - Searches for companies based on industry, keywords, and optional company name
    - De-duplicates against existing leads in database
    - Auto-scores each discovered lead
    - Returns ranked list with reasoning (does NOT save to database)

    Use POST /api/leads/upload or manual entry to save leads you want to pursue.

    Note: If Google CSE is unavailable (no API key/cx or libs missing), returns empty list with message.
    Use manual domain input with Hunter.io as fallback.
    """
    # Check if GoogleCSEService is available (libs installed)
    if GoogleCSEService is None:
        return DiscoverLeadsResponse(
            query_used="",
            total_found=0,
            new_leads=0,
            duplicates=0,
            leads=[],
            message="Google CSE disabled. Enable later to use discovery.",
        )

    # Check if Google CSE is configured BEFORE making any API calls
    if not settings.google_cse_api_key or not settings.google_cse_cx:
        logger.warning(
            "[discover_leads] Google CSE disabled: GOOGLE_CSE_API_KEY=%s, GOOGLE_CSE_CX=%s",
            "set" if settings.google_cse_api_key else "missing",
            "set" if settings.google_cse_cx else "missing",
        )
        return DiscoverLeadsResponse(
            query_used="",
            total_found=0,
            new_leads=0,
            duplicates=0,
            leads=[],
            message="Google CSE disabled (no API key/cx). Use manual domain input with Hunter.io.",
        )

    cse = GoogleCSEService()

    # Build query for display even if search fails
    query = cse._build_query(request.industry, request.keywords, request.company)

    # Handle unavailable search gracefully (e.g., 403 errors)
    try:
        raw_leads, message = cse.discover_leads(
            industry=request.industry,
            keywords=request.keywords,
            company=request.company,
        )
    except RuntimeError as e:
        # Unexpected error - return maintenance message
        logger.error("[discover_leads] Google CSE error: %s", e)
        raw_leads = []
        message = "Search temporarily unavailable. Use Hunter.io or manual upload."

    # If maintenance mode, return early with message
    if message:
        return DiscoverLeadsResponse(
            query_used=query,
            total_found=0,
            new_leads=0,
            duplicates=0,
            leads=[],
            message=message,
        )

    # Get existing companies and websites for deduplication
    existing_companies = {
        lead.company.lower() for lead in db.query(Lead.company).all() if lead.company
    }
    existing_websites = {
        lead.website.lower() for lead in db.query(Lead.website).all() if lead.website
    }

    # Process and score leads
    discovered_leads: List[DiscoveredLead] = []
    duplicates = 0

    for raw_lead in raw_leads:
        company_name = raw_lead.get("company", "")
        website = raw_lead.get("website", "")

        # Check for duplicates
        is_duplicate = (
            (company_name and company_name.lower() in existing_companies)
            or (website and website.lower() in existing_websites)
        )

        if is_duplicate:
            duplicates += 1

        # Create a temporary Lead object for scoring
        temp_lead = Lead(
            company=company_name,
            industry=request.industry,
            website=website,
            notes=raw_lead.get("description"),
        )
        score_result = score_lead(temp_lead)

        discovered_leads.append(
            DiscoveredLead(
                company=company_name,
                website=website,
                description=raw_lead.get("description"),
                industry=request.industry,
                source_url=raw_lead.get("source_url", ""),
                score=score_result["score"],
                score_reasons=score_result["reasons"],
                already_exists=is_duplicate,
            )
        )

    # Sort by score descending, non-duplicates first
    discovered_leads.sort(key=lambda x: (-int(not x.already_exists), -x.score))

    return DiscoverLeadsResponse(
        query_used=query,
        total_found=len(discovered_leads),
        new_leads=len(discovered_leads) - duplicates,
        duplicates=duplicates,
        leads=discovered_leads,
        message=None,
    )


# Company Discovery Endpoints (SerpAPI)

def compute_query_hash(
    source: str,
    industry: str,
    country: Optional[str],
    city: Optional[str],
    limit: int,
    query_text: str,
) -> str:
    payload = {
        "source": source,
        "industry": industry,
        "country": country,
        "city": city,
        "limit": limit,
        "query_text": query_text,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_results(db: Session, query_hash: str) -> Optional[List[dict]]:
    now = datetime.now(timezone.utc)
    cached = (
        db.query(CompanyDiscoveryCache)
        .filter(CompanyDiscoveryCache.query_hash == query_hash)
        .filter(CompanyDiscoveryCache.expires_at > now)
        .first()
    )
    if not cached:
        return None
    try:
        return json.loads(cached.results_json)
    except (TypeError, ValueError):
        return None


def set_cache_results(
    db: Session,
    query_hash: str,
    payload: List[dict],
    ttl_days: int,
    source: str,
    industry: str,
    country: Optional[str],
    city: Optional[str],
    query_text: str,
    limit: int,
) -> None:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=ttl_days)
    serialized = json.dumps(payload)
    cached = db.query(CompanyDiscoveryCache).filter(
        CompanyDiscoveryCache.query_hash == query_hash
    ).first()
    if cached:
        cached.results_json = serialized
        cached.created_at = now
        cached.expires_at = expires_at
        cached.source = source
        cached.industry = industry
        cached.country = country
        cached.city = city
        cached.query_text = query_text
        cached.limit = limit
    else:
        db.add(
            CompanyDiscoveryCache(
                query_hash=query_hash,
                source=source,
                industry=industry,
                country=country,
                city=city,
                query_text=query_text,
                limit=limit,
                results_json=serialized,
                expires_at=expires_at,
            )
        )
    db.commit()


@app.post("/api/companies/discover", response_model=CompanyDiscoverResponse)
def discover_companies(request: CompanyDiscoverRequest, db: Session = Depends(get_db)):
    """
    Discover companies by industry using SerpAPI.

    Credits are only used when revealing contact emails via /api/companies/{domain}/contacts.
    """
    if not settings.serpapi_api_key:
        return CompanyDiscoverResponse(companies=[], cached=False, message="SerpAPI not configured")

    if SerpAPIService is None:
        return CompanyDiscoverResponse(companies=[], cached=False, message="SerpAPI service not available")

    requested_limit = request.limit or 20
    max_allowed = 20 if settings.low_cost_mode else 50
    limit = max(1, min(int(requested_limit), max_allowed))
    source = request.source or "google_maps"
    query_text = " ".join(
        p for p in [request.industry, request.city, request.country] if p
    )
    query_hash = compute_query_hash(
        source=source,
        industry=request.industry,
        country=request.country,
        city=request.city,
        limit=limit,
        query_text=query_text,
    )

    cached_results = get_cached_results(db, query_hash)
    if cached_results is not None:
        companies = [DiscoveredCompany(**item) for item in cached_results]
        return CompanyDiscoverResponse(companies=companies, cached=True, message=None)

    serpapi = SerpAPIService()
    try:
        if source == "google_maps":
            results = serpapi.search_companies_maps(
                industry=request.industry,
                country=request.country,
                city=request.city,
                limit=limit,
            )
        else:
            results = serpapi.search_companies_google(
                industry=request.industry,
                country=request.country,
                city=request.city,
                limit=limit,
            )
    except Exception as exc:
        logger.error("SerpAPI discovery error: %s", exc)
        return CompanyDiscoverResponse(companies=[], cached=False, message=str(exc))

    if not results:
        message = "SerpAPI returned no results"
        return CompanyDiscoverResponse(companies=[], cached=False, message=message)

    ttl_hours = max(1, settings.cache_ttl_serpapi_hours)
    ttl_days = max(1, ttl_hours // 24)
    set_cache_results(
        db=db,
        query_hash=query_hash,
        payload=results,
        ttl_days=ttl_days,
        source=source,
        industry=request.industry,
        country=request.country,
        city=request.city,
        query_text=query_text,
        limit=limit,
    )

    companies = [DiscoveredCompany(**item) for item in results]
    return CompanyDiscoverResponse(companies=companies, cached=False, message=None)


@app.get("/api/companies/place/{place_id}")
def get_place_details(place_id: str, db: Session = Depends(get_db)):
    """
    Fetch Google Places details for a place_id.

    Cached for CACHE_TTL_PLACES_DAYS (default 30 days).
    Only called on user action (click / import) — never automatically.
    Returns 200 with message if Google Places API key is not configured.
    """
    if not settings.google_places_api_key:
        return {"place_id": place_id, "message": "Google Places not configured", "cached": False}

    now = datetime.utcnow()
    # Cache hit check
    cached = db.query(PlacesCache).filter(PlacesCache.place_id == place_id).first()
    if cached and cached.expires_at > now:
        try:
            return {**json.loads(cached.response_json), "cached": True}
        except Exception:
            pass  # Fall through to live call

    try:
        import requests as _requests
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,website,rating,types,opening_hours",
            "key": settings.google_places_api_key,
        }
        resp = _requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        payload = {
            "place_id": place_id,
            "name": result.get("name"),
            "address": result.get("formatted_address"),
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "rating": result.get("rating"),
            "categories": result.get("types", []),
            "hours": result.get("opening_hours", {}).get("weekday_text", []),
        }
    except Exception as exc:
        logger.error("Google Places fetch error for %s: %s", place_id, exc)
        return {"place_id": place_id, "message": f"Places API error: {exc}", "cached": False}

    # Upsert cache
    ttl_days = max(1, settings.cache_ttl_places_days)
    expires = now + timedelta(days=ttl_days)
    if cached:
        cached.response_json = json.dumps(payload)
        cached.expires_at = expires
    else:
        db.add(PlacesCache(place_id=place_id, response_json=json.dumps(payload), expires_at=expires))
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {**payload, "cached": False}


@app.post("/api/companies/{domain}/contacts", response_model=CompanyContactsResponse)
def get_company_contacts(domain: str, request: CompanyContactsRequest = None, db: Session = Depends(get_db)):
    """
    Get executive contacts for a company by domain.

    Cached for CACHE_TTL_HUNTER_DAYS (default 14 days).
    Returns 200 with message (never 500) when provider not configured.
    """
    source = request.source if request else "hunter"
    if source in ("google", "google_maps"):
        if HunterService is not None and settings.hunter_api_key:
            source = "hunter"
        elif SnovService is not None and settings.snov_client_id and settings.snov_client_secret:
            source = "snov"
        else:
            return CompanyContactsResponse(
                domain=domain,
                company_name=None,
                contacts=[],
                message="No contact provider configured",
            )

    contacts: List[ExecutiveContact] = []
    company_name = None
    messages = []
    now = datetime.utcnow()

    if source == "hunter":
        if HunterService is None or not settings.hunter_api_key:
            return CompanyContactsResponse(
                domain=domain, company_name=None, contacts=[],
                message="Hunter not configured",
            )

        # Cache check
        cached = db.query(HunterCache).filter(HunterCache.domain == domain).first()
        if cached and cached.expires_at > now:
            try:
                cached_data = json.loads(cached.response_json)
                contacts = [ExecutiveContact(**c) for c in cached_data.get("contacts", [])]
                return CompanyContactsResponse(
                    domain=domain,
                    company_name=cached_data.get("company_name"),
                    contacts=contacts,
                    message="cached",
                )
            except Exception:
                pass  # Fall through to live call

        try:
            hunter = HunterService()
            company_info = hunter.get_company_info(domain)
            if company_info:
                company_name = company_info.get("name")
            results = hunter.domain_search(domain)
            for person in results:
                contacts.append(ExecutiveContact(
                    name=person.get("name") or "Unknown",
                    title=person.get("job_title"),
                    email=person.get("email"),
                    linkedin_url=person.get("linkedin_url"),
                    source="hunter",
                ))
        except Exception as e:
            logger.error("Hunter domain search error: %s", e)
            return CompanyContactsResponse(
                domain=domain, company_name=None, contacts=[],
                message=f"Hunter error: {e}",
            )

        # Store in cache
        ttl_days = max(1, settings.cache_ttl_hunter_days)
        cache_payload = json.dumps({
            "company_name": company_name,
            "contacts": [c.model_dump() for c in contacts],
        })
        expires = now + timedelta(days=ttl_days)
        if cached:
            cached.response_json = cache_payload
            cached.expires_at = expires
        else:
            db.add(HunterCache(domain=domain, response_json=cache_payload, expires_at=expires))
        try:
            db.commit()
        except Exception:
            db.rollback()

    elif source == "snov":
        if SnovService is None or not settings.snov_client_id or not settings.snov_client_secret:
            return CompanyContactsResponse(
                domain=domain, company_name=None, contacts=[],
                message="Snov not configured",
            )
        try:
            snov = SnovService()
            company_profile = snov.get_company_profile(domain)
            if company_profile:
                company_name = company_profile.get("name")
            results = snov.get_emails_by_domain(domain)
            for person in results:
                contacts.append(ExecutiveContact(
                    name=person.get("name") or "Unknown",
                    title=person.get("title"),
                    email=person.get("email"),
                    linkedin_url=person.get("linkedin_url"),
                    source="snov",
                ))
        except Exception as e:
            logger.error("Snov.io domain search error: %s", e)
            return CompanyContactsResponse(
                domain=domain, company_name=None, contacts=[],
                message=f"Snov error: {e}",
            )
    else:
        return CompanyContactsResponse(
            domain=domain, company_name=None, contacts=[],
            message="Invalid source. Use 'hunter' or 'snov'",
        )

    return CompanyContactsResponse(
        domain=domain,
        company_name=company_name,
        contacts=contacts,
        message="; ".join(messages) if messages else None,
    )


@app.post("/api/leads/import", response_model=ImportCompaniesResponse)
def import_companies_as_leads(
    request: ImportCompaniesRequest, db: Session = Depends(get_db)
):
    """
    Import discovered companies as leads.

    Takes a list of companies (with optional contact info) and creates Lead records.
    Deduplicates against existing leads by company name or domain/website.
    Auto-scores each imported lead.
    """
    imported = 0
    skipped = 0
    leads_created: List[LeadRead] = []

    # Get existing companies and websites for deduplication
    existing_companies = {
        lead.company.lower() for lead in db.query(Lead.company).all() if lead.company
    }
    existing_websites = {
        lead.website.lower() for lead in db.query(Lead.website).all() if lead.website
    }

    for company in request.companies:
        # Check for duplicates
        company_lower = company.name.lower() if company.name else ""
        domain_lower = company.domain.lower() if company.domain else ""

        if company_lower in existing_companies:
            skipped += 1
            continue
        if domain_lower and domain_lower in existing_websites:
            skipped += 1
            continue

        # Parse employee count from size string
        employees = None
        if company.size:
            employees = parse_employees(company.size)

        # Build contacts_json from full contacts list (preserves all contacts, not just first)
        contacts_to_store = []
        if company.contacts:
            for c in company.contacts:
                contacts_to_store.append({
                    "name": c.get("name", "Unknown"),
                    "title": c.get("title"),
                    "email": c.get("email"),
                    "linkedin_url": c.get("linkedin_url"),
                    "source": c.get("source", company.source),
                })
        elif company.contact_name or company.contact_email:
            contacts_to_store.append({
                "name": company.contact_name or "Unknown",
                "title": company.contact_role,
                "email": company.contact_email,
                "linkedin_url": None,
                "source": company.source,
            })

        # Primary contact from first in contacts list
        primary_name = company.contact_name
        primary_role = company.contact_role
        primary_email = company.contact_email
        if contacts_to_store and not primary_email:
            first = contacts_to_store[0]
            primary_name = primary_name or first.get("name")
            primary_role = primary_role or first.get("title")
            primary_email = primary_email or first.get("email")

        # Create lead
        # notes = internal operator notes (CSV flagging signals — source of truth for scoring)
        # company_description = external description from discovery source (SerpAPI/Google Maps)
        lead = Lead(
            company=company.name,
            industry=company.industry,
            location=company.location,
            employees=employees,
            website=company.website_url or company.domain,
            notes=None,
            company_description=company.description,
            contact_name=primary_name,
            contact_role=primary_role,
            contact_email=primary_email,
            phone=company.phone,
            contacts_json=json.dumps(contacts_to_store) if contacts_to_store else None,
            source=company.source,
            status="new",
        )
        db.add(lead)
        db.flush()  # Get the ID

        # Score the lead
        score_result = score_lead(lead)
        lead.score = score_result["score"]
        lead.score_reason = "; ".join(score_result["reasons"])
        if score_result["score"] >= 70:
            lead.status = "qualified"

        # Add to existing sets for subsequent deduplication
        existing_companies.add(company_lower)
        if domain_lower:
            existing_websites.add(domain_lower)

        imported += 1
        leads_created.append(LeadRead.model_validate(lead))

    db.commit()

    return ImportCompaniesResponse(
        imported=imported,
        skipped=skipped,
        leads=leads_created,
    )


@app.get("/api/leads/approved", response_model=List[LeadRead])
def get_approved_leads(db: Session = Depends(get_db)):
    """Return all leads with status 'approved'."""
    leads = (
        db.query(Lead)
        .filter(Lead.status == "approved")
        .order_by(Lead.created_at.desc())
        .all()
    )
    return leads


@app.get("/api/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """Get a single lead by ID."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.get("/api/leads/{lead_id}/profile", response_model=LeadProfile)
def get_lead_profile(lead_id: int, db: Session = Depends(get_db)):
    """
    Get a lead's company profile, including all stored contacts.

    Returns: name, website, phone, location, description, linkedin_url, contacts[]
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Parse contacts from JSON
    contacts: list = []
    if lead.contacts_json:
        try:
            raw = json.loads(lead.contacts_json)
            for c in raw:
                contacts.append(ProfileContact(
                    name=c.get("name", "Unknown"),
                    title=c.get("title"),
                    email=c.get("email"),
                    linkedin_url=c.get("linkedin_url"),
                    source=c.get("source"),
                ))
        except (TypeError, ValueError):
            pass
    # Fallback: include single contact_email/contact_name if no contacts_json
    if not contacts and (lead.contact_name or lead.contact_email):
        contacts.append(ProfileContact(
            name=lead.contact_name or "Unknown",
            title=lead.contact_role,
            email=lead.contact_email,
            linkedin_url=None,
            source=lead.source,
        ))

    score_result = score_lead(lead)
    quality_label = get_quality_label(score_result["score"], has_negative_signal(lead.notes))

    return LeadProfile(
        id=lead.id,
        company=lead.company,
        website=lead.website,
        phone=lead.phone,
        location=lead.location,
        description=_resolve_description(lead, db),
        linkedin_url=lead.linkedin_url,
        contacts=contacts,
        status=lead.status,
        source=lead.source,
        industry=lead.industry,
        employees=lead.employees,
        stage=lead.stage,
        contact_name=lead.contact_name,
        contact_email=lead.contact_email,
        score=score_result["score"],
        score_reasons=score_result["reasons"],
        quality_label=quality_label,
    )


@app.patch("/api/leads/{lead_id}/contact_email", response_model=ContactEmailResponse)
def update_contact_email(
    lead_id: int, request: ContactEmailUpdate, db: Session = Depends(get_db)
):
    """Update a lead's contact email."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if "@" not in request.contact_email:
        raise HTTPException(status_code=400, detail="Invalid email: must contain @")

    lead.contact_email = request.contact_email
    db.commit()

    return ContactEmailResponse(lead_id=lead.id, contact_email=lead.contact_email)


@app.patch("/api/leads/{lead_id}/status", response_model=LeadStatusResponse)
def update_lead_status(
    lead_id: int, request: LeadStatusUpdate, db: Session = Depends(get_db)
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = request.status
    db.commit()

    return LeadStatusResponse(lead_id=lead.id, status=lead.status)


@app.get("/api/status", response_model=StatusResponse)
def get_status(db: Session = Depends(get_db)):
    total = db.query(Lead).count()

    status_counts = (
        db.query(Lead.status, sql_func.count(Lead.id))
        .group_by(Lead.status)
        .all()
    )

    by_status = [StatusCount(status=s, count=c) for s, c in status_counts]

    return StatusResponse(total=total, by_status=by_status)


@app.post("/api/leads/{lead_id}/draft", response_model=DraftResponse)
def draft_lead_email(lead_id: int, db: Session = Depends(get_db)):
    """
    Generate an outreach email draft for a lead.

    - Generates subject and body using the outbound agent
    - Saves them to email_subject, email_body
    - Updates status to 'drafted'
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Generate the draft
    draft = draft_outreach_email(lead)

    # Update the lead
    lead.email_subject = draft["subject"]
    lead.email_body = draft["body"]
    lead.status = "drafted"

    db.commit()
    db.refresh(lead)

    return DraftResponse(
        lead_id=lead.id,
        subject=lead.email_subject,
        body=lead.email_body,
        status=lead.status,
    )


@app.get("/api/leads/drafted", response_model=List[LeadRead])
def get_drafted_leads(db: Session = Depends(get_db)):
    """
    Return all leads with status 'drafted'.
    """
    leads = (
        db.query(Lead)
        .filter(Lead.status == "drafted")
        .order_by(Lead.created_at.desc())
        .all()
    )
    return leads


@app.post("/api/leads/{lead_id}/score", response_model=ScoreResponse)
def score_lead_endpoint(lead_id: int, db: Session = Depends(get_db)):
    """
    Score a lead based on transparent, additive criteria.

    - Scores the lead using the scoring agent
    - Saves score and reasons to the lead
    - Sets status to 'qualified' if score >= 70
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Score the lead
    result = score_lead(lead)

    # Update the lead
    lead.score = result["score"]
    lead.score_reason = "; ".join(result["reasons"])

    # Set status to qualified if score >= 70
    if result["score"] >= 70:
        lead.status = "qualified"

    db.commit()
    db.refresh(lead)

    return ScoreResponse(
        lead_id=lead.id,
        score=lead.score,
        reasons=result["reasons"],
        status=lead.status,
    )


@app.get("/api/leads/qualified", response_model=List[LeadRead])
def get_qualified_leads(db: Session = Depends(get_db)):
    """
    Return all leads with status 'qualified'.
    """
    leads = (
        db.query(Lead)
        .filter(Lead.status == "qualified")
        .order_by(Lead.score.desc())
        .all()
    )
    return leads


@app.post("/api/leads/{lead_id}/approve", response_model=GmailSendResponse)
def approve_lead(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Approve a drafted lead — sends the saved draft via Gmail and marks as 'sent'.

    Requires the lead to have email_subject, email_body, and contact_email saved
    (set via the save_draft endpoint from the Inbox page).
    """
    user_key = get_user_key(request)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.email_subject or not lead.email_body or not lead.contact_email:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="No saved draft found. Open this lead in Inbox to compose and save a draft first.",
        )

    if not _is_gmail_connected(db, user_key):
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="Gmail not connected. Connect in Settings first.",
        )

    if settings.demo_mode:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="Demo mode: sending disabled.",
        )

    daily_count = get_daily_email_count(db)
    if daily_count >= DAILY_SEND_LIMIT:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error=f"Daily send limit ({DAILY_SEND_LIMIT}) reached.",
        )

    result = _send_email_for_user(
        db, user_key,
        to=lead.contact_email,
        subject=lead.email_subject,
        body=lead.email_body,
    )

    if result["success"]:
        lead.status = "sent"
        sent_email = SentEmail(
            lead_id=lead.id,
            to_email=lead.contact_email,
            subject=lead.email_subject,
            body=lead.email_body,
            gmail_message_id=result.get("message_id"),
            sent_date=date.today(),
        )
        db.add(sent_email)
        increment_daily_email_count(db)
        db.commit()

    return GmailSendResponse(
        success=result["success"],
        lead_id=lead_id,
        message_id=result.get("message_id"),
        error=result.get("error"),
    )


@app.post("/api/leads/{lead_id}/unapprove", response_model=ApprovalResponse)
def unapprove_lead(lead_id: int, db: Session = Depends(get_db)):
    """Set lead status back to 'drafted'."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = "drafted"
    db.commit()

    return ApprovalResponse(lead_id=lead.id, status=lead.status)


@app.post("/api/leads/{lead_id}/qualify", response_model=ApprovalResponse)
def qualify_lead(lead_id: int, db: Session = Depends(get_db)):
    """
    Mark a lead as qualified.

    Re-scores using the Adina Playbook before qualifying, weighting the Notes
    column from CSV import as the primary signal source.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Re-score: notes act as weighted source of truth before any online enrichment
    score_result = score_lead(lead)
    lead.score = score_result["score"]
    lead.score_reason = "; ".join(score_result["reasons"])
    lead.status = "qualified"
    db.commit()

    return ApprovalResponse(lead_id=lead.id, status=lead.status)


@app.post("/api/leads/{lead_id}/save_draft")
def save_lead_draft(lead_id: int, request: SaveDraftRequest, db: Session = Depends(get_db)):
    """
    Save a composed email draft to the lead without sending.

    - Saves subject, body, and recipient email to the lead record
    - Sets lead status to 'drafted'
    - Called from the Inbox page when user clicks 'Save Draft'
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.email_subject = request.subject
    lead.email_body = request.body
    lead.contact_email = request.to_email
    lead.status = "drafted"
    db.commit()

    return {"lead_id": lead_id, "status": "drafted"}


@app.get("/api/leads/{lead_id}/sent_email", response_model=SentEmailRead)
def get_lead_sent_email(lead_id: int, db: Session = Depends(get_db)):
    """Return the most recent sent email for a lead."""
    sent = (
        db.query(SentEmail)
        .filter(SentEmail.lead_id == lead_id)
        .order_by(SentEmail.sent_at.desc())
        .first()
    )
    if not sent:
        raise HTTPException(status_code=404, detail="No sent email found for this lead")
    return sent


@app.post("/api/leads/{lead_id}/fetch_contacts", response_model=LeadProfile)
def fetch_lead_contacts(lead_id: int, db: Session = Depends(get_db)):
    """
    Fetch and save contacts for a lead using Hunter.io.

    - Extracts domain from lead's website field
    - Calls Hunter.io to find all contacts at that domain
    - Saves results to contacts_json on the lead
    - Sets primary contact fields if not already set
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.website:
        raise HTTPException(status_code=400, detail="Lead has no website — cannot look up contacts")

    if HunterService is None or not settings.hunter_api_key:
        raise HTTPException(status_code=503, detail="Hunter.io not configured")

    # Extract clean domain from website URL
    domain = lead.website
    for prefix in ("https://", "http://", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/")[0].strip()

    if not domain:
        raise HTTPException(status_code=400, detail="Could not extract domain from lead website")

    now = datetime.utcnow()
    results = None

    # Check hunter cache first
    cached_hunter = db.query(HunterCache).filter(HunterCache.domain == domain).first()
    if cached_hunter and cached_hunter.expires_at > now:
        try:
            cached_data = json.loads(cached_hunter.response_json)
            results = [
                {
                    "name": c.get("name") or "Unknown",
                    "job_title": c.get("title"),
                    "email": c.get("email"),
                    "linkedin_url": c.get("linkedin_url"),
                }
                for c in cached_data.get("contacts", [])
            ]
            logger.info("Hunter cache hit for domain %s (lead %d)", domain, lead_id)
        except Exception:
            results = None

    if results is None:
        try:
            hunter = HunterService()
            results = hunter.domain_search(domain)
        except Exception as e:
            logger.error("Hunter fetch_contacts error for lead %d: %s", lead_id, e)
            raise HTTPException(status_code=502, detail=f"Hunter.io error: {str(e)}")

        # Store in cache
        if results is not None:
            ttl_days = max(1, settings.cache_ttl_hunter_days)
            cache_payload = json.dumps({
                "company_name": lead.company,
                "contacts": [
                    {
                        "name": p.get("name") or "Unknown",
                        "title": p.get("job_title"),
                        "email": p.get("email"),
                        "linkedin_url": p.get("linkedin_url"),
                        "source": "hunter",
                    }
                    for p in results
                ],
            })
            expires = now + timedelta(days=ttl_days)
            if cached_hunter:
                cached_hunter.response_json = cache_payload
                cached_hunter.expires_at = expires
            else:
                db.add(HunterCache(domain=domain, response_json=cache_payload, expires_at=expires))
            try:
                db.commit()
            except Exception:
                db.rollback()

    if results:
        contacts_list = [
            {
                "name": p.get("name") or "Unknown",
                "title": p.get("job_title"),
                "email": p.get("email"),
                "linkedin_url": p.get("linkedin_url"),
                "source": "hunter",
            }
            for p in results
        ]
        lead.contacts_json = json.dumps(contacts_list)

        # Set primary contact fields if not already populated
        primary = next((c for c in contacts_list if c.get("email")), contacts_list[0])
        if not lead.contact_name:
            lead.contact_name = primary.get("name")
        if not lead.contact_email:
            lead.contact_email = primary.get("email")
        if not lead.contact_role:
            lead.contact_role = primary.get("title")

        db.commit()
        db.refresh(lead)

    # Build and return the updated profile
    contacts: list = []
    if lead.contacts_json:
        try:
            raw = json.loads(lead.contacts_json)
            for c in raw:
                contacts.append(ProfileContact(
                    name=c.get("name", "Unknown"),
                    title=c.get("title"),
                    email=c.get("email"),
                    linkedin_url=c.get("linkedin_url"),
                    source=c.get("source"),
                ))
        except (TypeError, ValueError):
            pass
    if not contacts and (lead.contact_name or lead.contact_email):
        contacts.append(ProfileContact(
            name=lead.contact_name or "Unknown",
            title=lead.contact_role,
            email=lead.contact_email,
            linkedin_url=None,
            source=lead.source,
        ))

    score_result = score_lead(lead)
    quality_label = get_quality_label(score_result["score"], has_negative_signal(lead.notes))

    return LeadProfile(
        id=lead.id,
        company=lead.company,
        website=lead.website,
        phone=lead.phone,
        location=lead.location,
        description=_resolve_description(lead, db),
        linkedin_url=lead.linkedin_url,
        contacts=contacts,
        status=lead.status,
        source=lead.source,
        industry=lead.industry,
        employees=lead.employees,
        stage=lead.stage,
        contact_name=lead.contact_name,
        contact_email=lead.contact_email,
        score=score_result["score"],
        score_reasons=score_result["reasons"],
        quality_label=quality_label,
    )


@app.post("/api/replies/draft", response_model=ReplyDraftResponse)
def draft_reply(request: ReplyDraftRequest, db: Session = Depends(get_db)):
    """
    Classify an inbound email reply and draft a follow-up.

    - Classifies the inbound text by intent (positive, neutral, objection, deferral, negative)
    - Drafts an appropriate follow-up based on the intent and lead context
    - Does NOT send any emails
    """
    lead = db.query(Lead).filter(Lead.id == request.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Classify the inbound reply
    intent_label = classify_reply(request.inbound_text)

    # Draft the follow-up
    result = draft_followup_with_context(intent_label, lead, request.inbound_text)

    return ReplyDraftResponse(
        lead_id=lead.id,
        intent_label=result["intent"],
        drafted_reply=result["body"],
    )


# Gmail Integration Endpoints

DAILY_SEND_LIMIT = 100


def get_daily_email_count(db: Session) -> int:
    """Get the number of emails sent today."""
    today = date.today()
    count_record = db.query(DailyEmailCount).filter(DailyEmailCount.date == today).first()
    return count_record.count if count_record else 0


def increment_daily_email_count(db: Session) -> None:
    """Increment the daily email count."""
    today = date.today()
    count_record = db.query(DailyEmailCount).filter(DailyEmailCount.date == today).first()
    if count_record:
        count_record.count += 1
    else:
        count_record = DailyEmailCount(date=today, count=1)
        db.add(count_record)


@app.post("/api/gmail/connect", response_model=GmailConnectResponse)
def connect_gmail(request: GmailConnectRequest = None):
    """
    Connect to Gmail via OAuth.

    - If no code provided: Returns auth_url for user to authorize
    - If code provided: Completes OAuth flow and saves token

    For local development, you can also call with no body to trigger
    the local server OAuth flow (opens browser).
    """
    if gmail is None:
        raise HTTPException(status_code=503, detail="Gmail service not available - Google libraries not installed")

    # Check if already connected
    status = gmail.get_connection_status()
    if status["connected"]:
        return GmailConnectResponse(
            connected=True,
            email=status["email"],
            message="Gmail already connected",
        )

    # If code provided, complete OAuth flow
    if request and request.code:
        result = gmail.complete_oauth_with_code(request.code, request.state)
        if result["success"]:
            status = gmail.get_connection_status()
            return GmailConnectResponse(
                connected=True,
                email=status.get("email"),
                message=result["message"],
            )
        else:
            return GmailConnectResponse(
                connected=False,
                error=result["error"],
            )

    # Start OAuth flow - return auth URL
    try:
        flow_result = gmail.start_oauth_flow()
        return GmailConnectResponse(
            connected=False,
            auth_url=flow_result["auth_url"],
            message="Please visit auth_url to authorize Gmail access",
        )
    except FileNotFoundError as e:
        return GmailConnectResponse(
            connected=False,
            error=str(e),
        )


@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(code: str = Query(...), state: str = Query(None)):
    """
    OAuth callback endpoint for Gmail authorization.

    Google redirects here after user authorizes. This endpoint:
    1. Exchanges the authorization code for tokens
    2. Saves the tokens
    3. Returns a success page to the user
    """
    if gmail is None:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>Gmail Not Available</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Gmail Service Not Available</h1>
                <p>Google libraries are not installed.</p>
            </body>
            </html>
            """,
            status_code=503,
        )

    result = gmail.complete_oauth_with_code(code, state)

    if result["success"]:
        status = gmail.get_connection_status()
        email = status.get("email", "your account")
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Gmail Connected</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Gmail Connected Successfully!</h1>
                <p>Connected as: <strong>{email}</strong></p>
                <p>You can close this window and return to the application.</p>
            </body>
            </html>
            """,
            status_code=200,
        )
    else:
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Gmail Connection Failed</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Gmail Connection Failed</h1>
                <p>Error: {result.get('error', 'Unknown error')}</p>
                <p>Please try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )


@app.get("/api/gmail/status", response_model=GmailConnectResponse)
def get_gmail_status(request: Request, db: Session = Depends(get_db)):
    """Get current Gmail connection status (DB-backed per-user, falls back to file)."""
    user_key = get_user_key(request)
    status = _gmail_status_for_user(db, user_key)
    return GmailConnectResponse(
        connected=status["connected"],
        email=status.get("email"),
        error=status.get("error"),
    )


@app.get("/api/gmail/auth/start")
def gmail_auth_start(request: Request):
    """
    Start Gmail OAuth — returns {url} for the Google consent screen.

    Uses DB-backed token storage (GOOGLE_CLIENT_ID/SECRET required).
    """
    user_key = get_user_key(request)
    if gmail_service is None:
        return {"error": "gmail_service module not available"}
    url = gmail_service.build_auth_url(user_key)
    if not url:
        return {"error": "Google OAuth credentials not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI)"}
    return {"url": url}


@app.get("/api/gmail/auth/callback", response_class=HTMLResponse)
def gmail_auth_callback(
    code: str = Query(...),
    state: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    Google OAuth callback — exchanges code, stores encrypted tokens, returns HTML.

    Google redirects here after user authorises. The `state` param carries user_key.
    """
    user_key = state or "local_user"
    if gmail_service is None:
        return HTMLResponse("<h1>gmail_service not available</h1>", status_code=503)

    email_address = gmail_service.exchange_code(db, code, user_key)
    if email_address:
        return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>Gmail Connected</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px">
  <h1>Gmail Connected!</h1>
  <p>Connected as <strong>{email_address}</strong></p>
  <p>You can close this window and return to ADINA.</p>
</body></html>""")
    return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Gmail Connection Failed</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px">
  <h1>Gmail Connection Failed</h1>
  <p>Could not exchange code for tokens. Please try again.</p>
</body></html>""", status_code=400)


@app.post("/api/gmail/disconnect")
def gmail_disconnect(request: Request, db: Session = Depends(get_db)):
    """
    Disconnect Gmail for the current user_key.

    Removes DB tokens only for this user — other users are unaffected.
    Also clears file-based token for backward compatibility.
    """
    user_key = get_user_key(request)
    db_removed = False
    if gmail_service is not None:
        db_removed = gmail_service.disconnect(db, user_key)
    # Also clear file-based token for backward compat
    if gmail is not None:
        try:
            gmail.disconnect()
        except Exception:
            pass
    return {"success": True, "user_key": user_key, "db_token_removed": db_removed}


@app.post("/api/gmail/send/{lead_id}", response_model=GmailSendResponse)
def send_email_to_lead(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Send the drafted email to a lead via Gmail.

    Email always sent FROM the account authenticated under x-user-key (default: local_user).
    """
    user_key = get_user_key(request)

    if settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode: sending disabled")

    if not _is_gmail_connected(db, user_key):
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="Gmail not connected. Please connect via /api/gmail/auth/start first.",
        )

    daily_count = get_daily_email_count(db)
    if daily_count >= DAILY_SEND_LIMIT:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error=f"Daily send limit ({DAILY_SEND_LIMIT}) reached. Try again tomorrow.",
        )

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.status != "approved":
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error=f"Lead status must be 'approved' to send. Current status: '{lead.status}'",
        )

    if not lead.contact_email:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="Lead has no contact_email",
        )

    if not lead.email_subject or not lead.email_body:
        return GmailSendResponse(
            success=False, lead_id=lead_id,
            error="Lead has no drafted email. Generate a draft first.",
        )

    result = _send_email_for_user(
        db, user_key,
        to=lead.contact_email,
        subject=lead.email_subject,
        body=lead.email_body,
    )

    if result["success"]:
        # Log the sent email
        sent_email = SentEmail(
            lead_id=lead.id,
            to_email=lead.contact_email,
            subject=lead.email_subject,
            body=lead.email_body,
            gmail_message_id=result["message_id"],
            sent_date=date.today(),
        )
        db.add(sent_email)

        # Update daily count
        increment_daily_email_count(db)

        # Update lead status
        lead.status = "sent"

        db.commit()

        return GmailSendResponse(
            success=True,
            lead_id=lead_id,
            message_id=result["message_id"],
        )
    else:
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error=result["error"],
        )


@app.post("/api/gmail/send_batch", response_model=BatchSendResponse)
def send_batch_emails(request: BatchSendRequest, db: Session = Depends(get_db)):
    """
    Send emails to multiple approved leads.

    - Only sends to leads with status == 'approved'
    - Enforces daily 100 email cap
    - Default limit: 25, max: 100
    - Returns summary of attempted, sent, skipped, and errors
    """
    if gmail is None:
        return BatchSendResponse(
            attempted=0,
            sent=0,
            skipped=0,
            errors=[BatchSendError(lead_id=0, error="Gmail service not available - Google libraries not installed")],
        )

    if settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode: sending disabled")

    # Check Gmail connection
    if not gmail.is_connected():
        return BatchSendResponse(
            attempted=0,
            sent=0,
            skipped=0,
            errors=[BatchSendError(lead_id=0, error="Gmail not connected")],
        )

    # Enforce limit bounds
    limit = min(request.limit or 25, 100)

    # Check daily quota
    daily_count = get_daily_email_count(db)
    remaining_quota = max(0, DAILY_SEND_LIMIT - daily_count)

    if remaining_quota == 0:
        return BatchSendResponse(
            attempted=0,
            sent=0,
            skipped=0,
            errors=[BatchSendError(lead_id=0, error="Daily send limit reached")],
        )

    # Adjust limit to remaining quota
    limit = min(limit, remaining_quota)

    # Get leads to send
    if request.lead_ids:
        # Send to specific leads (must be approved)
        leads = (
            db.query(Lead)
            .filter(Lead.id.in_(request.lead_ids), Lead.status == "approved")
            .limit(limit)
            .all()
        )
    else:
        # Send to all approved leads up to limit
        leads = (
            db.query(Lead)
            .filter(Lead.status == "approved")
            .order_by(Lead.created_at.asc())
            .limit(limit)
            .all()
        )

    attempted = 0
    sent = 0
    skipped = 0
    errors: List[BatchSendError] = []

    for lead in leads:
        attempted += 1

        # Validate lead has required fields
        if not lead.contact_email:
            skipped += 1
            errors.append(BatchSendError(lead_id=lead.id, error="No contact_email"))
            continue

        if not lead.email_subject or not lead.email_body:
            skipped += 1
            errors.append(BatchSendError(lead_id=lead.id, error="No drafted email"))
            continue

        # Send the email
        result = gmail.send_email(
            to=lead.contact_email,
            subject=lead.email_subject,
            body=lead.email_body,
        )

        if result["success"]:
            # Log the sent email
            sent_email = SentEmail(
                lead_id=lead.id,
                to_email=lead.contact_email,
                subject=lead.email_subject,
                body=lead.email_body,
                gmail_message_id=result["message_id"],
                sent_date=date.today(),
            )
            db.add(sent_email)

            # Update daily count
            increment_daily_email_count(db)

            # Update lead status
            lead.status = "sent"

            sent += 1
        else:
            errors.append(BatchSendError(lead_id=lead.id, error=result["error"] or "Unknown error"))

    db.commit()

    return BatchSendResponse(
        attempted=attempted,
        sent=sent,
        skipped=skipped,
        errors=errors,
    )


@app.post("/api/gmail/send_reply", response_model=GmailSendResponse)
def send_reply_email(send_request: SendReplyRequest, request: Request, db: Session = Depends(get_db)):
    """
    Send a drafted reply email via Gmail OAuth.

    Used by the Inbox page to send a classified/drafted reply to a specific recipient.
    Does not require the lead to be in 'approved' status.
    Email is sent FROM the authenticated Gmail account of the current user (x-user-key).
    """
    user_key = get_user_key(request)

    if settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode: sending disabled")

    if not _is_gmail_connected(db, user_key):
        return GmailSendResponse(
            success=False, lead_id=send_request.lead_id,
            error="Gmail not connected. Connect in Settings first.",
        )

    daily_count = get_daily_email_count(db)
    if daily_count >= DAILY_SEND_LIMIT:
        return GmailSendResponse(
            success=False, lead_id=send_request.lead_id,
            error=f"Daily send limit ({DAILY_SEND_LIMIT}) reached.",
        )

    lead = db.query(Lead).filter(Lead.id == send_request.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    result = _send_email_for_user(
        db, user_key,
        to=send_request.to_email,
        subject=send_request.subject,
        body=send_request.body,
    )

    if result["success"]:
        lead.status = "sent"
        lead.contact_email = send_request.to_email
        sent_email = SentEmail(
            lead_id=lead.id,
            to_email=send_request.to_email,
            subject=send_request.subject,
            body=send_request.body,
            gmail_message_id=result["message_id"],
            sent_date=date.today(),
        )
        db.add(sent_email)
        increment_daily_email_count(db)
        db.commit()

        return GmailSendResponse(
            success=True, lead_id=send_request.lead_id,
            message_id=result["message_id"],
        )
    else:
        return GmailSendResponse(
            success=False, lead_id=send_request.lead_id,
            error=result["error"],
        )


@app.get("/api/gmail/sent", response_model=List[SentEmailRead])
def get_sent_emails(db: Session = Depends(get_db)):
    """
    Get all sent emails, ordered by most recent first.
    """
    emails = db.query(SentEmail).order_by(SentEmail.sent_at.desc()).limit(200).all()
    return emails


@app.get("/api/gmail/sent/today", response_model=dict)
def get_today_send_count(db: Session = Depends(get_db)):
    """
    Get today's send count and remaining quota.
    """
    count = get_daily_email_count(db)
    return {
        "date": str(date.today()),
        "sent": count,
        "limit": DAILY_SEND_LIMIT,
        "remaining": max(0, DAILY_SEND_LIMIT - count),
    }


@app.get("/api/sent", response_model=List[SentEmailRead])
def get_sent_logs(db: Session = Depends(get_db)):
    """Get recent sent email logs, newest first."""
    emails = db.query(SentEmail).order_by(SentEmail.sent_at.desc()).limit(200).all()
    return emails


# Workflow Endpoints

@app.post("/api/workflow/approve_and_send/{lead_id}", response_model=WorkflowSendResponse)
def approve_and_send_lead(
    lead_id: int, dry_run: bool = Query(False), db: Session = Depends(get_db)
):
    """
    Combined workflow: draft (if needed), approve, and send a lead email.

    If dry_run=true: generates draft if missing, does NOT require contact_email,
    does NOT check Gmail, does NOT send, does NOT change status.
    Returns {lead_id, status="dry_run", subject, body}.

    If dry_run=false (default): full workflow with all validations.
    """
    if not dry_run:
        if gmail is None:
            return WorkflowSendResponse(
                lead_id=lead_id,
                status="error",
                error="Gmail service not available - Google libraries not installed",
            )

        # Block real sends in demo mode
        if settings.demo_mode:
            raise HTTPException(status_code=403, detail="Demo mode: sending disabled")

        # 1. Check Gmail connection
        if not gmail.is_connected():
            return WorkflowSendResponse(
                lead_id=lead_id,
                status="error",
                error="Gmail not connected. Please connect via /api/gmail/connect first.",
            )

        # 2. Check daily limit
        daily_count = get_daily_email_count(db)
        if daily_count >= DAILY_SEND_LIMIT:
            return WorkflowSendResponse(
                lead_id=lead_id,
                status="error",
                error=f"Daily send limit ({DAILY_SEND_LIMIT}) reached. Try again tomorrow.",
            )

    # 3. Get lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # 4. Check contact email (not required for dry_run)
    if not dry_run and not lead.contact_email:
        return WorkflowSendResponse(
            lead_id=lead_id,
            status="error",
            error="Lead has no contact_email. Cannot send without a recipient.",
        )

    # 5. Generate draft if not present
    if not lead.email_subject or not lead.email_body:
        draft = draft_outreach_email(lead)
        lead.email_subject = draft["subject"]
        lead.email_body = draft["body"]
        db.commit()

    # Dry run: return draft without changing status or sending
    if dry_run:
        return WorkflowSendResponse(
            lead_id=lead_id,
            status="dry_run",
            subject=lead.email_subject,
            body=lead.email_body,
        )

    # 6. Set status to approved
    lead.status = "approved"
    db.commit()

    # 7. Send email via Gmail
    result = gmail.send_email(
        to=lead.contact_email,
        subject=lead.email_subject,
        body=lead.email_body,
    )

    if result["success"]:
        # 8. Log the sent email and update status
        sent_email = SentEmail(
            lead_id=lead.id,
            to_email=lead.contact_email,
            subject=lead.email_subject,
            body=lead.email_body,
            gmail_message_id=result["message_id"],
            sent_date=date.today(),
        )
        db.add(sent_email)

        increment_daily_email_count(db)

        lead.status = "sent"
        db.commit()

        return WorkflowSendResponse(
            lead_id=lead_id,
            status="sent",
            message_id=result["message_id"],
        )
    else:
        # Email send failed - keep status as approved for retry
        return WorkflowSendResponse(
            lead_id=lead_id,
            status="approved",
            error=result["error"],
        )
