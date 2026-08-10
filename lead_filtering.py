"""
Module 8: Deduplication & Quality Filtering
--------------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Takes the scored leads from Module 7 and applies strict quality and
deduplication filters before they are allowed into the final output.

Filters applied:
1. Contact Point Minimum: Drops leads with NO emails, NO phone, and NO LinkedIn.
2. Invalid Contact Drop: Drops leads where ALL found emails are invalid.
3. Tier Filtering: Drops "Cold" leads (score < 50) as they lack sufficient data for outreach.
4. Intra-run Deduplication:
    - By Website Domain
    - By LinkedIn URL
    - By Phone Number
    (Note: Master-level deduplication across multiple runs by place_id 
     is already handled in output_exporter.py)

Returns the final, cleaned list of highly qualified leads.
"""

import logging
from typing import List
from urllib.parse import urlparse

# Module 7 dataclass
from ai_lead_scoring import ScoredLeadCompany

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("lead_filtering")


class LeadFilter:
    """
    Module 8 — Deduplication & Quality Filtering.
    """

    def filter_leads(self, leads: List[ScoredLeadCompany]) -> List[ScoredLeadCompany]:
        """
        Apply quality and deduplication filters to a list of scored leads.
        
        Args:
            leads: List of ScoredLeadCompany objects from Module 7.
        Returns:
            Filtered list of ScoredLeadCompany objects.
        """
        logger.info(f"Lead Filtering: analyzing {len(leads)} scored leads...")

        filtered = []
        dropped_reasons = {
            "no_contact_points": 0,
            "all_emails_invalid": 0,
            "cold_tier": 0,
            "duplicate_domain": 0,
            "duplicate_linkedin": 0,
            "duplicate_phone": 0,
        }

        # Track uniqueness within this run
        seen_domains = set()
        seen_linkedins = set()
        seen_phones = set()

        for lead in leads:
            # ── 1. Quality: Must have at least one contact vector ────────────
            has_email = bool(lead.verified_emails or lead.risky_emails)
            has_phone = bool(lead.phone or lead.phones_discovered)
            has_li    = bool(lead.linkedin_url)

            if not (has_email or has_phone or has_li):
                dropped_reasons["no_contact_points"] += 1
                continue

            # ── 2. Quality: All emails invalid check ──────────────────────────
            # If emails were found, but NONE of them are verified/risky, drop it
            had_raw_emails = bool(lead.emails)
            if had_raw_emails and not has_email:
                dropped_reasons["all_emails_invalid"] += 1
                continue

            # ── 3. Quality: Priority Filtering ────────────────────────────────────
            if lead.priority == "Low":
                dropped_reasons["cold_tier"] += 1
                continue

            # ── 4. Deduplication: Website Domain ──────────────────────────────
            domain = self._extract_domain(lead.website)
            if domain:
                if domain in seen_domains:
                    dropped_reasons["duplicate_domain"] += 1
                    continue
                seen_domains.add(domain)

            # ── 5. Deduplication: LinkedIn URL ────────────────────────────────
            li = self._normalize_linkedin(lead.linkedin_url)
            if li:
                if li in seen_linkedins:
                    dropped_reasons["duplicate_linkedin"] += 1
                    continue
                seen_linkedins.add(li)

            # ── 6. Deduplication: Phone ───────────────────────────────────────
            # Use the primary phone for strict deduplication
            phone = self._normalize_phone(lead.phone)
            if phone:
                if phone in seen_phones:
                    dropped_reasons["duplicate_phone"] += 1
                    continue
                seen_phones.add(phone)

            # Lead passed all filters!
            filtered.append(lead)

        # Log summary
        total_dropped = sum(dropped_reasons.values())
        if total_dropped > 0:
            logger.info(f"Filtering complete. Dropped {total_dropped} leads:")
            for reason, count in dropped_reasons.items():
                if count > 0:
                    logger.info(f"  - {reason}: {count}")
        else:
            logger.info("Filtering complete. 0 leads dropped.")

        logger.info(f"Final qualified leads: {len(filtered)}/{len(leads)}")
        return filtered

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_domain(self, url: str) -> str:
        """Extract base domain from a URL (e.g. https://www.acme.com/about -> acme.com)"""
        if not url:
            return ""
        
        # Add scheme if missing so urlparse works correctly
        if not url.startswith("http"):
            url = "http://" + url
            
        try:
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url.strip().lower()

    def _normalize_linkedin(self, url: str) -> str:
        """Normalize LinkedIn URLs for exact deduplication."""
        if not url:
            return ""
        url = url.lower().strip()
        if url.endswith("/"):
            url = url[:-1]
        # Remove tracking params
        if "?" in url:
            url = url.split("?")[0]
        return url

    def _normalize_phone(self, phone: str) -> str:
        """Keep only digits for phone deduplication."""
        if not phone:
            return ""
        digits = "".join(filter(str.isdigit, phone))
        # If it's too short after stripping, don't use it for dedup
        return digits if len(digits) >= 6 else ""

if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
