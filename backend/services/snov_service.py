from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.settings import settings


class SnovService:
    """Snov.io API client for lead discovery and email finding."""

    BASE_URL = "https://api.snov.io"
    _access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        """Get OAuth access token using client credentials."""
        if self._access_token:
            return self._access_token

        client_id = settings.snov_client_id
        client_secret = settings.snov_client_secret
        print(
            f"[Snov.io] Client ID first 4 chars: {client_id[:4] if client_id else 'None'}, "
            f"length: {len(client_id) if client_id else 0}"
        )

        if not client_id or not client_secret:
            raise RuntimeError("Snov.io credentials not configured")

        response = requests.post(
            f"{self.BASE_URL}/v1/oauth/access_token",
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if not response.ok:
            self._raise_error(response)

        self._access_token = response.json().get("access_token")
        return self._access_token

    def search_by_industry(
        self,
        industry: str,
        country: Optional[str] = None,
        size: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Search for companies by industry using Snov.io Database Search."""
        params = {
            "access_token": self._get_access_token(),
            "industry": industry,
            "limit": limit,
        }
        if country:
            params["country"] = country
        if size:
            params["size"] = size

        response = requests.post(
            f"{self.BASE_URL}/v2/company-list",
            json=params,
        )
        if not response.ok:
            self._raise_error(response)

        data = response.json()
        results = []
        for company in data.get("data", []):
            results.append({
                "name": company.get("name"),
                "domain": company.get("domain"),
                "description": company.get("description"),
                "industry": company.get("industry") or industry,
                "size": company.get("size"),
                "location": company.get("country"),
                "source": "snov",
            })
        return results

    def get_company_profile(self, domain: str) -> Optional[dict]:
        """Get company profile by domain."""
        response = requests.post(
            f"{self.BASE_URL}/v1/get-company-profile-by-domain",
            json={
                "access_token": self._get_access_token(),
                "domain": self._clean_domain(domain),
            },
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
        }

    def get_emails_by_domain(self, domain: str) -> List[dict]:
        """Find contacts associated with a domain."""
        response = requests.post(
            f"{self.BASE_URL}/v1/get-domain-emails-with-info",
            json={
                "access_token": self._get_access_token(),
                "domain": self._clean_domain(domain),
            },
        )
        if not response.ok:
            self._raise_error(response)

        data = response.json()
        results = []
        for contact in data.get("emails", []):
            name_parts = [contact.get("first_name"), contact.get("last_name")]
            name = " ".join(p for p in name_parts if p) or None
            results.append({
                "name": name,
                "email": contact.get("email"),
                "title": contact.get("position"),
                "linkedin_url": contact.get("social", {}).get("linkedin"),
                "source": "snov",
            })
        return results

    def find_prospect_by_name(
        self, first_name: str, last_name: str, domain: str
    ) -> Optional[dict]:
        """Find a specific person's email by name and domain."""
        response = requests.post(
            f"{self.BASE_URL}/v1/get-emails-from-names",
            json={
                "access_token": self._get_access_token(),
                "firstName": first_name,
                "lastName": last_name,
                "domain": self._clean_domain(domain),
            },
        )
        if not response.ok:
            self._raise_error(response)

        data = response.json().get("data", {})
        emails = data.get("emails", [])
        if not emails:
            return None

        email_data = emails[0]
        return {
            "email": email_data.get("email"),
            "status": email_data.get("status"),
            "first_name": first_name,
            "last_name": last_name,
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
            error_data = response.json()
            detail = error_data.get("message") or error_data.get("error") or response.text
        except (ValueError, KeyError):
            detail = response.text
        raise RuntimeError(f"Snov.io API {response.status_code}: {detail}")
