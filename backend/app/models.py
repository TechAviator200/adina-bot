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
