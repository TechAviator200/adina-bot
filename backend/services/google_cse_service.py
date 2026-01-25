"""
Google Custom Search Engine (CSE) service for lead discovery.

Uses the Google CSE JSON API to search for companies based on
industry, company name, and topic keywords.
"""
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.settings import settings

logger = logging.getLogger(__name__)


class GoogleCSEService:
    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        self.api_key = settings.google_cse_api_key
        self.cx = settings.google_cse_cx

    def is_configured(self) -> bool:
        """Check if Google CSE is properly configured."""
        return bool(self.api_key and self.cx)

    # Maintenance message when search is unavailable
    MAINTENANCE_MESSAGE = "Search Engine currently in maintenance, please use manual domain input."

    def search(self, query: str, num_results: int = 10) -> tuple[List[dict], Optional[str]]:
        """
        Execute a Google CSE search and return raw results.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10 per request)

        Returns:
            Tuple of (results list, error message or None)
            - On success: (items, None)
            - On 403/maintenance: ([], maintenance message)
            - On other errors: raises RuntimeError
        """
        if not self.is_configured():
            logger.warning("[GoogleCSE] Not configured, returning maintenance message")
            return [], self.MAINTENANCE_MESSAGE

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(num_results, 10),  # CSE max is 10 per request
        }

        # Log request details (redact API key)
        debug_params = {**params, "key": f"{self.api_key[:8]}...REDACTED"}
        logger.info(f"[GoogleCSE] Request URL: {self.BASE_URL}")
        logger.info(f"[GoogleCSE] Request params: {debug_params}")

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30,
            )

            # Handle 403 gracefully - return maintenance message
            if response.status_code == 403:
                logger.warning(f"[GoogleCSE] 403 Forbidden - returning maintenance message")
                return [], self.MAINTENANCE_MESSAGE

            if not response.ok:
                self._raise_error(response)

            data = response.json()
            return data.get("items", []), None

        except requests.RequestException as e:
            logger.error(f"[GoogleCSE] Request failed: {e}")
            return [], self.MAINTENANCE_MESSAGE

    def discover_leads(
        self,
        industry: str,
        keywords: Optional[List[str]] = None,
        company: Optional[str] = None,
    ) -> tuple[List[dict], Optional[str]]:
        """
        Discover potential leads using smart search queries.

        Builds contextual queries combining industry, keywords, and optional company name.

        Args:
            industry: Target industry (e.g., "healthcare", "fintech")
            keywords: Topic keywords (e.g., ["AI", "automation"])
            company: Optional specific company to search for

        Returns:
            Tuple of (leads list, error message or None)
            - leads: List of normalized lead dictionaries
            - message: Maintenance message if search unavailable, None otherwise
        """
        # Build smart search query
        query = self._build_query(industry, keywords, company)
        logger.info(f"[GoogleCSE] Search query: {query}")

        # Execute search
        raw_results, message = self.search(query)

        # If maintenance mode, return early with message
        if message:
            return [], message

        # Parse results into normalized leads
        leads = []
        for item in raw_results:
            lead = self._parse_result(item, industry)
            if lead:
                leads.append(lead)

        return leads, None

    def _build_query(
        self,
        industry: str,
        keywords: Optional[List[str]] = None,
        company: Optional[str] = None,
    ) -> str:
        """
        Build a smart search query from inputs.

        Strategy:
        - If company provided: "{company} {industry} company"
        - Otherwise: "{industry} {keywords} companies startups"
        """
        parts = []

        if company:
            # Searching for specific company
            parts.append(f'"{company}"')
            parts.append(industry)
            parts.append("company")
        else:
            # General industry search
            parts.append(industry)
            if keywords:
                parts.extend(keywords[:3])  # Limit to 3 keywords
            parts.append("companies OR startups")

        return " ".join(parts)

    def _parse_result(self, item: dict, industry: str) -> Optional[dict]:
        """
        Parse a Google CSE result item into a normalized lead.

        Extracts company name from title, website from URL, and description from snippet.
        """
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")

        if not link:
            return None

        # Extract domain/website
        try:
            parsed = urlparse(link)
            website = parsed.netloc.removeprefix("www.")
        except Exception:
            website = None

        # Extract company name from title
        # Common patterns: "Company Name - ...", "Company Name | ...", "Company Name: ..."
        company_name = self._extract_company_name(title, website)

        if not company_name:
            return None

        return {
            "company": company_name,
            "website": website,
            "description": snippet.strip() if snippet else None,
            "industry": industry,
            "source_url": link,
            "title": title,
        }

    def _extract_company_name(self, title: str, website: Optional[str]) -> Optional[str]:
        """
        Extract company name from page title.

        Strategies:
        1. Split on common separators (-, |, :, \u2013, \u2014)
        2. Take the first meaningful segment
        3. Fall back to domain name if title is generic
        """
        if not title:
            return self._company_from_domain(website) if website else None

        # Split on common title separators
        separators = r"[\|\-\:\u2013\u2014]"
        parts = re.split(separators, title)

        if parts:
            # Take first part, clean it up
            name = parts[0].strip()

            # Skip if it looks like a generic page title
            generic_patterns = [
                r"^home\s*$",
                r"^about\s*(us)?\s*$",
                r"^contact\s*(us)?\s*$",
                r"^welcome\s*$",
                r"^official\s*site\s*$",
            ]
            for pattern in generic_patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    # Try second part or fall back to domain
                    if len(parts) > 1:
                        name = parts[1].strip()
                    else:
                        return self._company_from_domain(website) if website else None
                    break

            # Truncate if too long (probably not a company name)
            if len(name) > 80:
                name = name[:80].rsplit(" ", 1)[0] + "..."

            return name if name else None

        return self._company_from_domain(website) if website else None

    def _company_from_domain(self, domain: str) -> Optional[str]:
        """Extract a rough company name from domain."""
        if not domain:
            return None
        # Remove TLD and common prefixes
        name = domain.split(".")[0]
        name = re.sub(r"^(www|app|api|blog)\-?", "", name)
        return name.title() if name else None

    @staticmethod
    def _raise_error(response: requests.Response):
        """Raise a descriptive error from API response."""
        try:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", response.text)
        except (ValueError, KeyError):
            error_msg = response.text
        raise RuntimeError(f"Google CSE API {response.status_code}: {error_msg}")
