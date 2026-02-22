"""
Outbound email drafting agent for ADINA.

Generates personalized outreach emails grounded in:
- The lead's industry cross-referenced against knowledge_pack["industries_served"]
- Industry-specific problems from knowledge_pack["problems_we_solve"]
- Preemptive objection handling from knowledge_pack["objections_and_rebuttals"]
All logic is deterministic and inspectable.
"""

from typing import Optional, TypedDict

from app.models import Lead
from app.utils.knowledge_pack import KNOWLEDGE_PACK


class EmailDraft(TypedDict):
    subject: str
    body: str


# Industry to relevant problems/services mapping
INDUSTRY_RELEVANCE = {
    "real estate": {
        "problems": [
            "Executive leadership becoming operational bottlenecks",
            "Teams operating with guesswork due to lack of documented processes",
            "Inability to delegate effectively due to missing infrastructure",
        ],
        "services": [
            "Operating System Audit & Priority Roadmap",
            "System Design, Documentation & Implementation (SOPs, workflows, templates)",
            "Management Structure with Defined Roles and Ownership",
        ],
    },
    "beauty": {
        "problems": [
            "Growth stalling because execution fails under complexity",
            "Systems that never materialize because leadership lacks capacity to build them",
            "Founder burnout from 60+ hour weeks",
        ],
        "services": [
            "Capacity Planning & Leadership Bandwidth Optimization",
            "Team Workflows, Change Management, Onboarding & Training",
            "Performance Measurement & Accountability Systems (KPIs, dashboards)",
        ],
    },
    "travel": {
        "problems": [
            "Inconsistent execution across the organization",
            "Teams operating with guesswork due to lack of documented processes",
            "Executive leadership becoming operational bottlenecks",
        ],
        "services": [
            "System Design, Documentation & Implementation (SOPs, workflows, templates)",
            "Team Workflows, Change Management, Onboarding & Training",
            "Future Roadmap & Growth Planning",
        ],
    },
    "wellness": {
        "problems": [
            "Founder burnout from 60+ hour weeks",
            "Growth stalling because execution fails under complexity",
            "Inability to delegate effectively due to missing infrastructure",
        ],
        "services": [
            "6-Month Operational Co-Founder Partnership: Full operational audit, system design, documentation, implementation, and transfer",
            "Capacity Planning & Leadership Bandwidth Optimization",
            "Management Structure with Defined Roles and Ownership",
        ],
    },
    "wellness & fitness": {
        "problems": [
            "Founder burnout from 60+ hour weeks",
            "Growth stalling because execution fails under complexity",
            "Inability to delegate effectively due to missing infrastructure",
        ],
        "services": [
            "6-Month Operational Co-Founder Partnership: Full operational audit, system design, documentation, implementation, and transfer",
            "Capacity Planning & Leadership Bandwidth Optimization",
            "Management Structure with Defined Roles and Ownership",
        ],
    },
    "healthcare": {
        "problems": [
            "Inconsistent execution across the organization",
            "Systems that never materialize because leadership lacks capacity to build them",
            "Executive leadership becoming operational bottlenecks",
        ],
        "services": [
            "System Design, Documentation & Implementation (SOPs, workflows, templates)",
            "Performance Measurement & Accountability Systems (KPIs, dashboards)",
            "Team Workflows, Change Management, Onboarding & Training",
        ],
    },
    "media": {
        "problems": [
            "Founder burnout from 60+ hour weeks",
            "Teams operating with guesswork due to lack of documented processes",
            "Inability to delegate effectively due to missing infrastructure",
        ],
        "services": [
            "Capacity Planning & Leadership Bandwidth Optimization",
            "System Design, Documentation & Implementation (SOPs, workflows, templates)",
            "Management Structure with Defined Roles and Ownership",
        ],
    },
}

# Default for industries not in mapping
DEFAULT_RELEVANCE = {
    "problems": [
        "Executive leadership becoming operational bottlenecks",
        "Growth stalling because execution fails under complexity",
        "Systems that never materialize because leadership lacks capacity to build them",
    ],
    "services": [
        "Operating System Audit & Priority Roadmap",
        "System Design, Documentation & Implementation (SOPs, workflows, templates)",
        "Capacity Planning & Leadership Bandwidth Optimization",
    ],
}


def get_industry_relevance(industry: str) -> dict:
    """Get relevant problems and services for an industry."""
    industry_lower = industry.lower().strip()

    if industry_lower in INDUSTRY_RELEVANCE:
        return INDUSTRY_RELEVANCE[industry_lower]

    for key in INDUSTRY_RELEVANCE:
        if key in industry_lower or industry_lower in key:
            return INDUSTRY_RELEVANCE[key]

    return DEFAULT_RELEVANCE


def _is_industry_served(industry: str) -> bool:
    """Check if the lead's industry is in knowledge_pack['industries_served']."""
    if not industry:
        return False
    industry_lower = industry.lower()
    for served in KNOWLEDGE_PACK.get("industries_served", []):
        served_lower = served.lower()
        if industry_lower in served_lower or served_lower in industry_lower:
            return True
    return False


def _is_regulated_industry(industry: str) -> bool:
    """Check if the industry is regulated (Healthcare or Real Estate)."""
    if not industry:
        return False
    industry_lower = industry.lower()
    return any(reg in industry_lower for reg in ["healthcare", "real estate", "regulated"])


def _get_industry_proof_point(industry: str) -> Optional[str]:
    """Find a proof point from knowledge_pack relevant to the lead's industry."""
    industry_lower = industry.lower()
    for proof in KNOWLEDGE_PACK.get("proof_points", []):
        if industry_lower in proof.lower():
            return proof
    return None


def _get_contextual_rebuttal(lead: Lead) -> Optional[str]:
    """
    Return a single-sentence preemptive rebuttal when the lead context warrants it.

    Checks:
    - Regulated industry → addresses "will it work for my industry?"
    - Notes mention prior consulting → addresses "we've tried consultants"
    """
    rebuttals = KNOWLEDGE_PACK.get("objections_and_rebuttals", {})
    industry = lead.industry or ""
    notes_lower = (lead.notes or "").lower()

    # Regulated industry: preempt the "proven methodology" concern
    if _is_regulated_industry(industry):
        full = rebuttals.get("How do we know it will work for our industry?", "")
        if full:
            # Use only the first sentence to keep the email concise
            first_sentence = full.split(".")[0].strip()
            return first_sentence + "." if first_sentence else None

    # Notes reference prior consulting experience
    if "consultant" in notes_lower or "fractional coo" in notes_lower or "fractional co" in notes_lower:
        full = rebuttals.get("We've tried consultants before", "")
        if full:
            first_sentence = full.split(".")[0].strip()
            return first_sentence + "." if first_sentence else None

    return None


def format_stage(stage: Optional[str]) -> str:
    """Format stage for email copy."""
    if not stage:
        return ""
    return stage


def draft_outreach_email(lead: Lead) -> EmailDraft:
    """
    Generate a personalized outreach email for a lead.

    The draft:
    - Cross-references lead's industry against knowledge_pack["industries_served"]
    - Uses industry-specific problems/services from INDUSTRY_RELEVANCE
    - Optionally includes a proof point for known industries
    - Preemptively addresses objections based on industry or notes context
    - Follows tone_guidelines from knowledge pack (direct, concise, <200 words)

    Args:
        lead: Lead model instance with company info

    Returns:
        EmailDraft with subject and body
    """
    company = lead.company
    industry = lead.industry or "your industry"
    location = lead.location
    stage = format_stage(lead.stage)

    # Get industry-relevant content
    relevance = get_industry_relevance(industry)
    primary_problem = relevance["problems"][0]
    primary_service = relevance["services"][0].split(":")[0]

    # Build subject line
    if stage:
        subject = f"{company} + ADINA: Operational support for {stage} growth"
    else:
        subject = f"{company} + ADINA: Building systems that scale"

    # Build personalized opening
    location_mention = f" based in {location}" if location else ""

    # Cross-reference with knowledge_pack to confirm this is a served industry
    is_served = _is_industry_served(industry)

    body_lines = [
        "Hi,",
        "",
        f"I came across {company}{location_mention} and noticed you're scaling in {industry}.",
        "",
    ]

    # Problem-specific hook
    if "burnout" in primary_problem.lower():
        body_lines.append(
            "At this stage, founders often find themselves working 60+ hour weeks "
            "while their teams lack the systems to execute consistently."
        )
    elif "bottleneck" in primary_problem.lower():
        body_lines.append(
            "At this stage, leadership often becomes the bottleneck—every decision "
            "runs through you because the systems don't exist for your team to own execution."
        )
    else:
        body_lines.append(
            "At this stage, growth often stalls because execution breaks down under "
            "complexity—teams operate with guesswork, and critical systems never get built."
        )

    body_lines.extend([
        "",
        "ADINA works alongside founders as an operational co-founder. We design, build, "
        "and transfer the operating systems your team needs—SOPs, workflows, accountability "
        "structures—so you can scale without burning out.",
        "",
    ])

    # Add a contextual rebuttal if relevant (regulated industry or prior consulting mention)
    rebuttal = _get_contextual_rebuttal(lead)
    if rebuttal:
        body_lines.extend([rebuttal, ""])

    # For served industries with a proof point, add brief credibility line
    if is_served and not rebuttal:
        proof = _get_industry_proof_point(industry)
        if proof:
            # Extract just the metric highlight (first clause up to first semicolon)
            highlight = proof.split(";")[0].strip().rstrip(".")
            if highlight:
                body_lines.extend([f"We've seen this work in {industry}: {highlight}.", ""])

    body_lines.extend([
        "Would a 15-minute call make sense to see if there's a fit?",
        "",
        "Best,",
        "Ify",
        "ADINA & Co.",
    ])

    body = "\n".join(body_lines)

    return EmailDraft(subject=subject, body=body)
