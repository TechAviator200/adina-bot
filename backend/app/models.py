from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Date
from sqlalchemy.sql import func

from app.db import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, nullable=False, index=True)
    industry = Column(String, nullable=False, index=True)
    location = Column(String, nullable=True, index=True)
    employees = Column(Integer, nullable=True)
    stage = Column(String, nullable=True)
    website = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    score = Column(Float, default=0)
    score_reason = Column(Text, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_role = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    email_subject = Column(String, nullable=True)
    email_body = Column(Text, nullable=True)
    status = Column(String, default="new")
    source = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Profile fields (added for company profile panel)
    phone = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    contacts_json = Column(Text, nullable=True)  # JSON: [{name,title,email,linkedin_url,source}]
    # notes = internal flagging notes from CSV (scoring source of truth)
    # company_description = external/scraped description (lazy-cached from website or ICP fallback)
    company_description = Column(Text, nullable=True)


class SentEmail(Base):
    __tablename__ = "sent_emails"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    gmail_message_id = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_date = Column(Date, nullable=False, index=True)


class DailyEmailCount(Base):
    __tablename__ = "daily_email_counts"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    count = Column(Integer, default=0)


class PlacesCache(Base):
    """Google Places Details cache (30-day TTL by default)."""
    __tablename__ = "places_cache"
    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(String, unique=True, index=True, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), index=True, nullable=False)


class HunterCache(Base):
    """Hunter.io domain search cache (14-day default TTL)."""
    __tablename__ = "hunter_cache"
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, unique=True, index=True, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), index=True, nullable=False)


class GmailToken(Base):
    """Encrypted Gmail OAuth tokens, keyed by user_key for multi-user support."""
    __tablename__ = "gmail_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_key = Column(String, unique=True, index=True, nullable=False)
    provider = Column(String, default="google")
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=True)
    scope = Column(String, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    email_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class SearchApiDailyCount(Base):
    """Daily counter for external search API calls (PSE + SerpApi). Hard cap: 95/day."""
    __tablename__ = "search_api_daily_counts"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    count = Column(Integer, default=0)


class CompanyDiscoveryCache(Base):
    __tablename__ = "company_discovery_cache"

    id = Column(Integer, primary_key=True, index=True)
    query_hash = Column(String, unique=True, index=True, nullable=False)
    source = Column(String, nullable=False)
    industry = Column(String, nullable=False)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    query_text = Column(Text, nullable=False)
    limit = Column(Integer, nullable=False)
    results_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), index=True, nullable=False)
