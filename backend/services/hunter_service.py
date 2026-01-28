from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.settings import settings


class HunterService:
    BASE_URL = "https://api.hunter.io/v2"

    def _api_key(self):
        key = settings.hunter_api_key
        print(f"[Hunter] API key first 4 chars: {key[:4] if key else 'None'}, length: {len(key) if key else 0}")
        return key

    def find_email(self, domain: str, first_name: str, last_name: str) -> Optional[dict]:
        """Find a specific person's email using Hunter's Email Finder endpoint."""
        response = requests.get(
            f"{self.BASE_URL}/email-finder",
            params={
                "domain": self._clean_domain(domain),
                "first_name": first_name,
                "last_name": last_name,
                "api_key": self._api_key(),
            },
        )
        if not response.ok:
            self._raise_error(response)
        data = response.json().get("data", {})
        if not data or not data.get("email"):
            return None
        return {
            "email": data.get("email"),
            "score": data.get("score"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "position": data.get("position"),
            "company": data.get("company"),
            "linkedin_url": data.get("linkedin"),
        }

    def domain_search(self, domain: str) -> List[dict]:
        """Find all people associated with a domain using Hunter's Domain Search endpoint."""
        response = requests.get(
            f"{self.BASE_URL}/domain-search",
            params={
                "domain": self._clean_domain(domain),
                "api_key": self._api_key(),
            },
        )
        if not response.ok:
            self._raise_error(response)
        data = response.json().get("data", {})
        results = []
        for person in data.get("emails", []):
            name_parts = [person.get("first_name"), person.get("last_name")]
            name = " ".join(p for p in name_parts if p) or None
            results.append({
                "name": name,
                "email": person.get("value"),
                "job_title": person.get("position"),
                "company_name": data.get("organization"),
                "domain": data.get("domain"),
                "linkedin_url": person.get("linkedin"),
            })
        return results

    def discover_companies(
        self,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        size: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Hunter.io company discovery - NOT available on free tier.
        This endpoint requires Hunter.io Discover (paid plan).
        Returns empty list with a message for free tier users.
        """
        # Hunter.io /v2/companies/search is only available on paid plans
        # The free tier only supports: email-finder, email-verifier, domain-search
        raise RuntimeError(
            "Hunter.io discovery requires paid plan - using Snov.io instead"
        )

    def get_company_info(self, domain: str) -> Optional[dict]:
        """Get detailed company information by domain."""
        response = requests.get(
            f"{self.BASE_URL}/companies/{self._clean_domain(domain)}",
            params={"api_key": self._api_key()},
        )
        if not response.ok:
            if response.status_code == 404:
                return None
            self._raise_error(response)

        data = response.json().get("data", {})
        if not data:
            return None

        return {
            "name": data.get("name"),
            "domain": data.get("domain"),
            "description": data.get("description"),
            "industry": data.get("industry"),
            "size": data.get("size"),
            "location": data.get("country"),
            "website": f"https://{data.get('domain')}" if data.get("domain") else None,
        }

    @staticmethod
    def _clean_domain(domain: str) -> str:
        """Extract bare domain from a URL or domain string."""
        domain = domain.strip()
        if "://" in domain or domain.startswith("www."):
            parsed = urlparse(domain if "://" in domain else f"https://{domain}")
            domain = parsed.hostname or domain
        domain = domain.removeprefix("www.")
        return domain

    @staticmethod
    def _raise_error(response: requests.Response):
        try:
            detail = response.json().get("errors", [{}])[0].get("details", response.text)
        except (ValueError, IndexError, KeyError):
            detail = response.text
        raise RuntimeError(f"Hunter API {response.status_code}: {detail}")
