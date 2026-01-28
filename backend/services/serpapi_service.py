import logging
from typing import List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.settings import settings

logger = logging.getLogger(__name__)


class SerpAPIService:
    BASE_URL = "https://serpapi.com/search"

    def __init__(self) -> None:
        self.api_key = settings.serpapi_api_key
        self.session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def search_companies_google(
        self,
        industry: str,
        country: Optional[str] = None,
        city: Optional[str] = None,
        limit: int = 30,
    ) -> List[dict]:
        query = self._build_query(industry, country, city)
        params = {
            "engine": "google",
            "q": query,
            "num": min(limit, 50),
            "api_key": self.api_key,
        }
        data = self._request(params)

        results = []
        for item in data.get("organic_results", [])[:limit]:
            website_url = item.get("link")
            domain = self._extract_domain(website_url)
            results.append({
                "name": item.get("title") or "Unknown",
                "domain": domain,
                "website_url": website_url,
                "phone": None,
                "location": None,
                "description": item.get("snippet"),
                "source": "google",
            })
        return results

    def search_companies_maps(
        self,
        industry: str,
        country: Optional[str] = None,
        city: Optional[str] = None,
        limit: int = 30,
    ) -> List[dict]:
        query = self._build_query(industry, country, city)
        params = {
            "engine": "google_maps",
            "q": query,
            "type": "search",
            "api_key": self.api_key,
        }
        data = self._request(params)

        results = []
        for item in data.get("local_results", [])[:limit]:
            website_url = item.get("website")
            domain = self._extract_domain(website_url)
            results.append({
                "name": item.get("title") or "Unknown",
                "domain": domain,
                "website_url": website_url,
                "phone": item.get("phone"),
                "location": item.get("address") or item.get("location"),
                "description": item.get("description") or item.get("snippet"),
                "source": "google_maps",
            })
        return results

    def _request(self, params: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("SerpAPI API key not configured")

        safe_params = {k: ("***" if k == "api_key" else v) for k, v in params.items()}
        logger.info("[SerpAPI] Request params: %s", safe_params)
        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=20)
        except requests.RequestException as exc:
            logger.error("[SerpAPI] Request failed: %s", exc)
            raise RuntimeError("SerpAPI request failed") from exc

        if not response.ok:
            logger.error("[SerpAPI] HTTP %s: %s", response.status_code, response.text)
            raise RuntimeError(f"SerpAPI HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError:
            logger.error("[SerpAPI] Non-JSON response")
            raise RuntimeError("SerpAPI returned non-JSON response")

        if data.get("error"):
            logger.error("[SerpAPI] Error: %s", data.get("error"))
            raise RuntimeError(f"SerpAPI error: {data.get('error')}")

        return data

    @staticmethod
    def _build_query(industry: str, country: Optional[str], city: Optional[str]) -> str:
        parts = [industry]
        if city:
            parts.append(city)
        if country:
            parts.append(country)
        parts.append("company")
        return " ".join(p for p in parts if p)

    @staticmethod
    def _extract_domain(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.hostname
            if not host:
                return None
            return host.removeprefix("www.")
        except Exception:
            return None
