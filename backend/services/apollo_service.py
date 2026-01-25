import time
from typing import List

import requests

from app.settings import settings


class ApolloService:
    BASE_URL = "https://api.apollo.io/v1/mixed_people/search"
    REQUEST_DELAY = 1.0  # seconds between paginated requests

    def search(self, titles: List[str], locations: List[str], max_pages: int = 3, per_page: int = 25) -> List[dict]:
        results = []

        for page in range(1, max_pages + 1):
            if page > 1:
                time.sleep(self.REQUEST_DELAY)

            response = requests.post(
                self.BASE_URL,
                headers={"x-api-key": settings.apollo_api_key},
                json={
                    "person_titles": titles,
                    "person_locations": locations,
                    "page": page,
                    "per_page": per_page,
                },
            )
            if not response.ok:
                try:
                    detail = response.json().get("error", response.text)
                except ValueError:
                    detail = response.text
                raise RuntimeError(f"Apollo API {response.status_code}: {detail}")
            data = response.json()

            people = data.get("people", [])
            if not people:
                break

            for person in people:
                results.append({
                    "name": person.get("name"),
                    "job_title": person.get("title"),
                    "company_name": person.get("organization", {}).get("name") if person.get("organization") else None,
                    "linkedin_url": person.get("linkedin_url"),
                    "apollo_id": person.get("id"),
                })

            total_pages = data.get("pagination", {}).get("total_pages", 1)
            if page >= total_pages:
                break

        return results
