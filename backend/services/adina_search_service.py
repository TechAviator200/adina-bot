"""
AdinaSearchService — Smart two-tier search for company lead discovery.

Priority:
  1. Google Programmable Search Engine (PSE/CSE) — free, ~100 queries/day
  2. SerpApi — paid, used only when PSE returns 0 results or is unavailable

Returns a unified lead list in the GoogleCSE dict shape so the existing
deduplication and scoring pipeline in main.py works without modification.
"""
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class AdinaSearchService:
    """Smart search: Google PSE first, SerpApi fallback."""

    def __init__(self):
        self._cse = None
        self._serp = None

        try:
            from services.google_cse_service import GoogleCSEService
            svc = GoogleCSEService()
            if svc.is_configured():
                self._cse = svc
                logger.debug("[AdinaSearch] Google PSE configured")
        except Exception as exc:
            logger.debug("[AdinaSearch] GoogleCSEService unavailable: %s", exc)

        try:
            from services.serpapi_service import SerpAPIService
            from app.settings import settings
            if settings.serpapi_api_key:
                self._serp = SerpAPIService()
                logger.debug("[AdinaSearch] SerpApi configured")
        except Exception as exc:
            logger.debug("[AdinaSearch] SerpAPIService unavailable: %s", exc)

    def is_configured(self) -> bool:
        """True if at least one search provider is ready."""
        return self._cse is not None or self._serp is not None

    def discover_leads(
        self,
        industry: str,
        keywords: Optional[List[str]] = None,
        company: Optional[str] = None,
        limit: int = 10,
    ) -> Tuple[List[dict], str, str, Optional[str]]:
        """
        Discover leads using the best available search provider.

        Returns:
            (leads, query_used, source, message)
            - leads: normalized dicts with keys company/website/description/industry/source_url
            - query_used: display string of the query that ran
            - source: "google_cse" | "serpapi" | "none"
            - message: human-readable error/fallback note, or None on success
        """
        query = self._build_query(industry, keywords, company)

        # ── 1. Google PSE (free tier) ────────────────────────────────────────
        if self._cse is not None:
            try:
                leads, cse_msg = self._cse.discover_leads(industry, keywords, company)
                if cse_msg:
                    logger.warning("[AdinaSearch] PSE message: %s — trying SerpApi", cse_msg)
                elif leads:
                    logger.info("[AdinaSearch] PSE returned %d leads", len(leads))
                    return leads, query, "google_cse", None
                else:
                    logger.info("[AdinaSearch] PSE returned 0 results — falling back to SerpApi")
            except Exception as exc:
                logger.error("[AdinaSearch] PSE error: %s — trying SerpApi", exc)

        # ── 2. SerpApi fallback ──────────────────────────────────────────────
        if self._serp is not None:
            try:
                raw = self._serp.search_companies_google(industry=industry, limit=limit)
                leads = [self._normalize_serp(r, industry) for r in raw]
                leads = [l for l in leads if l]
                logger.info("[AdinaSearch] SerpApi returned %d leads", len(leads))
                return leads, query, "serpapi", None
            except Exception as exc:
                logger.error("[AdinaSearch] SerpApi error: %s", exc)

        # ── Both failed ──────────────────────────────────────────────────────
        return (
            [],
            query,
            "none",
            "Search temporarily unavailable. Use manual domain input with Hunter.io.",
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_query(
        industry: str,
        keywords: Optional[List[str]],
        company: Optional[str],
    ) -> str:
        parts = []
        if company:
            parts.append(f'"{company}"')
            parts.append(industry)
            parts.append("company")
        else:
            parts.append(industry)
            if keywords:
                parts.extend(keywords[:3])
            parts.append("companies OR startups")
        return " ".join(parts)

    @staticmethod
    def _normalize_serp(result: dict, industry: str) -> Optional[dict]:
        """Map a SerpAPIService result dict to the GoogleCSE lead shape."""
        name = result.get("name") or result.get("title")
        if not name:
            return None
        return {
            "company": name,
            "website": result.get("domain") or result.get("website_url"),
            "description": result.get("description"),
            "industry": industry,
            "source_url": result.get("website_url") or "",
        }
