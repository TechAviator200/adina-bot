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
import io
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, text

from app.settings import settings
from app.db import Base, engine, get_db
from app.models import Lead, SentEmail, DailyEmailCount
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
)
from app.agent.outbound import draft_outreach_email
from app.agent.scoring import score_lead
from app.agent.responses import classify_reply, draft_followup_with_context
from app import gmail
from app.utils.response_playbook import RESPONSE_PLAYBOOK
from services.hunter_service import HunterService

# Google CSE is optional - app must not crash if google libs are missing
try:
    from services.google_cse_service import GoogleCSEService
except ImportError:
    GoogleCSEService = None  # type: ignore

logger = logging.getLogger(__name__)

if GoogleCSEService is None:
    logger.warning(
        "GoogleCSEService not available (missing google libs). "
        "/api/leads/discover will be disabled."
    )

# Create database tables (with error handling for production)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
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
    
    # Try to create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error("Failed to create database tables: %s", e)
        logger.warning("Application will continue, but database operations may fail")
    
    logger.info("Adina Bot API startup complete")

# CORS middleware for frontend
_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
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


@app.get("/api/config")
def get_config():
    return {
        "demo_mode": settings.demo_mode,
        "oauth_redirect_uri": settings.oauth_redirect_uri,
    }


_KNOWLEDGE_PACK_PATH = Path(__file__).parent / "knowledge_pack.json"


@app.get("/api/templates")
def get_templates():
    """Return outreach response templates from the playbook."""
    templates = RESPONSE_PLAYBOOK.get("followup_templates", {})
    result = []
    for intent, config in templates.items():
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

        for person in people:
            # Deduplicate by email if available, otherwise by name + company
            if person.get("email"):
                exists = db.query(Lead).filter(Lead.contact_email == person["email"]).first()
            else:
                exists = db.query(Lead).filter(
                    Lead.contact_name == person.get("name"),
                    Lead.company == (person.get("company_name") or "Unknown"),
                ).first()

            if exists:
                continue

            lead = Lead(
                company=person.get("company_name") or "Unknown",
                industry="Unknown",
                contact_name=person.get("name"),
                contact_role=person.get("job_title"),
                contact_email=person.get("email"),
                source="hunter",
                source_url=person.get("linkedin_url"),
                website=person.get("domain"),
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
            message="Google CSE disabled. Use Hunter.io or manual CSV upload.",
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


@app.post("/api/leads/{lead_id}/approve", response_model=ApprovalResponse)
def approve_lead(lead_id: int, db: Session = Depends(get_db)):
    """Set lead status to 'approved'."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = "approved"
    db.commit()

    return ApprovalResponse(lead_id=lead.id, status=lead.status)


@app.post("/api/leads/{lead_id}/unapprove", response_model=ApprovalResponse)
def unapprove_lead(lead_id: int, db: Session = Depends(get_db)):
    """Set lead status back to 'drafted'."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = "drafted"
    db.commit()

    return ApprovalResponse(lead_id=lead.id, status=lead.status)


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
def get_gmail_status():
    """Get current Gmail connection status."""
    status = gmail.get_connection_status()
    return GmailConnectResponse(
        connected=status["connected"],
        email=status.get("email"),
        error=status.get("error"),
    )


@app.post("/api/gmail/send/{lead_id}", response_model=GmailSendResponse)
def send_email_to_lead(lead_id: int, db: Session = Depends(get_db)):
    """
    Send the drafted email to a lead via Gmail.

    Requirements:
    - Lead must exist
    - Lead status must be 'approved'
    - Lead must have contact_email
    - Lead must have email_subject and email_body (drafted)
    - Gmail must be connected
    - Daily send limit (100) must not be exceeded
    """
    if settings.demo_mode:
        raise HTTPException(status_code=403, detail="Demo mode: sending disabled")

    # Check Gmail connection
    if not gmail.is_connected():
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error="Gmail not connected. Please connect via /api/gmail/connect first.",
        )

    # Check daily limit
    daily_count = get_daily_email_count(db)
    if daily_count >= DAILY_SEND_LIMIT:
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error=f"Daily send limit ({DAILY_SEND_LIMIT}) reached. Try again tomorrow.",
        )

    # Get lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Check lead status - must be approved
    if lead.status != "approved":
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error=f"Lead status must be 'approved' to send. Current status: '{lead.status}'",
        )

    # Check contact email
    if not lead.contact_email:
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error="Lead has no contact_email",
        )

    # Check draft exists
    if not lead.email_subject or not lead.email_body:
        return GmailSendResponse(
            success=False,
            lead_id=lead_id,
            error="Lead has no drafted email. Generate a draft first via /api/leads/{lead_id}/draft",
        )

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
