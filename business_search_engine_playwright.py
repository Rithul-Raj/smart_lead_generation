"""
Module 2: Business Search Engine (Playwright version)
----------------------------------------------------------------------------
Smart Lead Generation AI Model 

Setup (run these once in your VS Code terminal):
    pip install playwright
    playwright install chromium
"""

import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("business_search_engine_playwright")


@dataclass
class BusinessCandidate:
    """Structured output of Module 2 - handed off to Module 3 next."""
    company_name: str
    address: str = None
    location: str = None
    industry: str = None
    source: str = "google_maps_scrape"
    raw: dict = field(default_factory=dict)


class BusinessSearchEnginePlaywright:
    """
    Discovers candidate businesses by scraping Google Maps search results.
    No API key or billing required.
    """

    def __init__(self, headless: bool = True, scroll_pause: float = 1.5):
        """
        Args:
            headless: True = browser runs invisibly in the background.
                      Set False while you're debugging, so you can SEE
                      the browser working - very helpful for beginners.
            scroll_pause: seconds to wait after each scroll, so the page
                      has time to load new results (be polite to Google).
        """
        self.headless = headless
        self.scroll_pause = scroll_pause

    def search(self, num_leads: int, location: str, industry: str) -> List[BusinessCandidate]:
        """
        Main entry point - same input contract as the API version.

        Args:
            num_leads: how many leads you want
            location: e.g. "Bangalore, India"
            industry: e.g. "Information Technology"

        Returns:
            List[BusinessCandidate]
        """
        query = f"{industry} in {location}"
        logger.info(f"Searching Google Maps for: '{query}'")

        results: List[BusinessCandidate] = []
        seen_names = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()

            search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            page.goto(search_url, timeout=60000)
            page.wait_for_timeout(3000)  # let the page settle

            # The scrollable results panel on Google Maps
            feed_selector = 'div[role="feed"]'
            try:
                page.wait_for_selector(feed_selector, timeout=15000)
            except Exception:
                logger.error(
                    "Could not find the results panel. Google Maps may have "
                    "changed its layout, or the search returned nothing. "
                    "Try running with headless=False to see what's happening."
                )
                browser.close()
                return results

            # Scroll the results panel repeatedly to load more businesses
            max_scrolls = 15
            for scroll_num in range(max_scrolls):
                if len(results) >= num_leads:
                    break

                cards = page.query_selector_all(f'{feed_selector} > div > div[role="article"]')
                for card in cards:
                    name_el = card.query_selector('div[class*="fontHeadline"]')
                    name = name_el.inner_text().strip() if name_el else None
                    if not name or name in seen_names:
                        continue

                    address_el = card.query_selector('div[class*="fontBodyMedium"] span')
                    address = address_el.inner_text().strip() if address_el else None

                    seen_names.add(name)
                    results.append(
                        BusinessCandidate(
                            company_name=name,
                            address=address,
                            location=location,
                            industry=industry,
                        )
                    )
                    if len(results) >= num_leads:
                        break

                # scroll down inside the results panel
                page.evaluate(
                    f"""
                    const feed = document.querySelector('{feed_selector}');
                    if (feed) feed.scrollTop = feed.scrollHeight;
                    """
                )
                page.wait_for_timeout(int(self.scroll_pause * 1000))

            browser.close()

        logger.info(f"Search complete: {len(results)}/{num_leads} candidates found.")
        return results[:num_leads]


# ---------------- Standalone test run ----------------
if __name__ == "__main__":
    # CHANGE THESE THREE VALUES to search for whatever you want:
    engine = BusinessSearchEnginePlaywright(headless=False)  # False = watch it work
    candidates = engine.search(
        num_leads=10,
        location="Bangalore, India",
        industry="Information Technology",
    )

    print(f"\n{len(candidates)} candidates found:\n")
    for c in candidates:
        print({k: v for k, v in asdict(c).items() if k != "raw"})
