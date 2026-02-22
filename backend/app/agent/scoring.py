"""
Lead scoring agent for ADINA — aligned with the Adina Playbook.

Scores leads using transparent, additive criteria grounded in Adina's ICP:
  High Score: Founder-led + outpaced infrastructure, Revenue $10M+ scaling
              complexity, Founder burnout risk (60+ hrs/week)
  Low Score:  Early-stage/pre-revenue, Small agencies (<5 employees),
              Regulated industries (Healthcare/Real Estate), Lifestyle operations
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

# Regulated / lower-priority industries per Adina Playbook
REGULATED_INDUSTRIES = {"healthcare", "real estate"}


# ── HIGH SCORE SIGNALS (checked against lead.notes + lead.company_description) ──

# Founder-led business that has outpaced its own infrastructure
FOUNDER_LED_SIGNALS = [
    "founder-led",
    "founder led",
    "founder owned",
    "owner-operated",
    "owner operated",
    "ceo does everything",
    "founder still doing",
    "outpaced",
    "outgrown",
    "no systems",
    "no infrastructure",
    "infrastructure gap",
    "lacks infrastructure",
    "still founder-run",
    "founder runs",
    "founder is the bottleneck",
    "founder bottleneck",
    "leadership bottleneck",
]

# Revenue $10M+ or clear scaling-complexity language
REVENUE_SCALE_SIGNALS = [
    "10m+",
    "$10m",
    "10 million",
    "eight figure",
    "eight-figure",
    "multi-million",
    "scaling revenue",
    "revenue growth",
    "seven figure",
    "7-figure",
    "8-figure",
    "growing fast",
    "rapid growth",
    "scale-up",
    "scale up",
    "high growth",
    "hypergrowth",
]

# Founder burnout risk — 60+ hours/week, overwhelmed, can't delegate
BURNOUT_SIGNALS = [
    "60+ hours",
    "60 hours",
    "70 hours",
    "80 hours",
    "working 60",
    "working 70",
    "working 80",
    "burnout",
    "burned out",
    "burnt out",
    "wearing all hats",
    "wearing every hat",
    "doing everything",
    "can't delegate",
    "cannot delegate",
    "stretched thin",
    "overwhelmed founder",
    "stretched too thin",
]

# ── LOW SCORE SIGNALS ────────────────────────────────────────────────────────

# Early-stage / pre-revenue (checked against notes and stage field)
EARLY_STAGE_SIGNALS = [
    "pre-revenue",
    "pre revenue",
    "no revenue",
    "idea stage",
    "concept stage",
    "pre-launch",
    "pre launch",
    "not yet launched",
    "early stage",
    "just starting",
    "just launched",
    "newly launched",
]

# Lifestyle operations — not scaling, not founder-led growth
LIFESTYLE_SIGNALS = [
    "lifestyle business",
    "lifestyle brand",
    "solopreneur",
    "solo business",
    "one-person shop",
    "one person shop",
    "freelancer",
    "self-employed",
    "hobby business",
    "side project",
    "side hustle",
    "part-time business",
]

# Explicit not-a-fit signals
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

# Strong positive signals — explicit ADINA service need expressed in notes
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


def _notes_text(lead: Lead) -> str:
    """Combine notes and company_description into a single searchable string."""
    parts = [
        lead.notes or "",
        getattr(lead, "company_description", None) or "",
    ]
    return " ".join(parts).lower()


def is_industry_match(industry: Optional[str]) -> bool:
    """Check if industry matches knowledge pack industries."""
    if not industry:
        return False

    industry_lower = industry.lower()

    for kp_industry in KNOWLEDGE_PACK_INDUSTRIES:
        if kp_industry in industry_lower or industry_lower in kp_industry:
            return True
        # Check for key terms
        for term in kp_industry.split():
            if len(term) > 3 and term in industry_lower:
                return True

    return False


def is_regulated_industry(industry: Optional[str]) -> bool:
    """Check if industry is a regulated/lower-priority sector per Adina Playbook."""
    if not industry:
        return False
    industry_lower = industry.lower()
    return any(reg in industry_lower for reg in REGULATED_INDUSTRIES)


def is_us_or_dubai(location: Optional[str]) -> bool:
    """Check if location is in US or Dubai."""
    if not location:
        return False

    location_lower = location.lower()

    if "dubai" in location_lower or "uae" in location_lower:
        return True

    for us_loc in US_LOCATIONS:
        if us_loc in location_lower:
            return True

    if "," in location_lower:
        parts = location_lower.split(",")
        if len(parts) >= 2:
            state_part = parts[-1].strip()
            for us_loc in US_LOCATIONS:
                if us_loc == state_part:
                    return True

    return False


def is_small_agency(employees: Optional[int]) -> bool:
    """Check if team is below minimum scale threshold (<5 employees)."""
    if employees is None:
        return False
    return employees < 5


def has_founder_led_signal(notes: str) -> bool:
    """Detect founder-led business that has outpaced its infrastructure."""
    return any(sig in notes for sig in FOUNDER_LED_SIGNALS)


def has_revenue_scale_signal(notes: str) -> bool:
    """Detect $10M+ revenue or clear scaling-complexity language."""
    return any(sig in notes for sig in REVENUE_SCALE_SIGNALS)


def has_burnout_signal(notes: str) -> bool:
    """Detect founder burnout risk — 60+ hours/week or delegation failure."""
    return any(sig in notes for sig in BURNOUT_SIGNALS)


def has_early_stage_signal(lead: Lead) -> bool:
    """Detect early-stage or pre-revenue companies (low score)."""
    notes = _notes_text(lead)
    notes_match = any(sig in notes for sig in EARLY_STAGE_SIGNALS)

    # Also check the stage field for explicit early-stage indicators
    stage_lower = (lead.stage or "").lower()
    stage_match = any(
        sig in stage_lower
        for sig in ["pre-revenue", "pre revenue", "pre-seed", "idea", "concept"]
    )

    return notes_match or stage_match


def has_lifestyle_signal(notes: str) -> bool:
    """Detect lifestyle or solo operations (not aligned with Adina's growth model)."""
    return any(sig in notes for sig in LIFESTYLE_SIGNALS)


def has_strong_positive_signal(notes: str) -> bool:
    """Check if notes contain an explicit ADINA service need or hot/strong lead flag."""
    return any(sig in notes for sig in STRONG_POSITIVE_SIGNALS)


def has_ops_keywords(notes: str) -> bool:
    """Check if notes mention ops, scaling, growth, etc. (weaker positive signal)."""
    return any(keyword in notes for keyword in OPS_KEYWORDS)


def has_negative_signal(notes: Optional[str]) -> bool:
    """Check if notes indicate the lead is explicitly NOT a current fit."""
    if not notes:
        return False
    notes_lower = notes.lower()
    return any(sig in notes_lower for sig in NEGATIVE_SIGNALS)


def get_matched_signals(lead: Lead) -> dict:
    """Return matched positive and negative signals for a lead."""
    notes = _notes_text(lead)
    return {
        "founder_led": [s for s in FOUNDER_LED_SIGNALS if s in notes],
        "revenue_scale": [s for s in REVENUE_SCALE_SIGNALS if s in notes],
        "burnout": [s for s in BURNOUT_SIGNALS if s in notes],
        "strong_positives": [s for s in STRONG_POSITIVE_SIGNALS if s in notes],
        "ops_keywords": [k for k in OPS_KEYWORDS if k in notes],
        "negatives": [s for s in NEGATIVE_SIGNALS if s in notes],
        "early_stage": [s for s in EARLY_STAGE_SIGNALS if s in notes],
        "lifestyle": [s for s in LIFESTYLE_SIGNALS if s in notes],
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
    Score a lead against the Adina Playbook ICP.

    Scoring logic:
    HIGH SCORE (+):
      - Industry in Adina-served markets              → +30
      - Location in US or Dubai                       → +20
      - Founder-led + outpaced infrastructure (notes) → +25
      - Revenue $10M+ / scaling complexity (notes)    → +20
      - Founder burnout risk 60+hrs/week (notes)      → +20
      - Explicit ADINA service need in notes          → +15
      - General operational context in notes          → +10

    LOW SCORE (–):
      - Early-stage / pre-revenue                     → -20
      - Small agency (<5 employees)                   → -15
      - Regulated industry (Healthcare/Real Estate)   → -10
      - Lifestyle or solo operation                   → -15
      - Explicit not-a-fit signal in notes            → -15

    Score is capped between 0 and 100.
    """
    score = 0.0
    reasons: List[str] = []

    notes = _notes_text(lead)

    # ── HIGH SCORE ──────────────────────────────────────────────────────────
    if is_industry_match(lead.industry):
        score += 30
        reasons.append(f"Industry '{lead.industry}' is an Adina-served market (+30)")

    if is_us_or_dubai(lead.location):
        score += 20
        reasons.append(f"Location '{lead.location}' is in our primary market (+20)")

    if has_founder_led_signal(notes):
        score += 25
        reasons.append("Founder-led business showing signs of outpaced infrastructure (+25)")

    if has_revenue_scale_signal(notes):
        score += 20
        reasons.append("Revenue signals indicate $10M+ scaling complexity (+20)")

    if has_burnout_signal(notes):
        score += 20
        reasons.append("Founder burnout risk — working 60+ hours/week (+20)")

    if has_strong_positive_signal(notes):
        score += 15
        reasons.append("Notes show explicit operational need for Adina services (+15)")
    elif has_ops_keywords(notes):
        score += 10
        reasons.append("Notes reference operational activity and scaling context (+10)")

    # ── LOW SCORE ────────────────────────────────────────────────────────────
    if has_early_stage_signal(lead):
        score -= 20
        reasons.append("Early-stage or pre-revenue — not yet at Adina's target scale (-20)")

    if is_small_agency(lead.employees):
        score -= 15
        reasons.append(f"Small team ({lead.employees} employees) — below minimum scale threshold (-15)")

    if is_regulated_industry(lead.industry):
        score -= 10
        reasons.append(f"Regulated industry ('{lead.industry}') adds complexity and longer sales cycles (-10)")

    if has_lifestyle_signal(notes):
        score -= 15
        reasons.append("Lifestyle or solo operation — not aligned with Adina's growth-stage model (-15)")

    if has_negative_signal(lead.notes):
        score -= 15
        matched = next((s for s in NEGATIVE_SIGNALS if s in (lead.notes or "").lower()), "")
        reasons.append(f"Notes indicate current mismatch: '{matched}' (-15)")

    # Cap between 0 and 100
    score = max(0.0, min(score, 100.0))

    if not reasons:
        reasons.append("No scoring criteria matched — needs manual review")

    return ScoreResult(score=score, reasons=reasons)
