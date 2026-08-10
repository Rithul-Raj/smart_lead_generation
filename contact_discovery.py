"""
Module 4: Contact Discovery
-----------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Module 3 gave us each company's website URL plus basic info.
This module goes DEEPER into those websites to discover actual
contact-level data:

  - Email addresses  (regex scan of every page visited)
  - Phone numbers    (regex scan - adds to what Module 3 already found)
  - LinkedIn company page URL
  - Social media profile URLs (Twitter/X, Facebook, Instagram, YouTube)
  - The URL of the company's dedicated contact page (if one exists)

Crawling strategy per company
-------------------------------
  1. Visit the company homepage.
  2. Find and visit up to N "contact-like" pages by checking common
     URL patterns (/contact, /contact-us, /about, /team, /people, etc.)
     AND by scanning the homepage's own links for matching anchor text.
  3. On every page visited: run regex to extract emails + phone numbers;
     scan <a href> tags for social media domain matches.
  4. Deduplicate everything and rank emails
     (domain-matched personal/role addresses ranked above generic ones).
  5. Package results into ContactEnrichedCompany and return.

No new packages needed
------------------------
Uses playwright + beautifulsoup4 (already installed for Modules 2 and 3).

Setup reminder:
    pip install playwright beautifulsoup4
    playwright install chromium
"""

import re
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, BrowserContext
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("contact_discovery")


# ── regex patterns ────────────────────────────────────────────────────────────

# Matches most valid email formats found on web pages
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Matches Indian and international phone number formats commonly seen on websites
# Covers: +91-XXXXXXXXXX, 0XXXXXXXXXX, XXX-XXX-XXXX, (XXX) XXX-XXXX, etc.
_PHONE_RE = re.compile(
    r"""
    (?:
        (?:\+?\d{1,3}[\s\-.])?          # optional country code
        (?:\(?\d{2,4}\)?[\s\-.])?       # optional area code
        \d{3,5}                          # first block
        [\s\-.]                          # separator
        \d{3,5}                          # second block
        (?:[\s\-.]\d{2,5})?             # optional third block
    )
    """,
    re.VERBOSE,
)

# Social media domains to look for in <a href> tags
_SOCIAL_PATTERNS: Dict[str, re.Pattern] = {
    "linkedin_url":   re.compile(r"linkedin\.com/(?:company|in)/", re.I),
    "twitter_url":    re.compile(r"(?:twitter|x)\.com/", re.I),
    "facebook_url":   re.compile(r"facebook\.com/", re.I),
    "instagram_url":  re.compile(r"instagram\.com/", re.I),
    "youtube_url":    re.compile(r"youtube\.com/(?:c/|channel/|@)?", re.I),
}

# Email addresses to skip entirely (automated / bounce addresses)
_SKIP_EMAILS = re.compile(
    r"^(?:noreply|no-reply|donotreply|do-not-reply|bounce|mailer-daemon|"
    r"postmaster|webmaster|unsubscribe)@",
    re.I,
)

# Lower-priority generic role addresses (kept, but ranked after personal ones)
_GENERIC_EMAILS = re.compile(
    r"^(?:info|contact|hello|hi|enquiry|enquiries|sales|support|help|"
    r"admin|hr|careers|jobs|feedback|service|office|team|marketing)@",
    re.I,
)

# Common contact-page URL path segments to try
_CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/contactus",
    "/contacts",
    "/reach-us",
    "/reach_us",
    "/get-in-touch",
    "/getintouch",
    "/about",
    "/about-us",
    "/aboutus",
    "/team",
    "/our-team",
    "/people",
    "/meet-the-team",
]

# Anchor-text keywords that suggest a link leads to a contact-like page
_CONTACT_ANCHOR_WORDS = re.compile(
    r"\b(?:contact|reach|get.in.touch|about|team|people|connect)\b",
    re.I,
)


# ── output dataclass ──────────────────────────────────────────────────────────

@dataclass
class ContactEnrichedCompany:
    """
    Everything from Module 3's EnrichedCompany PLUS the contact fields
    discovered by this module. This is the object passed to Module 5+.
    """
    # ── fields carried over from Module 3 ────────────────────────────────
    company_name:        str
    address:             Optional[str] = None
    location:            Optional[str] = None
    industry:            Optional[str] = None
    website:             Optional[str] = None
    phone:               Optional[str] = None       # from Google Maps (Module 3)
    category:            Optional[str] = None
    rating:              Optional[str] = None
    review_count:        Optional[str] = None
    website_title:       Optional[str] = None
    website_description: Optional[str] = None
    company_size:        Optional[str] = None
    source:              str = "google_maps_detail_scrape_async"

    # ── NEW fields added by Module 4 ─────────────────────────────────────
    emails:              List[str] = field(default_factory=list)
    primary_email:       Optional[str] = None       # best single email to use
    phones_discovered:   List[str] = field(default_factory=list)  # extra phones from website
    linkedin_url:        Optional[str] = None
    twitter_url:         Optional[str] = None
    facebook_url:        Optional[str] = None
    instagram_url:       Optional[str] = None
    youtube_url:         Optional[str] = None
    contact_page_url:    Optional[str] = None       # URL of the /contact page if found
    pages_crawled:       int = 0                    # how many pages were visited

    # internal - not exported
    raw: dict = field(default_factory=dict)


# ── main class ────────────────────────────────────────────────────────────────

class ContactDiscovery:
    """
    Takes a list of enriched company dicts (output of Module 3) and
    discovers contact-level information from each company's website.
    """

    def __init__(
        self,
        headless: bool = True,
        concurrency: int = 3,
        page_timeout_ms: int = 15000,
        max_pages_per_company: int = 4,
    ):
        """
        Args:
            headless            : run browsers invisibly (True) or visibly (False).
            concurrency         : number of parallel workers (browser tabs).
            page_timeout_ms     : max milliseconds to wait for any single page load.
            max_pages_per_company: how many pages to crawl per company at most
                                   (homepage + up to N-1 contact/about pages).
        """
        self.headless             = headless
        self.concurrency          = concurrency
        self.page_timeout_ms      = page_timeout_ms
        self.max_pages_per_company = max_pages_per_company

    # ── public entry point ────────────────────────────────────────────────────

    def discover(
        self,
        companies: List[Dict[str, Any]],
    ) -> List[ContactEnrichedCompany]:
        """
        Public synchronous entry point — wraps the async logic.

        Args:
            companies: list of dicts (Module 3 output).
                       Each dict must have at least 'company_name'.
                       'website' is used for crawling; companies without
                       a website get empty contact fields.

        Returns:
            List[ContactEnrichedCompany] — same order as input.
        """
        return asyncio.run(self._discover_async(companies))

    # ── internal async orchestration ─────────────────────────────────────────

    async def _discover_async(
        self,
        companies: List[Dict[str, Any]],
    ) -> List[ContactEnrichedCompany]:

        logger.info(
            f"Contact Discovery: processing {len(companies)} companies "
            f"({self.concurrency} workers, timeout={self.page_timeout_ms}ms)"
        )

        queue: asyncio.Queue = asyncio.Queue()
        for i, company in enumerate(companies):
            queue.put_nowait((i, company))

        results: List[Optional[ContactEnrichedCompany]] = [None] * len(companies)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            async def worker(worker_id: int):
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                try:
                    while True:
                        try:
                            index, company = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                        result = await self._discover_one(context, page, company)
                        results[index] = result
                        queue.task_done()
                finally:
                    await context.close()

            workers = [
                asyncio.create_task(worker(w))
                for w in range(self.concurrency)
            ]
            await asyncio.gather(*workers)
            await browser.close()

        found = sum(1 for r in results if r and (r.emails or r.linkedin_url))
        logger.info(
            f"Contact Discovery complete: "
            f"{found}/{len(companies)} companies had contact data found."
        )
        return results

    # ── per-company crawl ─────────────────────────────────────────────────────

    async def _discover_one(
        self,
        context: BrowserContext,
        page: Page,
        company: Dict[str, Any],
    ) -> ContactEnrichedCompany:
        """
        Build a ContactEnrichedCompany for a single company.
        Gracefully returns an empty-contact result if the website is
        unreachable or blocks scraping.
        """
        name    = company.get("company_name", "Unknown")
        website = company.get("website")

        # Build base object from Module 3 fields — copy all known fields
        result = ContactEnrichedCompany(
            company_name        = name,
            address             = company.get("address"),
            location            = company.get("location"),
            industry            = company.get("industry"),
            website             = website,
            phone               = company.get("phone"),
            category            = company.get("category"),
            rating              = company.get("rating"),
            review_count        = company.get("review_count"),
            website_title       = company.get("website_title"),
            website_description = company.get("website_description"),
            company_size        = company.get("company_size"),
            source              = company.get("source", "google_maps_detail_scrape_async"),
        )

        if not website:
            logger.info(f"  [{name}] No website — skipping contact crawl.")
            return result

        # Normalise URL (Google Maps often gives bare domain like 'vitvara.in')
        base_url = self._normalise_url(website)

        # Collect all scraped data across pages
        all_emails:    List[str] = []
        all_phones:    List[str] = []
        social_links:  Dict[str, Optional[str]] = {k: None for k in _SOCIAL_PATTERNS}
        contact_url:   Optional[str] = None
        pages_crawled: int = 0

        # ── Page 1: homepage ──────────────────────────────────────────────
        homepage_html, homepage_links = await self._fetch_page(page, base_url)
        if homepage_html:
            pages_crawled += 1
            emails, phones = self._extract_contacts(homepage_html)
            all_emails.extend(emails)
            all_phones.extend(phones)
            self._extract_social(homepage_html, social_links)

            # Find contact/about page URLs from the homepage links
            candidate_urls = self._find_contact_page_urls(
                base_url, homepage_links
            )
        else:
            logger.warning(f"  [{name}] Could not load homepage: {base_url}")
            result.pages_crawled = 0
            return result

        # ── Pages 2-N: contact/about pages ───────────────────────────────
        visited = {base_url}
        pages_to_visit = candidate_urls[: self.max_pages_per_company - 1]

        for url in pages_to_visit:
            if url in visited:
                continue
            visited.add(url)

            html, _ = await self._fetch_page(page, url)
            if not html:
                continue

            pages_crawled += 1
            emails, phones = self._extract_contacts(html)
            all_emails.extend(emails)
            all_phones.extend(phones)
            self._extract_social(html, social_links)

            # Record the first contact page we successfully loaded
            if contact_url is None and self._is_contact_url(url):
                contact_url = url

        # ── Assemble result ───────────────────────────────────────────────
        ranked_emails      = self._rank_emails(all_emails, base_url)
        cleaned_phones     = self._clean_phones(all_phones, company.get("phone"))

        result.emails            = ranked_emails
        result.primary_email     = ranked_emails[0] if ranked_emails else None
        result.phones_discovered = cleaned_phones
        result.linkedin_url      = social_links.get("linkedin_url")
        result.twitter_url       = social_links.get("twitter_url")
        result.facebook_url      = social_links.get("facebook_url")
        result.instagram_url     = social_links.get("instagram_url")
        result.youtube_url       = social_links.get("youtube_url")
        result.contact_page_url  = contact_url
        result.pages_crawled     = pages_crawled

        logger.info(
            f"  [{name}]  emails={len(ranked_emails)}  "
            f"phones={len(cleaned_phones)}  "
            f"linkedin={'yes' if result.linkedin_url else 'no'}  "
            f"pages={pages_crawled}"
        )
        return result

    # ── page fetcher ──────────────────────────────────────────────────────────

    async def _fetch_page(
        self,
        page: Page,
        url: str,
    ):
        """
        Navigate to a URL and return (html_text, list_of_hrefs).
        Returns (None, []) on any error.
        """
        try:
            await page.goto(url, timeout=self.page_timeout_ms, wait_until="domcontentloaded")
            html = await page.content()
            # Collect all hrefs on the page for link-following
            hrefs = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.getAttribute('href'))",
            )
            return html, hrefs
        except Exception as e:
            logger.debug(f"    Failed to load {url}: {e}")
            return None, []

    # ── contact/about URL discovery ───────────────────────────────────────────

    def _find_contact_page_urls(
        self,
        base_url: str,
        homepage_links: List[str],
    ) -> List[str]:
        """
        Returns a deduplicated list of URLs likely to contain contact info,
        ordered by confidence:
          1. Links from the homepage whose anchor text matches contact keywords
          2. Standard path guesses (/contact, /about, etc.)
        """
        found: List[str] = []
        seen:  set        = set()
        base_parsed = urlparse(base_url)

        # 1. Homepage links with contact-like anchor text
        for href in homepage_links:
            if not href:
                continue
            full_url = urljoin(base_url, href)
            parsed   = urlparse(full_url)
            # Only follow same-domain links
            if parsed.netloc and parsed.netloc != base_parsed.netloc:
                continue
            if _CONTACT_ANCHOR_WORDS.search(href):
                if full_url not in seen:
                    seen.add(full_url)
                    found.append(full_url)

        # 2. Standard path guesses
        for path in _CONTACT_PATHS:
            url = f"{base_parsed.scheme}://{base_parsed.netloc}{path}"
            if url not in seen:
                seen.add(url)
                found.append(url)

        return found

    # ── extraction helpers ────────────────────────────────────────────────────

    def _extract_contacts(self, html: str):
        """
        Run regex over the full HTML to extract emails and phone numbers.
        Returns (emails: List[str], phones: List[str]).
        """
        soup  = BeautifulSoup(html, "html.parser")
        # Use the visible text only to reduce false positives in scripts/styles
        text  = soup.get_text(separator=" ")

        emails = list({
            m.lower()
            for m in _EMAIL_RE.findall(text)
            if not _SKIP_EMAILS.match(m)
            # Remove false-positive image/file extensions mistaken for emails
            and not m.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
            )
        })

        phones = list({
            m.strip()
            for m in _PHONE_RE.findall(text)
            if len(re.sub(r"\D", "", m)) >= 10   # at least 10 digits (Indian number minimum)
        })

        return emails, phones

    def _extract_social(self, html: str, social_links: Dict[str, Optional[str]]) -> None:
        """
        Scan all <a href> tags for social media domain matches.
        Updates social_links in-place; skips already-found platforms.
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()   # strip leading/trailing whitespace and newlines
            if not href:
                continue
            for key, pattern in _SOCIAL_PATTERNS.items():
                if social_links[key] is None and pattern.search(href):
                    # Normalise: make sure it's an absolute URL
                    if href.startswith("http"):
                        social_links[key] = href
                    elif href.startswith("//"):
                        social_links[key] = f"https:{href}"
                    # Relative or malformed hrefs are skipped

    def _is_contact_url(self, url: str) -> bool:
        """Returns True if the URL path looks like a contact/about page."""
        path = urlparse(url).path.lower()
        return any(kw in path for kw in [
            "contact", "reach", "getintouch", "get-in-touch",
            "about", "team", "people",
        ])

    # ── email ranking ─────────────────────────────────────────────────────────

    def _rank_emails(self, raw_emails: List[str], base_url: str) -> List[str]:
        """
        Deduplicate and rank emails:
          Tier 1 (best):  matches the company's own domain AND is not generic
          Tier 2:         matches domain but is a generic role address (info@, sales@)
          Tier 3:         any other non-skip email
        Returns a list sorted best-first.
        """
        if not raw_emails:
            return []

        domain = urlparse(base_url).netloc.lower().lstrip("www.")
        seen   = set()
        tiers  = {1: [], 2: [], 3: []}

        for email in raw_emails:
            e = email.lower().strip()
            if e in seen:
                continue
            seen.add(e)

            email_domain = e.split("@")[-1] if "@" in e else ""
            on_domain    = domain and (email_domain == domain or email_domain.endswith("." + domain))
            is_generic   = bool(_GENERIC_EMAILS.match(e))

            if on_domain and not is_generic:
                tiers[1].append(e)
            elif on_domain and is_generic:
                tiers[2].append(e)
            else:
                tiers[3].append(e)

        return tiers[1] + tiers[2] + tiers[3]

    # ── phone deduplication ───────────────────────────────────────────────────

    def _clean_phones(
        self,
        raw_phones: List[str],
        maps_phone: Optional[str],
    ) -> List[str]:
        """
        Validate, deduplicate, and clean phone numbers found on the website.

        Validation rules (Indian lead generation context):
          1. Must have at least 10 digits.
          2. Must not exceed 13 digits (rules out ISBN-like numbers, IDs, etc.).
          3. If a country code is present (+XX), only +91 (India) is accepted.
             Numbers with +1, +81, +66 etc. are foreign and discarded.
          4. The core 10-digit part must start with 6-9 (Indian mobile/local)
             OR the number starts with 0 / 91 (STD / ISD prefix).
          5. Excludes any number whose digits already appear in the Google Maps
             phone field (which is already stored in the 'phone' field).
        """
        seen_digits: set  = set()
        cleaned:     List[str] = []

        # Seed seen-set with the Maps phone so we don't duplicate it
        if maps_phone:
            seen_digits.add(re.sub(r"\D", "", maps_phone))

        for p in raw_phones:
            p = p.strip()
            digits = re.sub(r"\D", "", p)

            # Rule 1 & 2: digit count must be 10-13
            if not (10 <= len(digits) <= 13):
                continue

            # Rule 3: reject non-Indian country codes
            # If the string starts with +, extract and check the country code.
            if p.startswith("+"):
                cc_match = re.match(r"^\+(\d{1,3})", p)
                if cc_match:
                    cc = cc_match.group(1)
                    if cc != "91":          # not India — skip
                        continue

            # Rule 4: core 10 digits must start with 6-9, OR number has 0/91 prefix
            core = digits[-10:]             # last 10 digits = the local number
            has_valid_prefix = (
                digits.startswith("91")     # ISD prefix 91XXXXXXXXXX
                or digits.startswith("0")   # STD prefix 0XXXXXXXXXXX
            )
            if not re.match(r"^[6-9]", core) and not has_valid_prefix:
                continue

            # Dedup by digit signature
            if digits not in seen_digits:
                seen_digits.add(digits)
                cleaned.append(p)

        return cleaned

    # ── URL normalisation ─────────────────────────────────────────────────────

    @staticmethod
    def _normalise_url(website: str) -> str:
        """
        Ensure the website string is a proper https:// URL.
        Google Maps often returns bare domains like 'vitvara.in'.
        """
        website = website.strip()
        if not website.startswith("http://") and not website.startswith("https://"):
            website = "https://" + website
        return website


# ── standalone test run ───────────────────────────────────────────────────────
# How to run this module:
#
#     python main.py
#
# main.py opens the GUI input form and runs the full pipeline including
# this module as Step 5.
#
# To test this module in isolation:
#
#     from contact_discovery import ContactDiscovery
#     import json
#     with open("output/current_leads.json") as f:
#         data = json.load(f)
#     results = ContactDiscovery().discover(data["leads"])
#     for r in results:
#         print(r.company_name, r.primary_email, r.linkedin_url)
#
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline with the GUI input form.")
    print("See the comment block above for how to test this module in isolation.")
