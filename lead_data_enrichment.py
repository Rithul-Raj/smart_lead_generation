"""
Module 5: Lead Data Enrichment
--------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
After Modules 1-4 we have company name, address, phone, website, emails,
and social links.  Module 5 fills in the remaining fields that the CRM and
downstream AI modules (Module 7 - Lead Scoring, Module 9 - CRM Export) need:

  company_size_range       : "1-10" / "11-50" / "51-200" / "201-500" /
                             "501-1000" / "1000+"
  employee_count_est       : raw text hint  e.g. "team of ~150"
  year_founded             : "2012"
  headquarters             : "Pune, Maharashtra, India"
  company_description      : 1-2 sentence summary (what the company does)
  technologies_used        : ["React", "AWS", "Python"]  (detected from HTML)
  enrichment_source        : "website" / "linkedin" / "google" / "none"
  data_completeness_score  : 0.0-1.0  (% of 8 key fields filled, used by
                             Module 7 - AI Lead Scoring)

Enrichment sources (priority order)
--------------------------------------
  1. Company website /about page  — founded year, employee hints, description
  2. LinkedIn public company page — size, founded, HQ, description
  3. Google search snippet        — fallback for any still-missing fields

No paid APIs needed.
Uses: playwright + beautifulsoup4 + re  (already installed for earlier modules)
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
logger = logging.getLogger("lead_data_enrichment")


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

# Founded / established year
_FOUNDED_RE = [
    re.compile(r'\bfounded\s+(?:in\s+)?((?:19|20)\d{2})\b',      re.I),
    re.compile(r'\bestablished\s+(?:in\s+)?((?:19|20)\d{2})\b',  re.I),
    re.compile(r'\bincorporated\s+(?:in\s+)?((?:19|20)\d{2})\b', re.I),
    re.compile(r'\bstarted\s+(?:in\s+)?((?:19|20)\d{2})\b',      re.I),
    re.compile(r'\bsince\s+((?:19|20)\d{2})\b',                   re.I),
    re.compile(r'\best\.\s*((?:19|20)\d{2})\b',                   re.I),   # "Est. 2010"
    re.compile(r'\bin\s+((?:19|20)\d{2})\s+(?:and|we|our)',       re.I),
    # "2012 - Present" or "2012-present"
    re.compile(r'\b((?:19|20)\d{2})\s*[-\u2013]\s*(?:present|now|today)\b', re.I),
    # Footer copyright: "© 2012" or "Copyright 2012"
    re.compile(r'(?:copyright|©)\s*\w*\s*((?:19|20)\d{2})', re.I),
]

# Employee / team size
_SIZE_TEXT_RE = [
    # Explicit ranges like "51-200 employees"
    re.compile(r'\b(\d{1,4})\s*[-\u2013]\s*(\d{1,4})\s*(?:employees?|people|professionals?|staff|team\s*members?)\b', re.I),
    # "team of 50", "over 200 employees", "50+ employees"
    re.compile(r'\b(?:team\s+of|over|more\s+than|around|approximately|~)\s*(\d{1,5})\s*(?:employees?|people|professionals?|staff|members?)?\b', re.I),
    # "150 employees"
    re.compile(r'\b(\d{1,5})\+?\s*(?:employees?|professionals?|staff|people)\b', re.I),
]

# LinkedIn-specific patterns (found in their public page HTML)
_LI_SIZE_RE   = re.compile(r'(\d[\d,]*)\s*[-\u2013]\s*(\d[\d,]*)\s*employees', re.I)
_LI_FOUNDED_RE = re.compile(r'Founded\s*\n?\s*((?:19|20)\d{2})', re.I)
_LI_HQ_RE     = re.compile(r'Headquarters\s*\n?\s*([^\n]+)', re.I)

# ─────────────────────────────────────────────────────────────────────────────
# Technology signature map
# key   = human-readable technology name shown in output
# value = list of substrings to look for in the page HTML source
# ─────────────────────────────────────────────────────────────────────────────
_TECH_SIGNATURES: Dict[str, List[str]] = {
    # Frontend frameworks
    "React":          ["react.min.js", "react-dom", "/react@", "react.js"],
    "Angular":        ["angular.min.js", "ng-version=", "@angular/core", "angular.js"],
    "Vue.js":         ["vue.min.js", "vue.js", "/vue@", "vuejs"],
    "Next.js":        ["/_next/static", "__next"],
    "Nuxt.js":        ["/_nuxt/", "__nuxt"],
    "jQuery":         ["jquery.min.js", "jquery-", "/jquery@"],
    "Bootstrap":      ["bootstrap.min.css", "bootstrap.min.js", "bootstrap/css"],
    "Tailwind CSS":   ["tailwind.css", "tailwindcss", "tailwind.min.css"],
    "Material UI":    ["material-ui", "@mui/", "material.min.js"],

    # CMS / Website builders
    "WordPress":      ["wp-content/", "wp-includes/", "wordpress"],
    "Shopify":        ["cdn.shopify.com", "shopify.com/s/files"],
    "Wix":            ["wixstatic.com", "parastorage.com"],
    "Squarespace":    ["squarespace.com", "sqspcdn.com"],
    "Webflow":        ["webflow.com", "webflow.io"],
    "Joomla":         ["joomla", "/media/jui/"],
    "Drupal":         ["drupal.js", "/sites/default/files/", "drupal.org"],
    "Magento":        ["mage/", "magento", "requirejs/require.js"],

    # Backend / Server-side hints (sometimes visible in headers or paths)
    "Django":         ["csrfmiddlewaretoken", "django", "__django"],
    "Laravel":        ["laravel", "livewire"],
    "ASP.NET":        ["__viewstate", "asp.net", "aspnetcore"],
    "Ruby on Rails":  ["rails", "turbolinks"],
    "PHP":            [".php?", "php/"],

    # Cloud & CDN
    "AWS":            ["amazonaws.com", "cloudfront.net", "s3.amazonaws"],
    "Google Cloud":   ["googleapis.com", "storage.googleapis"],
    "Cloudflare":     ["cloudflare.com", "cdnjs.cloudflare"],
    "Azure":          ["azurewebsites.net", "azure.com", "azureedge.net"],

    # Analytics & Marketing
    "Google Analytics": ["google-analytics.com", "gtag(", "analytics.js"],
    "Google Tag Manager": ["googletagmanager.com", "gtm.js"],
    "HubSpot":        ["hubspot.com", "hs-scripts.com", "hubspot"],
    "Intercom":       ["intercom.io", "widget.intercom"],
    "Zendesk":        ["zendesk.com", "zopim.com"],
    "Hotjar":         ["hotjar.com", "static.hotjar"],
    "Mixpanel":       ["mixpanel.com", "cdn.mxpnl"],

    # Payments / Commerce
    "Stripe":         ["stripe.com/v3", "js.stripe.com"],
    "Razorpay":       ["razorpay.com", "checkout.razorpay"],
    "PayPal":         ["paypal.com", "paypalobjects"],

    # Other
    "GraphQL":        ["graphql", "/graphql", "apollo"],
    "TypeScript":     [".ts?v=", "typescript.js"],
    "Salesforce":     ["salesforce.com", "force.com", "lightning.force"],
}

# Size range buckets — used to normalise raw employee counts
_SIZE_BUCKETS = [
    (1,    10,   "1-10"),
    (11,   50,   "11-50"),
    (51,   200,  "51-200"),
    (201,  500,  "201-500"),
    (501,  999,  "501-1000"),
    (1000, 9999999, "1000+"),
]

# Key fields used to compute data_completeness_score (8 fields per the CRM spec)
_COMPLETENESS_FIELDS = [
    "company_name",
    "website",
    "primary_email",
    "phone",
    "linkedin_url",
    "company_size_range",
    "year_founded",
    "headquarters",
]


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnrichedLeadCompany:
    """
    Full lead record after Module 5.
    Carries all fields from Module 4 (ContactEnrichedCompany) plus the
    enrichment fields added here.  This is the object handed to Module 6+.
    """
    # ── Module 1-4 fields ────────────────────────────────────────────────────
    company_name:          str
    address:               Optional[str] = None
    location:              Optional[str] = None
    industry:              Optional[str] = None
    website:               Optional[str] = None
    phone:                 Optional[str] = None
    category:              Optional[str] = None
    rating:                Optional[str] = None
    review_count:          Optional[str] = None
    website_title:         Optional[str] = None
    website_description:   Optional[str] = None
    # company_size intentionally omitted — use company_size_range below instead
    source:                str = "google_maps_detail_scrape_async"
    emails:                List[str] = field(default_factory=list)
    primary_email:         Optional[str] = None
    phones_discovered:     List[str] = field(default_factory=list)
    linkedin_url:          Optional[str] = None
    twitter_url:           Optional[str] = None
    facebook_url:          Optional[str] = None
    instagram_url:         Optional[str] = None
    youtube_url:           Optional[str] = None
    contact_page_url:      Optional[str] = None
    pages_crawled:         int = 0

    # ── Module 5 NEW fields ──────────────────────────────────────────────────
    company_size_range:        Optional[str]  = None   # "51-200"
    employee_count_est:        Optional[str]  = None   # raw hint e.g. "~120 employees"
    year_founded:              Optional[str]  = None   # "2012"
    headquarters:              Optional[str]  = None   # "Pune, Maharashtra"
    company_description:       Optional[str]  = None   # 1-2 sentence summary
    technologies_used:         List[str]      = field(default_factory=list)
    enrichment_source:         Optional[str]  = None   # "website" / "linkedin" / "google" / "none"
    data_completeness_score:   float          = 0.0    # 0.0-1.0

    # internal
    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class LeadDataEnricher:
    """
    Takes a list of contact-enriched company dicts (Module 4 output) and
    enriches each one with company size, founded year, headquarters,
    description, and technology stack.
    """

    def __init__(
        self,
        headless:        bool = True,
        concurrency:     int  = 3,
        page_timeout_ms: int  = 15000,
    ):
        self.headless        = headless
        self.concurrency     = concurrency
        self.page_timeout_ms = page_timeout_ms

    # ── public entry point ────────────────────────────────────────────────────

    def enrich(self, companies: List[Dict[str, Any]]) -> List["EnrichedLeadCompany"]:
        """
        Public synchronous entry point.

        Args:
            companies: list of dicts produced by Module 4 (ContactDiscovery).
        Returns:
            List[EnrichedLeadCompany] in the same order as input.
        """
        return asyncio.run(self._enrich_async(companies))

    # ── async orchestration ───────────────────────────────────────────────────

    async def _enrich_async(
        self, companies: List[Dict[str, Any]]
    ) -> List["EnrichedLeadCompany"]:

        logger.info(
            f"Lead Data Enrichment: processing {len(companies)} companies "
            f"({self.concurrency} workers)"
        )

        queue: asyncio.Queue = asyncio.Queue()
        for i, c in enumerate(companies):
            queue.put_nowait((i, c))

        results: List[Optional[EnrichedLeadCompany]] = [None] * len(companies)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            async def worker():
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
                            idx, company = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        results[idx] = await self._enrich_one(page, company)
                        queue.task_done()
                finally:
                    await context.close()

            await asyncio.gather(*[worker() for _ in range(self.concurrency)])
            await browser.close()

        enriched = sum(
            1 for r in results
            if r and (r.company_size_range or r.year_founded or r.company_description)
        )
        logger.info(
            f"Lead Data Enrichment complete: "
            f"{enriched}/{len(companies)} companies had enrichment data found."
        )
        return results

    # ── per-company enrichment ────────────────────────────────────────────────

    async def _enrich_one(
        self, page: Page, company: Dict[str, Any]
    ) -> "EnrichedLeadCompany":
        """
        Enrich a single company.  Tries sources in this order:
          1. Company website /about page
          2. LinkedIn public company page
          3. Google search snippet (fallback)
        """
        name    = company.get("company_name", "Unknown")
        website = company.get("website")
        li_url  = company.get("linkedin_url")

        # Start with all existing fields copied over
        result = EnrichedLeadCompany(
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
            # company_size omitted — replaced by company_size_range (Module 5 field below)
            source              = company.get("source", "google_maps_detail_scrape_async"),
            emails              = company.get("emails") or [],
            primary_email       = company.get("primary_email"),
            phones_discovered   = company.get("phones_discovered") or [],
            linkedin_url        = li_url,
            twitter_url         = company.get("twitter_url"),
            facebook_url        = company.get("facebook_url"),
            instagram_url       = company.get("instagram_url"),
            youtube_url         = company.get("youtube_url"),
            contact_page_url    = company.get("contact_page_url"),
            pages_crawled       = company.get("pages_crawled", 0),
        )

        enrichment_data: Dict[str, Any] = {}

        # ── Source 1: Company website /about page ─────────────────────────────
        if website:
            enrichment_data = await self._enrich_from_website(page, website, name)

        # ── Source 2: LinkedIn public company page ────────────────────────────
        # Only attempt if website didn't give us size + founded
        if li_url and not (enrichment_data.get("company_size_range") and enrichment_data.get("year_founded")):
            li_data = await self._enrich_from_linkedin(page, li_url, name)
            # Merge — LinkedIn fills gaps not found on website
            for key, val in li_data.items():
                if val and not enrichment_data.get(key):
                    enrichment_data[key] = val
            if li_data:
                enrichment_data["enrichment_source"] = (
                    "website+linkedin"
                    if enrichment_data.get("enrichment_source") == "website"
                    else "linkedin"
                )

        # ── Source 3: Google search fallback ─────────────────────────────────
        if not enrichment_data.get("year_founded") and not enrichment_data.get("company_size_range"):
            g_data = await self._enrich_from_google(page, name, company.get("location", ""))
            for key, val in g_data.items():
                if val and not enrichment_data.get(key):
                    enrichment_data[key] = val
            if g_data and not enrichment_data.get("enrichment_source"):
                enrichment_data["enrichment_source"] = "google"

        # ── Apply enrichment data to result ───────────────────────────────────
        result.company_size_range  = enrichment_data.get("company_size_range")
        result.employee_count_est  = enrichment_data.get("employee_count_est")
        result.year_founded        = enrichment_data.get("year_founded")
        result.headquarters        = enrichment_data.get("headquarters")
        result.company_description = enrichment_data.get("company_description")
        result.technologies_used   = enrichment_data.get("technologies_used", [])
        result.enrichment_source   = enrichment_data.get("enrichment_source", "none")

        # ── Compute data completeness score ───────────────────────────────────
        result.data_completeness_score = self._compute_completeness(result)

        logger.info(
            f"  [{name}]  "
            f"size={result.company_size_range or '-'}  "
            f"founded={result.year_founded or '-'}  "
            f"tech={len(result.technologies_used)}  "
            f"score={result.data_completeness_score:.2f}  "
            f"src={result.enrichment_source}"
        )
        return result

    # ── Source 1: Website enrichment ──────────────────────────────────────────

    async def _enrich_from_website(
        self, page: Page, website: str, name: str
    ) -> Dict[str, Any]:
        """
        Visit the company website (homepage + /about) and extract:
        - company_description (from meta description or first paragraph)
        - year_founded (regex on text)
        - employee_count_est + company_size_range (regex on text)
        - technologies_used (from script/link tags)
        - headquarters (city extraction from address mentions)
        """
        data: Dict[str, Any] = {}

        base_url = self._normalise_url(website)

        # Try homepage first, then /about page
        pages_to_try = [base_url, urljoin(base_url, "/about"), urljoin(base_url, "/about-us")]

        all_text   = ""
        all_html   = ""
        desc_found = False

        for url in pages_to_try:
            html, text = await self._fetch(page, url)
            if not html:
                continue

            all_html += html
            all_text += " " + text

            # Description: prefer /about page's first substantial paragraph
            if not desc_found:
                desc = self._extract_description(html, url, base_url)
                if desc:
                    data["company_description"] = desc
                    desc_found = True

        if not all_html:
            return data

        # Founded year
        founded = self._extract_founded(all_text)
        if founded:
            data["year_founded"] = founded

        # Employee count / size
        size_range, size_est = self._extract_size(all_text)
        if size_range:
            data["company_size_range"] = size_range
        if size_est:
            data["employee_count_est"] = size_est

        # Technology stack (from HTML source)
        techs = self._detect_technologies(all_html)
        if techs:
            data["technologies_used"] = techs

        if data:
            data["enrichment_source"] = "website"

        return data

    # ── Source 2: LinkedIn enrichment ─────────────────────────────────────────

    async def _enrich_from_linkedin(
        self, page: Page, li_url: str, name: str
    ) -> Dict[str, Any]:
        """
        Visit the LinkedIn public company /about page and extract
        company size, founded year, headquarters, and description.

        LinkedIn's public pages show limited info without login.
        We gracefully return empty dict if they block or redirect to login.
        """
        data: Dict[str, Any] = {}

        # Normalise to the /about sub-page
        li_about = li_url.rstrip("/") + "/about/"

        html, text = await self._fetch(page, li_about)
        if not html or "authwall" in page.url or "login" in page.url.lower():
            return data   # redirected to login — skip

        # Company size: LinkedIn shows "51-200 employees" in a dt/dd block
        m = _LI_SIZE_RE.search(text)
        if m:
            low, high = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            data["company_size_range"] = self._bucket_size(low)
            data["employee_count_est"] = f"{m.group(1)}-{m.group(2)} employees"

        # Founded year
        m = _LI_FOUNDED_RE.search(text)
        if m:
            data["year_founded"] = m.group(1)

        # Headquarters
        m = _LI_HQ_RE.search(text)
        if m:
            hq = m.group(1).strip()
            if len(hq) < 80:   # sanity check — real HQs are short
                data["headquarters"] = hq

        # Description (the "Overview" section on LinkedIn)
        soup = BeautifulSoup(html, "html.parser")
        # LinkedIn's about section often has a <p> with the overview text
        for tag in soup.find_all(["p", "section"]):
            txt = tag.get_text(" ", strip=True)
            if 60 < len(txt) < 1000 and not any(
                skip in txt.lower()
                for skip in ["sign in", "join now", "linkedin", "cookie"]
            ):
                data["company_description"] = txt[:500]
                break

        return data

    # ── Source 3: Google search fallback ──────────────────────────────────────

    async def _enrich_from_google(
        self, page: Page, company_name: str, location: str
    ) -> Dict[str, Any]:
        """
        Search Google for '<company> <location> founded employees' and
        extract structured data from the Knowledge Panel / first snippet.
        """
        data: Dict[str, Any] = {}

        query = f"{company_name} {location} company founded employees"
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

        html, text = await self._fetch(page, search_url)
        if not html:
            return data

        # Founded year from search results text
        founded = self._extract_founded(text)
        if founded:
            data["year_founded"] = founded

        # Size / employees from search results text
        size_range, size_est = self._extract_size(text)
        if size_range:
            data["company_size_range"] = size_range
        if size_est:
            data["employee_count_est"] = size_est

        # Description: look for the meta description of the search snippet
        soup = BeautifulSoup(html, "html.parser")
        for span in soup.find_all("span"):
            txt = span.get_text(" ", strip=True)
            if 80 < len(txt) < 600 and company_name.lower().split()[0] in txt.lower():
                data["company_description"] = txt[:500]
                break

        return data

    # ── Page fetcher ──────────────────────────────────────────────────────────

    async def _fetch(self, page: Page, url: str):
        """Navigate to URL; return (html, visible_text) or (None, None)."""
        try:
            await page.goto(url, timeout=self.page_timeout_ms, wait_until="domcontentloaded")
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            return html, text
        except Exception as e:
            logger.debug(f"  fetch failed [{url}]: {e}")
            return None, None

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _extract_description(self, html: str, url: str, base_url: str) -> Optional[str]:
        """
        Try to get a clean 1-2 sentence description of the company.
        Priority: meta description → og:description → first long <p> on /about page.
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. Meta description
        for meta in soup.find_all("meta"):
            name    = (meta.get("name") or meta.get("property") or "").lower()
            content = meta.get("content", "").strip()
            if name in ("description", "og:description") and 40 < len(content) < 600:
                return content

        # 2. First meaningful paragraph on /about pages
        is_about = any(kw in url for kw in ["/about", "/company", "/who-we-are"])
        if is_about:
            for tag in soup.find_all("p"):
                txt = tag.get_text(" ", strip=True)
                if 80 < len(txt) < 800:
                    return txt[:500]

        return None

    def _extract_founded(self, text: str) -> Optional[str]:
        """Scan text for year-founded hints using multiple regex patterns."""
        for pattern in _FOUNDED_RE:
            m = pattern.search(text)
            if m:
                year = m.group(1)
                # Sanity: founded year must be plausible (1900-current year)
                if 1900 <= int(year) <= 2026:
                    return year
        return None

    def _extract_size(self, text: str):
        """
        Scan text for employee count hints.
        Returns (size_range: str | None, employee_count_est: str | None).
        """
        for pattern in _SIZE_TEXT_RE:
            m = pattern.search(text)
            if m:
                groups = [g for g in m.groups() if g is not None]
                if not groups:
                    continue
                # If we got a range (low, high), use the low value for bucketing
                try:
                    low  = int(groups[0].replace(",", ""))
                    high = int(groups[1].replace(",", "")) if len(groups) > 1 else low
                    bucket = self._bucket_size(low)
                    raw    = f"{groups[0]}-{groups[1]} employees" if len(groups) > 1 else f"~{groups[0]} employees"
                    return bucket, raw
                except (ValueError, IndexError):
                    continue
        return None, None

    def _bucket_size(self, count: int) -> str:
        """Map a raw employee count integer to a size-range bucket string."""
        for low, high, label in _SIZE_BUCKETS:
            if low <= count <= high:
                return label
        return "1000+"

    def _detect_technologies(self, html: str) -> List[str]:
        """
        Scan the page HTML source for known technology signatures.
        Returns a deduplicated list of technology names detected.
        """
        html_lower = html.lower()
        found: List[str] = []
        for tech_name, signatures in _TECH_SIGNATURES.items():
            if any(sig.lower() in html_lower for sig in signatures):
                found.append(tech_name)
        return found

    @staticmethod
    def _normalise_url(website: str) -> str:
        """Ensure website has an https:// prefix."""
        website = website.strip()
        if not website.startswith("http://") and not website.startswith("https://"):
            website = "https://" + website
        return website

    # ── Data completeness score ───────────────────────────────────────────────

    @staticmethod
    def _compute_completeness(company: "EnrichedLeadCompany") -> float:
        """
        Compute a 0.0-1.0 score representing how complete this lead record is.

        Checks 8 key fields defined in the CRM spec:
          company_name, website, primary_email, phone,
          linkedin_url, company_size_range, year_founded, headquarters

        Used downstream by Module 7 (AI Lead Scoring) as one of its inputs.
        """
        field_values = {
            "company_name":      company.company_name,
            "website":           company.website,
            "primary_email":     company.primary_email,
            "phone":             company.phone,
            "linkedin_url":      company.linkedin_url,
            "company_size_range":company.company_size_range,
            "year_founded":      company.year_founded,
            "headquarters":      company.headquarters,
        }
        filled = sum(1 for v in field_values.values() if v)
        return round(filled / len(field_values), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone usage note
# ─────────────────────────────────────────────────────────────────────────────
# Run the full pipeline:
#     python main.py
#
# To test this module in isolation:
#     from lead_data_enrichment import LeadDataEnricher
#     import json
#     with open("output/current/current_leads.json") as f:
#         data = json.load(f)
#     results = LeadDataEnricher().enrich(data["leads"])
#     for r in results:
#         print(r.company_name, r.company_size_range, r.year_founded,
#               r.data_completeness_score, r.technologies_used[:3])
#
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
    print("See the comment block above for isolation testing.")
