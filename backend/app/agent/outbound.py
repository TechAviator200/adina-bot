"""
Outbound email drafting agent for ADINA.

Generates personalized outreach emails based on lead data and knowledge pack.
All logic is deterministic and inspectable.
"""

import json
from pathlib import Path
from typing import Optional, TypedDict

from app.models import Lead


class EmailDraft(TypedDict):
    subject: str
    body: str


# Load knowledge pack at module level (optional)
_knowledge_pack_path = Path(__file__).parent.parent / "knowledge_pack.json"
try:
    with open(_knowledge_pack_path) as f:
        KNOWLEDGE_PACK = json.load(f)
except FileNotFoundError:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"knowledge_pack.json not found at {_knowledge_pack_path}, using empty fallback")
    KNOWLEDGE_PACK = {}
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Error loading knowledge_pack.json: {e}, using empty fallback")
    KNOWLEDGE_PACK = {}


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

    # Check for exact match first
    if industry_lower in INDUSTRY_RELEVANCE:
        return INDUSTRY_RELEVANCE[industry_lower]

    # Check for partial matches
    for key in INDUSTRY_RELEVANCE:
        if key in industry_lower or industry_lower in key:
            return INDUSTRY_RELEVANCE[key]

    return DEFAULT_RELEVANCE


def format_stage(stage: Optional[str]) -> str:
    """Format stage for email copy."""
    if not stage:
        return ""
    return stage


def draft_outreach_email(lead: Lead) -> EmailDraft:
    """
    Generate a personalized outreach email for a lead.

    The draft:
    - References the lead's company, industry, location, and stage if present
    - Uses services/problems relevant to the industry
    - Follows tone_guidelines from knowledge pack
    - Includes a soft CTA
    - Is under 150 words

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
    primary_service = relevance["services"][0].split(":")[0]  # Get short name

    # Build subject line
    if stage:
        subject = f"{company} + ADINA: Operational support for {stage} growth"
    else:
        subject = f"{company} + ADINA: Building systems that scale"

    # Build personalized opening
    if location:
        location_mention = f" based in {location}"
    else:
        location_mention = ""

    # Construct body following tone guidelines:
    # - Professional, direct, confident
    # - Speak to operators who understand their problem
    # - Emphasize building and ownership transfer
    # - Use concrete outcomes
    # - Be concise

    body_lines = [
        f"Hi,",
        f"",
        f"I came across {company}{location_mention} and noticed you're scaling in {industry}.",
        f"",
    ]

    # Add problem-specific hook
    if "burnout" in primary_problem.lower():
        body_lines.append(
            f"At this stage, founders often find themselves working 60+ hour weeks while their teams lack the systems to execute consistently."
        )
    elif "bottleneck" in primary_problem.lower():
        body_lines.append(
            f"At this stage, leadership often becomes the bottleneck—every decision runs through you because the systems don't exist for your team to own execution."
        )
    else:
        body_lines.append(
            f"At this stage, growth often stalls because execution breaks down under complexity—teams operate with guesswork, and critical systems never get built."
        )

    body_lines.extend([
        f"",
        f"ADINA works alongside founders as an operational co-founder. We design, build, and transfer the operating systems your team needs—SOPs, workflows, accountability structures—so you can scale without burning out.",
        f"",
        f"Would a 15-minute call make sense to see if there's a fit?",
        f"",
        f"Best,",
        f"Ify",
        f"ADINA & Co.",
    ])

    body = "\n".join(body_lines)

    return EmailDraft(subject=subject, body=body)
