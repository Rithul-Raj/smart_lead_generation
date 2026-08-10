"""
Module 3: Company Data Extraction (ASYNC / OPTIMIZED version)
----------------------------------------------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

This version applies a round of performance/reliability improvements over
the first async version:

  1. Uses Module 2's saved `maps_url` to jump straight to a business's
     Google Maps page - no need to re-search for it.
  2. Uses wait_for_selector() instead of fixed wait_for_timeout() -
     continues as soon as the page is ready, instead of always waiting
     the full delay.
  3. Reuses ONE browser context per worker across many companies, instead
     of opening/closing a new context per company (less overhead).
  4. Retries a company once if extraction fails, before giving up.
  5. Lower page timeout (12s instead of 60s) so one stuck page can't stall
     the whole run.
  6. Extracts more fields while the page is already open: address,
     category, rating, review count (in addition to website + phone).
  7. Saves each company's result to CSV immediately after it's scraped,
     instead of waiting until the very end - so a crash midway doesn't
     lose everything already collected.
  8. After finding a company's website, opens that website too, and uses
     BeautifulSoup to read its page title + meta description as a first,
     lightweight look at the company (full contact/email digging is
     Module 4: Contact Discovery's job, not this module's).

Everything else - what the output looks like, how to call it - stays the
same shape as before, so Module 4 doesn't need to change anything.

Setup:
    pip install playwright beautifulsoup4
    playwright install chromium
"""

import json
import re
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Union, Optional
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from output_exporter import LIVE_BUFFER_CSV   # single source of truth for the live buffer path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("company_data_extraction_async")


@dataclass
class EnrichedCompany:
    """Structured output of Module 3 - handed off to Module 4 next."""
    company_name: str
    address: str = None
    location: str = None
    industry: str = None
    website: str = None
    phone: str = None
    category: str = None            # NEW - e.g. "Software company"
    rating: str = None              # NEW - e.g. "4.3"
    review_count: str = None        # NEW - e.g. "1,204"
    website_title: str = None       # NEW - <title> of the company's own website
    website_description: str = None # NEW - meta description of the company's own website
    company_size: str = None        # still intentionally empty - not reliably available
    source: str = "google_maps_detail_scrape_async"
    raw: dict = field(default_factory=dict)


class AsyncCompanyDataExtractor:
    """
    Takes companies discovered by Module 2 and enriches each one - faster
    and more resilient than the first async version.
    """

    def __init__(
        self,
        headless: bool = True,
        concurrency: int = 3,
        page_timeout_ms: int = 12000,
        retries: int = 1,
        output_csv_path: str = LIVE_BUFFER_CSV,  # output/current/current_leads_live.csv
    ):
        """
        Args:
            headless: True = browsers run invisibly.
            concurrency: how many workers (browser tabs) run at once.
            page_timeout_ms: max time to wait for a page to respond (12s).
            retries: how many times to retry a company before giving up.
            output_csv_path: where results are saved incrementally, one
                              row at a time, as they're scraped.
        """
        self.headless = headless
        self.concurrency = concurrency
        self.page_timeout_ms = page_timeout_ms
        self.retries = retries
        self.output_csv_path = output_csv_path
        self._csv_lock = asyncio.Lock()  # prevents two workers writing at once

    def enrich(self, companies: Union[List[dict], str]) -> List[EnrichedCompany]:
        """Public entry point - wraps the async logic so you can call it normally."""
        return asyncio.run(self._enrich_async(companies))

    # ---------------- internal async logic ----------------

    async def _enrich_async(self, companies: Union[List[dict], str]) -> List[EnrichedCompany]:
        from output_exporter import append_row_to_csv  # local import avoids circular import

        companies = self._load_input(companies)
        logger.info(
            f"Enriching {len(companies)} companies "
            f"({self.concurrency} workers, saving progress to {self.output_csv_path})"
        )

        # A queue holds (index, company) pairs. Each worker pulls the next
        # available company whenever it's free - this naturally balances
        # work across workers, unlike splitting the list evenly upfront.
        queue: asyncio.Queue = asyncio.Queue()
        for i, company in enumerate(companies):
            queue.put_nowait((i, company))

        results: List[Optional[EnrichedCompany]] = [None] * len(companies)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            async def worker(worker_id: int):
                # ONE context per worker, reused for every company that
                # worker processes - this is the "reuse browser contexts"
                # optimization. Much less overhead than a fresh context
                # (and fresh cookies/cache setup) per company.
                context = await browser.new_context()
                page = await context.new_page()
                try:
                    while True:
                        try:
                            index, company = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                        enriched = await self._extract_with_retry(context, page, company)
                        results[index] = enriched

                        async with self._csv_lock:
                            append_row_to_csv(asdict(enriched), self.output_csv_path)

                        queue.task_done()
                finally:
                    await context.close()

            workers = [asyncio.create_task(worker(w)) for w in range(self.concurrency)]
            await asyncio.gather(*workers)
            await browser.close()

        logger.info(f"Done. Enriched {len(results)} companies.")
        return results

    def _load_input(self, companies: Union[List[dict], str]) -> List[dict]:
        if isinstance(companies, str):
            with open(companies, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("leads", data)
        return companies

    async def _extract_with_retry(self, context, page, company: dict) -> EnrichedCompany:
        """Tries to extract a company's data, retrying once on failure."""
        name = company.get("company_name")
        last_error = None

        for attempt in range(self.retries + 1):
            try:
                return await self._extract_one(context, page, company)
            except Exception as e:
                last_error = e
                if attempt < self.retries:
                    logger.warning(f"Retrying '{name}' after error: {e}")
                    await asyncio.sleep(1)

        logger.warning(f"Giving up on '{name}' after {self.retries + 1} attempts: {last_error}")
        return EnrichedCompany(
            company_name=name,
            address=company.get("address"),
            location=company.get("location"),
            industry=company.get("industry"),
        )

    async def _extract_one(self, context, page, company: dict) -> EnrichedCompany:
        name = company.get("company_name")
        maps_url = company.get("maps_url")

        if maps_url:
            # Fast path: go straight to the business's own Maps page.
            await page.goto(maps_url, timeout=self.page_timeout_ms)
        else:
            # Fallback path for companies with no saved URL (e.g. manually
            # typed test data) - same behaviour as the earlier version.
            address = company.get("address") or ""
            query = f"{name} {address}".strip().replace(" ", "+")
            await page.goto(
                f"https://www.google.com/maps/search/{query}", timeout=self.page_timeout_ms
            )
            first_card = await page.query_selector('div[role="feed"] > div > div[role="article"]')
            if first_card:
                await first_card.click()

        # SMART WAIT: instead of a fixed 3-second delay, wait specifically
        # for the business name heading (h1) to appear - that's our signal
        # the detail panel has actually finished loading. Continues the
        # moment it's ready, instead of always waiting the full time.
        await page.wait_for_selector("h1", timeout=self.page_timeout_ms)

        website = await self._get_text_by_data_item(page, "authority")
        phone = await self._get_text_by_data_item(page, "phone")
        address_full = await self._get_text_by_data_item(page, "address")
        category, rating, review_count = await self._get_category_and_rating(page)

        website_title, website_description = await self._extract_website_details(context, website)

        return EnrichedCompany(
            company_name=name,
            address=address_full or company.get("address"),
            location=company.get("location"),
            industry=company.get("industry"),
            website=website,
            phone=phone,
            category=category,
            rating=rating,
            review_count=review_count,
            website_title=website_title,
            website_description=website_description,
        )

    async def _get_text_by_data_item(self, page, prefix: str):
        """Same technique as before - reads text from an element identified
        by its data-item-id attribute (see Module 3 v1 for full explanation)."""
        el = await page.query_selector(f'[data-item-id^="{prefix}"]')
        if not el:
            return None
        text_el = await el.query_selector('div[class*="fontBodyMedium"]')
        if text_el:
            return (await text_el.inner_text()).strip()
        return (await el.inner_text()).strip()

    async def _get_category_and_rating(self, page):
        """
        Reads the business category, star rating, and review count from the
        Google Maps detail panel.

        Google Maps changes its HTML frequently, so we use multiple fallback
        strategies for each field rather than relying on a single selector.
        """
        category     = None
        rating       = None
        review_count = None

        # ── Category ─────────────────────────────────────────────────────────
        category_el = await page.query_selector('button[jsaction*="category"]')
        if category_el:
            category = (await category_el.inner_text()).strip()

        # ── Rating ───────────────────────────────────────────────────────────
        # aria-label looks like "4.2 stars" — validate it's actually a number
        # to avoid matching elements that just say "stars" with no number.
        rating_el = await page.query_selector('span[aria-label*="stars"]')
        if rating_el:
            label = await rating_el.get_attribute("aria-label") or ""
            match = re.match(r'^(\d+\.?\d*)\s+stars?', label.strip(), re.I)
            if match:
                rating = match.group(1)

        # ── Review count — 3-tier fallback ───────────────────────────────────
        #
        # Tier 1: span[aria-label*="review"] — the classic selector.
        #   Google Maps wraps the count in a span like:
        #   <span aria-label="2,014 reviews">
        review_els = await page.query_selector_all('span[aria-label*="review"]')
        for el in review_els:
            label = await el.get_attribute("aria-label") or ""
            m = re.search(r'([\d,]+)\s+review', label, re.I)
            if m:
                review_count = m.group(1)   # keep commas e.g. "1,234"
                break

        # Tier 2: button[aria-label*="review"] — Google sometimes wraps it
        #   in a clickable button instead of a plain span.
        if not review_count:
            btn_els = await page.query_selector_all('button[aria-label*="review"]')
            for el in btn_els:
                label = await el.get_attribute("aria-label") or ""
                m = re.search(r'([\d,]+)\s+review', label, re.I)
                if m:
                    review_count = m.group(1)
                    break

        # Tier 3: scan the full visible page text for the pattern
        #   "4.3(1,234)" or "4.3 (1,234)" — the count sits in parentheses
        #   right after the star rating on the Maps panel.
        if not review_count:
            try:
                page_text = await page.inner_text("body")
                m = re.search(r'\d+\.?\d*\s*\(([\d,]+)\)', page_text)
                if m:
                    review_count = m.group(1)
            except Exception:
                pass

        return category, rating, review_count

    async def _extract_website_details(self, context, website_url: Optional[str]):
        """
        Opens the company's OWN website (not Google Maps) and uses
        BeautifulSoup to read basic info off it: the page title and meta
        description. This is a light first look at the company - full
        contact/email extraction belongs to Module 4.

        Uses the SAME browser context as the caller (context reuse),
        just a new tab within it.
        """
        if not website_url:
            return None, None

        # Google Maps shows website as plain text like "bit-bangalore.edu.in"
        # (no https://), which is NOT a valid URL to navigate to directly.
        # Add the scheme if it's missing.
        if not website_url.startswith("http://") and not website_url.startswith("https://"):
            website_url = f"https://{website_url}"

        try:
            site_page = await context.new_page()
            await site_page.goto(website_url, timeout=self.page_timeout_ms)
            html = await site_page.content()  # the fully rendered HTML
            await site_page.close()

            soup = BeautifulSoup(html, "html.parser")  # BeautifulSoup parses it

            title = soup.title.string.strip() if soup.title and soup.title.string else None

            description = None
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag and meta_tag.get("content"):
                description = meta_tag["content"].strip()

            return title, description

        except Exception as e:
            logger.warning(f"Could not read website '{website_url}': {e}")
            return None, None


# ── How to run this module ────────────────────────────────────────────────────
#
# This module is now called from the central pipeline entry point:
#
#     python main.py
#
# main.py opens the GUI input form so you can fill in your search parameters
# (number of leads, location, industry) without editing any code.
#
# Enrichment progress is saved incrementally to:
#     output/current_leads_live.csv
# and the final result is written to:
#     output/current_leads.csv + output/current_leads.json
# by the pipeline in main.py.
#
# If you need to test this module in isolation, you can still do:
#
#     from company_data_extraction_async import AsyncCompanyDataExtractor
#     extractor = AsyncCompanyDataExtractor(headless=True, concurrency=3)
#     enriched  = extractor.enrich("output/current_leads.json")
#     print(enriched)
#
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline with the GUI input form.")
    print("See the comment block above for how to test this module in isolation.")