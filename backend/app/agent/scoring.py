"""
Lead scoring agent for ADINA.

Scores leads based on transparent, additive criteria.
All logic is deterministic and inspectable.
"""

import re
from typing import List, Optional, TypedDict

from app.models import Lead
from app.utils.knowledge_pack import KNOWLEDGE_PACK


class ScoreResult(TypedDict):
    score: float
    reasons: List[str]

# Extract industries from knowledge pack (normalized to lowercase)
KNOWLEDGE_PACK_INDUSTRIES = [
    industry.lower() for industry in KNOWLEDGE_PACK.get("industries_served", [])
]

# Strong positive signals — explicit "hot/strong lead" or specific ADINA service need
STRONG_POSITIVE_SIGNALS = [
    "hot lead",
    "strong lead",
    "needs procurement",
    "needs supply",
    "needs operations",
    "needs ops",
    "needs strategy",
    "needs logistics",
    "needs project manager",
    "needs senior consultant",
    "needs coordinator",
    "needs director",
    "needs manager",
    "in need of supply",
    "in need of strategy",
    "in need of operations",
    "in need of ops",
    "in need of logistics",
    "urgent need",
    "immediate need",
]

# General operational keywords (weaker signal)
OPS_KEYWORDS = [
    "ops",
    "operations",
    "scaling",
    "scale",
    "growth",
    "growing",
    "expand",
    "expansion",
    "coordinator",
    "manager",
    "director",
    "looking for",
]

# Negative signals — lead has explicitly stated they are NOT a current fit
NEGATIVE_SIGNALS = [
    "only hiring brokers",
    "only hiring analysts",
    "only hiring for sales",
    "only hiring sales",
    "only hiring agents",
    "no immediate hiring for strategy",
    "no immediate hiring for ops",
    "no immediate hiring for strateg",
    "no immediate need",
    "no overlap",
    "not a fit",
    "not interested",
    "no operational need",
    "no plans to hire",
    "no need for",
    "downsizing",
    "laying off",
    "restructuring",
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


def has_strong_positive_signal(notes: Optional[str]) -> bool:
    """Check if notes contain an explicit hot/strong lead signal."""
    if not notes:
        return False
    notes_lower = notes.lower()
    return any(sig in notes_lower for sig in STRONG_POSITIVE_SIGNALS)


def has_ops_keywords(notes: Optional[str]) -> bool:
    """Check if notes mention ops, scaling, growth, etc. (weaker positive signal)."""
    if not notes:
        return False
    notes_lower = notes.lower()
    return any(keyword in notes_lower for keyword in OPS_KEYWORDS)


def has_negative_signal(notes: Optional[str]) -> bool:
    """Check if notes indicate the lead is explicitly NOT a current fit."""
    if not notes:
        return False
    notes_lower = notes.lower()
    return any(sig in notes_lower for sig in NEGATIVE_SIGNALS)


def get_matched_signals(notes: Optional[str]) -> dict:
    """
    Return matched positive and negative signals from notes.

    Returns dict with keys:
        strong_positives: list of matched strong positive phrases
        ops_keywords: list of matched general ops keywords
        negatives: list of matched negative phrases
    """
    if not notes:
        return {"strong_positives": [], "ops_keywords": [], "negatives": []}

    notes_lower = notes.lower()
    return {
        "strong_positives": [s for s in STRONG_POSITIVE_SIGNALS if s in notes_lower],
        "ops_keywords": [k for k in OPS_KEYWORDS if k in notes_lower],
        "negatives": [s for s in NEGATIVE_SIGNALS if s in notes_lower],
    }


def get_quality_label(score: float, has_neg: bool) -> str:
    """Return a human-readable quality label based on score and signals."""
    if has_neg:
        if score >= 65:
            return "Possible Fit — Not Hiring Now"
        return "Poor Fit"
    if score >= 90:
        return "Hot Lead"
    if score >= 70:
        return "Strong Fit"
    if score >= 50:
        return "Good Fit"
    if score >= 30:
        return "Possible Fit"
    return "Weak Fit"


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

    # Notes signal analysis
    signals = get_matched_signals(lead.notes)

    if signals["strong_positives"]:
        # Hot/strong lead or explicit ADINA service need → +20
        score += 20
        sample = ", ".join(signals["strong_positives"][:2])
        reasons.append(f"Notes show explicit demand: '{sample}' (+20)")
    elif signals["ops_keywords"]:
        # General operational keywords → +10
        score += 10
        sample = ", ".join(signals["ops_keywords"][:3])
        reasons.append(f"Notes mention operational activity: {sample} (+10)")

    if signals["negatives"]:
        # Explicit not-a-fit signal → -15
        score -= 15
        sample = signals["negatives"][0]
        reasons.append(f"Notes indicate current mismatch: '{sample}' (-15)")

    # Cap score between 0 and 100
    score = max(0.0, min(score, 100.0))

    # Add summary if no reasons
    if not reasons:
        reasons.append("No scoring criteria matched — needs manual review")

    return ScoreResult(score=score, reasons=reasons)
