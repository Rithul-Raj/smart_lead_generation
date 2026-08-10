"""
Module 9: Output Formatting & CRM Export
-----------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Takes the final qualified leads from Module 8 (ScoredLeadCompany objects)
and transforms them into clean, CRM-ready dictionaries before they are saved
to output/current/ and output/master/.

Transformations applied:
  1. Column ordering       — Most important fields come first (Lead Tier,
                             Score, Best Email, Phone — then company details).
  2. Column renaming       — Snake_case field names become human-readable
                             column headers usable in HubSpot / Salesforce.
  3. Internal field drops  — Pipeline-only fields (raw, source, pages_crawled,
                             enrichment_source, data_completeness_score, etc.)
                             are stripped — they don't belong in a sales sheet.
  4. List formatting       — Technologies, verified emails, etc. are joined
                             as comma-separated strings for spreadsheet use.
  5. Empty-value cleanup   — None / empty-list values become empty strings.

Output: plain dicts consumed directly by save_current_output() in output_exporter.py.
The existing current_leads.csv / master_leads.csv ARE the CRM export — no extra files.
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger("crm_exporter")

# ─────────────────────────────────────────────────────────────────────────────
# CRM column order + human-readable header names
# Ordered: prioritisation signals → contact info → company details → social
# ─────────────────────────────────────────────────────────────────────────────
_CRM_FIELD_MAP = [
    # ── Lead qualification signals ─────────────────────────────────────────
    ("priority",               "Priority"),           # High / Medium / Low
    ("lead_score",             "Lead Score"),          # 0–100
    # ── Best contact point ─────────────────────────────────────────────────
    ("best_email",             "Best Email"),          # top verified/risky email
    ("verified_emails",        "Verified Emails"),     # personal emails (valid)
    ("risky_emails",           "Role Emails"),         # info@, sales@, etc.
    ("phone",                  "Phone (Google Maps)"), # Maps-listed phone
    ("phones_discovered",      "Phones Discovered"),   # extra phones from site
    # ── Core company identity ──────────────────────────────────────────────
    ("company_name",           "Company Name"),
    ("category",               "Business Category"),
    ("industry",               "Industry"),
    ("location",               "Search Location"),
    ("address",                "Full Address"),
    ("website",                "Website"),
    # ── Company profile ────────────────────────────────────────────────────
    ("company_size_range",     "Company Size"),
    ("year_founded",           "Year Founded"),
    ("headquarters",           "Headquarters"),
    ("company_description",    "Company Description"),
    ("technologies_used",      "Tech Stack"),
    # ── Reputation signals ─────────────────────────────────────────────────
    ("rating",                 "Google Rating"),
    ("review_count",           "Review Count"),
    # ── Social / digital presence ──────────────────────────────────────────
    ("linkedin_url",           "LinkedIn"),
    ("twitter_url",            "Twitter / X"),
    ("facebook_url",           "Facebook"),
    ("instagram_url",          "Instagram"),
    ("youtube_url",            "YouTube"),
    # ── Email verification summary ─────────────────────────────────────────
    ("email_verification_notes", "Email Verification Status"),
    ("primary_email_status",   "Primary Email Status"),
    # ── Website content snippets (useful for personalization) ──────────────
    ("website_title",          "Website Title"),
    ("website_description",    "Website Meta Description"),
]

# Keys of all fields in _CRM_FIELD_MAP (for fast lookup)
_CRM_KEYS = {internal for internal, _ in _CRM_FIELD_MAP}


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class CRMExporter:
    """
    Module 9 — Output Formatting & CRM Export.

    Converts ScoredLeadCompany dicts into clean, ordered, human-readable
    dicts ready for CRM import (HubSpot / Salesforce / Zoho / etc.).
    """

    def format(self, leads: List[Any]) -> List[Dict[str, Any]]:
        """
        Format a list of ScoredLeadCompany objects (or plain dicts) into
        CRM-ready dicts.

        Args:
            leads: List of ScoredLeadCompany objects from Module 8.
        Returns:
            List of ordered, human-readable dicts.
        """
        crm_records = []
        for lead in leads:
            row = lead if isinstance(lead, dict) else self._to_dict(lead)
            crm_records.append(self._format_one(row))

        hot   = sum(1 for r in crm_records if r.get("Priority") == "High")
        warm  = sum(1 for r in crm_records if r.get("Priority") == "Medium")
        cold  = sum(1 for r in crm_records if r.get("Priority") == "Low")
        logger.info(
            f"CRM Export formatted {len(crm_records)} leads — "
            f"High: {hot} | Medium: {warm} | Low: {cold}"
        )
        return crm_records

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(lead) -> Dict[str, Any]:
        """Convert a dataclass object to a plain dict, dropping 'raw'."""
        try:
            from dataclasses import asdict
            d = asdict(lead)
        except TypeError:
            d = vars(lead)
        d.pop("raw", None)
        return d

    @staticmethod
    def _format_value(value) -> str:
        """
        Render any Python value into a clean string for CSV/JSON output.
          - list  → comma-separated (e.g. "React, AWS, Bootstrap")
          - None  → ""
          - bool  → "Yes" / "No"
          - float → rounded to 2 dp
          - other → str()
        """
        if value is None:
            return ""
        if isinstance(value, list):
            cleaned = [str(v).strip() for v in value if v]
            return ", ".join(cleaned)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            return f"{value:.2f}" if value != int(value) else str(int(value))
        return str(value).strip()

    def _format_one(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single raw lead dict into a CRM-ready ordered dict."""
        crm: Dict[str, Any] = {}

        for internal_key, crm_header in _CRM_FIELD_MAP:
            raw_val = row.get(internal_key)
            crm[crm_header] = self._format_value(raw_val)

        return crm


# ─────────────────────────────────────────────────────────────────────────────
# Standalone test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
