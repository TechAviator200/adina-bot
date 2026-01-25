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
