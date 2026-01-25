"""
Lead scoring agent for ADINA.

Scores leads based on transparent, additive criteria.
All logic is deterministic and inspectable.
"""

import json
import re
from pathlib import Path
from typing import List, Optional, TypedDict

from app.models import Lead


class ScoreResult(TypedDict):
    score: float
    reasons: List[str]


# Load knowledge pack at module level
_knowledge_pack_path = Path(__file__).parent.parent / "knowledge_pack.json"
with open(_knowledge_pack_path) as f:
    KNOWLEDGE_PACK = json.load(f)

# Extract industries from knowledge pack (normalized to lowercase)
KNOWLEDGE_PACK_INDUSTRIES = [
    industry.lower() for industry in KNOWLEDGE_PACK.get("industries_served", [])
]

# Keywords that indicate operational needs in notes
OPS_KEYWORDS = [
    "ops",
    "operations",
    "scaling",
    "scale",
    "growth",
    "hiring",
    "growing",
    "expand",
    "expansion",
    "coordinator",
    "manager",
    "director",
    "needs",
    "looking for",
    "hot lead",
    "strong lead",
]

# US states and common US location indicators
US_LOCATIONS = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    # Common abbreviations and indicators
    "usa", "united states", "u.s.", "us",
    # State abbreviations
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
]


def is_industry_match(industry: Optional[str]) -> bool:
    """Check if industry matches knowledge pack industries."""
    if not industry:
        return False

    industry_lower = industry.lower()

    for kp_industry in KNOWLEDGE_PACK_INDUSTRIES:
        # Check for substring match in either direction
        if kp_industry in industry_lower or industry_lower in kp_industry:
            return True

        # Check for key terms
        kp_terms = kp_industry.split()
        for term in kp_terms:
            if len(term) > 3 and term in industry_lower:
                return True

    return False


def is_us_or_dubai(location: Optional[str]) -> bool:
    """Check if location is in US or Dubai."""
    if not location:
        return False

    location_lower = location.lower()

    # Check for Dubai
    if "dubai" in location_lower or "uae" in location_lower:
        return True

    # Check for US locations
    for us_loc in US_LOCATIONS:
        if us_loc in location_lower:
            return True

    # Check for city, state pattern with common US cities
    # Pattern like "Chicago, Illinois" or "New York, NY"
    if "," in location_lower:
        parts = location_lower.split(",")
        if len(parts) >= 2:
            state_part = parts[-1].strip()
            for us_loc in US_LOCATIONS:
                if us_loc == state_part or state_part == us_loc:
                    return True

    return False


def is_employee_range_match(employees: Optional[int]) -> bool:
    """Check if employee count is in target range (5-50)."""
    if employees is None:
        return False
    return 5 <= employees <= 50


def is_stage_match(stage: Optional[str]) -> bool:
    """Check if stage contains 'Series A' or 'A'."""
    if not stage:
        return False

    stage_lower = stage.lower().strip()

    # Check for Series A
    if "series a" in stage_lower:
        return True

    # Check for standalone "A" (but not as part of another word)
    if stage_lower == "a":
        return True

    # Check for "A" at word boundaries
    if re.search(r'\ba\b', stage_lower):
        return True

    return False


def has_ops_keywords(notes: Optional[str]) -> bool:
    """Check if notes mention ops, scaling, growth, hiring, etc."""
    if not notes:
        return False

    notes_lower = notes.lower()

    for keyword in OPS_KEYWORDS:
        if keyword in notes_lower:
            return True

    return False


def score_lead(lead: Lead) -> ScoreResult:
    """
    Score a lead based on transparent, additive criteria.

    Scoring logic:
    - Industry in knowledge_pack industries → +30
    - Location US or Dubai → +20
    - Employees 5–50 → +20
    - Stage contains "Series A" or "A" → +15
    - Notes mention ops, scaling, growth, hiring → +15

    Score is capped at 100.

    Args:
        lead: Lead model instance

    Returns:
        ScoreResult with score (float) and reasons (list of strings)
    """
    score = 0.0
    reasons: List[str] = []

    # Industry match: +30
    if is_industry_match(lead.industry):
        score += 30
        reasons.append(f"Industry '{lead.industry}' matches target industries (+30)")

    # Location match: +20
    if is_us_or_dubai(lead.location):
        score += 20
        reasons.append(f"Location '{lead.location}' is in US or Dubai (+20)")

    # Employee range match: +20
    if is_employee_range_match(lead.employees):
        score += 20
        reasons.append(f"Employee count {lead.employees} is in target range 5-50 (+20)")

    # Stage match: +15
    if is_stage_match(lead.stage):
        score += 15
        reasons.append(f"Stage '{lead.stage}' indicates Series A (+15)")

    # Notes keyword match: +15
    if has_ops_keywords(lead.notes):
        score += 15
        # Find which keywords matched for transparency
        matched_keywords = [
            kw for kw in OPS_KEYWORDS
            if lead.notes and kw in lead.notes.lower()
        ]
        keyword_sample = ", ".join(matched_keywords[:3])
        if len(matched_keywords) > 3:
            keyword_sample += "..."
        reasons.append(f"Notes contain operational keywords: {keyword_sample} (+15)")

    # Cap score at 100
    score = min(score, 100.0)

    # Add summary if no reasons
    if not reasons:
        reasons.append("No scoring criteria matched")

    return ScoreResult(score=score, reasons=reasons)
