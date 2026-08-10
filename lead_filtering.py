"""
Module 8: Deduplication
------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Takes ALL scored leads from Module 7 and removes only TRUE intra-run
duplicates. Every lead, regardless of its priority or data completeness,
appears in the final output — ranked by lead_score (best first).

Only removed:
  - Intra-run duplicates by Website Domain
  - Intra-run duplicates by LinkedIn URL
  - Intra-run duplicates by Phone Number
  (Cross-run deduplication when merging into master is handled separately
   in output_exporter.py)

NOTE: Leads with Low priority or missing contact data are NOT dropped here.
      They appear in the output with their score (possibly 0) so the user
      always gets the full picture of what was searched.
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
        Remove intra-run duplicate leads only.
        All other leads pass through regardless of score or data completeness.

        Args:
            leads: List of ScoredLeadCompany objects from Module 7 (already
                   sorted by score descending).
        Returns:
            De-duplicated list — same order (best score first).
        """
        logger.info(f"Lead Deduplication: checking {len(leads)} leads for intra-run duplicates...")

        filtered = []
        dropped_reasons = {
            "duplicate_domain":   0,
            "duplicate_linkedin": 0,
            "duplicate_phone":    0,
        }

        # Track uniqueness within this run
        seen_domains   = set()
        seen_linkedins = set()
        seen_phones    = set()

        for lead in leads:
            # ── Deduplication: Website Domain ─────────────────────────────────
            domain = self._extract_domain(lead.website)
            if domain:
                if domain in seen_domains:
                    dropped_reasons["duplicate_domain"] += 1
                    continue
                seen_domains.add(domain)

            # ── Deduplication: LinkedIn URL ────────────────────────────────────
            li = self._normalize_linkedin(lead.linkedin_url)
            if li:
                if li in seen_linkedins:
                    dropped_reasons["duplicate_linkedin"] += 1
                    continue
                seen_linkedins.add(li)

            # ── Deduplication: Phone ───────────────────────────────────────────
            phone = self._normalize_phone(lead.phone)
            if phone:
                if phone in seen_phones:
                    dropped_reasons["duplicate_phone"] += 1
                    continue
                seen_phones.add(phone)

            filtered.append(lead)

        # Log summary
        total_dropped = sum(dropped_reasons.values())
        if total_dropped > 0:
            logger.info(f"Deduplication complete. Removed {total_dropped} duplicate leads:")
            for reason, count in dropped_reasons.items():
                if count > 0:
                    logger.info(f"  - {reason}: {count}")
        else:
            logger.info("Deduplication complete. No duplicates found.")

        logger.info(
            f"Output: {len(filtered)} leads  "
            f"(High: {sum(1 for c in filtered if c.priority=='High')}, "
            f"Medium: {sum(1 for c in filtered if c.priority=='Medium')}, "
            f"Low: {sum(1 for c in filtered if c.priority=='Low')})"
        )
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
