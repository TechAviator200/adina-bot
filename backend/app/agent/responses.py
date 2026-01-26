"""
Inbound response agent for ADINA.

Classifies incoming email replies by intent and drafts appropriate follow-ups.
All logic is rule-based and inspectable.
"""

import re
from typing import Dict, List, Literal, Tuple, TypedDict

from app.models import Lead
from app.utils.response_playbook import RESPONSE_PLAYBOOK


IntentLabel = Literal["positive", "neutral", "objection", "deferral", "negative"]


class ClassificationResult(TypedDict):
    intent: IntentLabel
    confidence: str  # "high", "medium", "low"
    matched_keywords: List[str]
    matched_patterns: List[str]


class FollowupResult(TypedDict):
    body: str
    intent: IntentLabel


def _normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, collapse whitespace."""
    return " ".join(text.lower().split())


def _count_keyword_matches(text: str, keywords: List[str]) -> Tuple[int, List[str]]:
    """Count keyword matches and return matched keywords."""
    text_lower = text.lower()
    matches = []
    for keyword in keywords:
        if keyword.lower() in text_lower:
            matches.append(keyword)
    return len(matches), matches


def _count_pattern_matches(text: str, patterns: List[str]) -> Tuple[int, List[str]]:
    """Count pattern matches and return matched patterns."""
    text_normalized = _normalize_text(text)
    matches = []
    for pattern in patterns:
        if pattern.lower() in text_normalized:
            matches.append(pattern)
    return len(matches), matches


def classify_reply(text: str) -> IntentLabel:
    """
    Classify an inbound email reply by intent.

    Uses keyword and pattern matching against the response playbook.
    Returns the intent with the highest match score.

    Intent labels:
    - positive: Interested, wants to learn more, agrees to call
    - neutral: Asks questions, seeks clarification
    - objection: Raises concerns about price, fit, timing
    - deferral: Delays decision, asks to reconnect later
    - negative: Declines, unsubscribes, says no

    Args:
        text: The inbound email text

    Returns:
        IntentLabel (one of: positive, neutral, objection, deferral, negative)
    """
    result = classify_reply_detailed(text)
    return result["intent"]


def classify_reply_detailed(text: str) -> ClassificationResult:
    """
    Classify an inbound email reply with detailed match information.

    Returns intent, confidence level, and which keywords/patterns matched.

    Args:
        text: The inbound email text

    Returns:
        ClassificationResult with intent, confidence, and match details
    """
    classification = RESPONSE_PLAYBOOK["intent_classification"]

    scores: Dict[IntentLabel, dict] = {}

    for intent, config in classification.items():
        keywords = config.get("keywords", [])
        patterns = config.get("patterns", [])

        keyword_count, matched_keywords = _count_keyword_matches(text, keywords)
        pattern_count, matched_patterns = _count_pattern_matches(text, patterns)

        # Patterns are weighted higher than keywords
        score = keyword_count + (pattern_count * 2)

        scores[intent] = {
            "score": score,
            "matched_keywords": matched_keywords,
            "matched_patterns": matched_patterns,
        }

    # Check for explicit negative signals first (they override other signals)
    negative_score = scores.get("negative", {}).get("score", 0)
    if negative_score >= 2:  # Strong negative signal
        return ClassificationResult(
            intent="negative",
            confidence="high" if negative_score >= 3 else "medium",
            matched_keywords=scores["negative"]["matched_keywords"],
            matched_patterns=scores["negative"]["matched_patterns"],
        )

    # Find the intent with the highest score
    best_intent: IntentLabel = "neutral"  # Default
    best_score = 0
    best_data = {"matched_keywords": [], "matched_patterns": []}

    for intent, data in scores.items():
        if data["score"] > best_score:
            best_score = data["score"]
            best_intent = intent
            best_data = data

    # Determine confidence based on score and separation from other intents
    if best_score == 0:
        confidence = "low"
    elif best_score >= 4:
        confidence = "high"
    elif best_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return ClassificationResult(
        intent=best_intent,
        confidence=confidence,
        matched_keywords=best_data["matched_keywords"],
        matched_patterns=best_data["matched_patterns"],
    )


def _detect_objection_type(text: str) -> str:
    """Detect the type of objection from the text."""
    text_lower = text.lower()

    # Price objection
    price_keywords = ["expensive", "cost", "price", "budget", "afford", "investment"]
    if any(kw in text_lower for kw in price_keywords):
        return "price"

    # Timing objection
    timing_keywords = ["busy", "later", "not now", "timing", "quarter", "month"]
    if any(kw in text_lower for kw in timing_keywords):
        return "timing"

    # Fit objection
    fit_keywords = ["not sure if", "right fit", "don't think", "not for us", "not what we need"]
    if any(kw in text_lower for kw in fit_keywords):
        return "fit"

    return "default"


def draft_followup(intent_label: IntentLabel, lead: Lead) -> str:
    """
    Draft a follow-up email based on the classified intent.

    The draft:
    - Follows tone guidelines (professional, direct, not pushy)
    - Does not oversell
    - References the lead's company when appropriate
    - Uses the appropriate template for the intent

    Args:
        intent_label: The classified intent of the inbound reply
        lead: Lead model instance for personalization

    Returns:
        The drafted follow-up email body
    """
    templates = RESPONSE_PLAYBOOK["followup_templates"]
    template_config = templates.get(intent_label, templates["neutral"])

    company = lead.company or "your company"

    if intent_label == "objection":
        # For objections, we need to detect the objection type
        # Since we don't have the original text here, use the default
        # In practice, you'd pass the objection type or original text
        objection_templates = template_config.get("templates_by_objection", {})
        template = objection_templates.get("default", "")
    else:
        template = template_config.get("template", "")

    # Personalize the template
    body = template.replace("{company}", company)

    # Handle other placeholders with reasonable defaults
    body = body.replace("{suggested_time}", "sometime this week")
    body = body.replace("{followup_timeframe}", "a few weeks")
    body = body.replace("{answer_to_question}", "[I'll address your specific question here]")

    return body


def draft_followup_with_context(
    intent_label: IntentLabel,
    lead: Lead,
    inbound_text: str,
) -> FollowupResult:
    """
    Draft a follow-up email with context from the original inbound message.

    This version uses the inbound text to:
    - Detect objection type for objection responses
    - Potentially extract specific questions for neutral responses

    Args:
        intent_label: The classified intent of the inbound reply
        lead: Lead model instance for personalization
        inbound_text: The original inbound email text

    Returns:
        FollowupResult with body and intent
    """
    templates = RESPONSE_PLAYBOOK["followup_templates"]
    template_config = templates.get(intent_label, templates["neutral"])

    company = lead.company or "your company"

    if intent_label == "objection":
        # Detect the specific objection type
        objection_type = _detect_objection_type(inbound_text)
        objection_templates = template_config.get("templates_by_objection", {})
        template = objection_templates.get(objection_type, objection_templates.get("default", ""))
    else:
        template = template_config.get("template", "")

    # Personalize the template
    body = template.replace("{company}", company)

    # Handle other placeholders
    body = body.replace("{suggested_time}", "sometime this week")

    # For deferrals, try to extract a timeframe from their message
    if intent_label == "deferral":
        followup_time = _extract_timeframe(inbound_text)
        body = body.replace("{followup_timeframe}", followup_time)

    # For neutral (questions), note that a human should fill in the answer
    body = body.replace("{answer_to_question}", "[Your specific question addressed here]")

    return FollowupResult(body=body, intent=intent_label)


def _extract_timeframe(text: str) -> str:
    """Extract a follow-up timeframe from deferral text."""
    text_lower = text.lower()

    # Look for specific timeframes mentioned
    if "next quarter" in text_lower or "q2" in text_lower or "q3" in text_lower or "q4" in text_lower:
        return "next quarter"
    if "next month" in text_lower:
        return "a month"
    if "next week" in text_lower:
        return "next week"
    if "few weeks" in text_lower:
        return "a few weeks"
    if "next year" in text_lower or "new year" in text_lower:
        return "the new year"
    if "january" in text_lower:
        return "January"
    if "after" in text_lower:
        # Try to find what they're waiting for
        if "fundraise" in text_lower or "raise" in text_lower:
            return "after your fundraise"
        if "hire" in text_lower:
            return "after your hiring push"
        if "launch" in text_lower:
            return "after your launch"

    return "a few weeks"
