"""
Module 2: Business Search Engine
---------------------------------
Smart Lead Generation AI Model
"""

import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("business_search_engine")


@dataclass
class BusinessCandidate:
    """Structured output of Module 2. This is what gets handed to Module 3."""
    company_name: str
    address: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None          # usually None here; filled in by Module 3
    phone: Optional[str] = None            # usually None here; filled in by Module 3
    place_id: Optional[str] = None         # key used to fetch full details in Module 3
    source: str = "google_places"
    raw: dict = field(default_factory=dict)  # original API payload, kept for debugging


class BusinessSearchEngine:
    """
    Discovers candidate businesses for a given (leads, location, industry)
    request. Handles query construction, pagination, and de-duplication.
    """

    TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    MAX_RESULTS_PER_QUERY = 60  # Google Places hard cap (3 pages x 20)

    def __init__(self, api_key: Optional[str] = None, request_delay: float = 2.1):
        """
        Args:
            api_key: Google Places API key. Falls back to env var if not passed.
            request_delay: seconds to wait before using a next_page_token
                (Google requires a short delay before a token becomes valid).
        """
        self.api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY")
        self.request_delay = request_delay

        if not self.api_key:
            logger.warning(
                "GOOGLE_PLACES_API_KEY not found. Running in MOCK mode — "
                "returning sample data instead of live search results."
            )

    # ---------------- Public API ----------------

    def search(self, num_leads: int, location: str, industry: str) -> List[BusinessCandidate]:
        """
        Main entry point. Matches the input contract from Module 1.

        Args:
            num_leads: number of leads requested by the user
            location: city, state, country, or region (e.g. "Bangalore, India")
            industry: business sector (e.g. "Information Technology")

        Returns:
            List[BusinessCandidate], length <= num_leads.
            May return fewer if the source runs out of unique results.
        """
        self._validate_inputs(num_leads, location, industry)
        logger.info(f"Searching: {num_leads} leads | industry='{industry}' | location='{location}'")

        if not self.api_key:
            return self._mock_search(num_leads, location, industry)

        if num_leads > self.MAX_RESULTS_PER_QUERY:
            logger.warning(
                f"Requested {num_leads} leads exceeds single-query cap "
                f"({self.MAX_RESULTS_PER_QUERY}). Consider query-splitting "
                f"by sub-location/sub-industry to get more (see NOTES)."
            )

        query = self._build_query(location, industry)
        results: List[BusinessCandidate] = []
        seen_keys = set()
        next_page_token = None

        while len(results) < num_leads:
            params = {"query": query, "key": self.api_key}
            if next_page_token:
                params["pagetoken"] = next_page_token
                time.sleep(self.request_delay)

            try:
                response = requests.get(self.TEXT_SEARCH_URL, params=params, timeout=15)
                data = response.json()
            except requests.RequestException as e:
                logger.error(f"Request to Google Places API failed: {e}")
                break

            status = data.get("status")
            if status == "ZERO_RESULTS":
                logger.info("No results returned for this query.")
                break
            if status != "OK":
                logger.error(f"Google Places API error: {status} - {data.get('error_message')}")
                break

            for place in data.get("results", []):
                candidate = self._parse_place(place, location, industry)
                dedup_key = self._dedup_key(candidate)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                results.append(candidate)
                if len(results) >= num_leads:
                    break

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break  # source exhausted

        logger.info(f"Search complete: {len(results)}/{num_leads} candidates found.")
        return results[:num_leads]

    # ---------------- Internal helpers ----------------

    def _validate_inputs(self, num_leads: int, location: str, industry: str) -> None:
        if not isinstance(num_leads, int) or num_leads <= 0:
            raise ValueError("num_leads must be a positive integer")
        if not location or not location.strip():
            raise ValueError("location cannot be empty")
        if not industry or not industry.strip():
            raise ValueError("industry cannot be empty")

    def _build_query(self, location: str, industry: str) -> str:
        """Builds a natural-language query for Places Text Search."""
        return f"{industry} companies in {location}"

    def _parse_place(self, place: dict, location: str, industry: str) -> BusinessCandidate:
        return BusinessCandidate(
            company_name=place.get("name", "Unknown"),
            address=place.get("formatted_address"),
            location=location,
            industry=industry,
            place_id=place.get("place_id"),
            raw=place,
        )

    def _dedup_key(self, candidate: BusinessCandidate) -> str:
        """
        Source-level dedup only. Full cross-run/CRM dedup is Module 8's job.
        Prefer place_id (stable, unique); fall back to normalized name+address.
        """
        if candidate.place_id:
            return candidate.place_id
        name = (candidate.company_name or "").strip().lower()
        addr = (candidate.address or "").strip().lower()
        return f"{name}|{addr}"

    def _mock_search(self, num_leads: int, location: str, industry: str) -> List[BusinessCandidate]:
        """Sample data generator so downstream modules can be built/tested without an API key."""
        logger.info("MOCK mode active — generating sample candidates.")
        mock_data = []
        for i in range(1, num_leads + 1):
            mock_data.append(
                BusinessCandidate(
                    company_name=f"{industry.title()} Company {i}",
                    address=f"{i} Sample Street, {location}",
                    location=location,
                    industry=industry,
                    website=f"https://www.company{i}.example.com",
                    place_id=f"MOCK_PLACE_ID_{i}",
                    source="mock",
                )
            )
        return mock_data


# ---------------- Standalone test run ----------------
if __name__ == "__main__":
    engine = BusinessSearchEngine()
    candidates = engine.search(num_leads=10, location="Bangalore, India", industry="Information Technology")

    print(f"\n{len(candidates)} candidates found:\n")
    for c in candidates:
        print({k: v for k, v in asdict(c).items() if k != "raw"})


# ---------------- NOTES for teammates / future you ----------------
#
# 1. Getting a real API key:
#    - Google Cloud Console -> enable "Places API" -> create API key.
#    - Free tier / trial credit is usually enough for dev/testing.
#
# 2. Alternative data sources (drop-in replacements for _build_query/search):
#    - Bing Maps / Azure Maps Search API
#    - Yelp Fusion API (great for local/small businesses)
#    - SerpApi (wraps Google Search/Maps results, no Google Cloud billing needed)
#    - LinkedIn Company Search (requires partner API access, harder to get)
#
# 3. Getting MORE than 60 results for one request:
#    Google Places Text Search caps at 60 results per query. To reach larger
#    num_leads values, split the search into sub-queries, e.g.:
#      - by sub-locality ("IT companies in Koramangala, Bangalore",
#        "IT companies in Whitefield, Bangalore", ...)
#      - by industry sub-category if the user's industry is broad
#    Then merge + dedup across sub-query results before returning.
#
# 4. Output contract for Module 3 (Company Data Extraction):
#    Module 3 should accept List[BusinessCandidate] and use `place_id` to
#    call the Places "Place Details" endpoint (or scrape `website` once
#    Module 3 resolves it) to fetch: website, phone, company size signals,
#    etc. Keeping M2 -> M3 handoff to just (name, address, place_id) keeps
#    Module 2 fast and cheap to run.
