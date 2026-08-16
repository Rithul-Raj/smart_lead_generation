"""
Module 9: Output Formatting & CRM Export
-----------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Takes the final qualified leads from Module 8 (ScoredLeadCompany objects)
and transforms them into clean, minimal, CRM-ready dictionaries before
they are saved to output/current/ and output/master/.

Transformations applied:
  1. Column ordering       — Priority → Score → Email → Phone → Company details.
  2. Column renaming       — Snake_case → human-readable headers.
  3. Internal field drops  — All pipeline-only fields stripped (raw, source,
                             pages_crawled, tech stack, social URLs, website
                             title/description, email verification internals, etc.)
  4. Smart email column    — Single "Email" column: uses best_email if present,
                             falls back to verified_emails, then risky_emails.
                             No extra email columns clutter the sheet.
  5. List formatting       — Phone lists joined as comma-separated strings.
  6. Empty-value cleanup   — None / empty values become empty strings.

Final CRM columns (in order):
  Priority | Lead Score | Email | Phone | Additional Phones |
  Company Name | Business Category | Industry | Location |
  Full Address | Website | Company Size | Year Founded |
  Headquarters | Company Description | Google Rating
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger("crm_exporter")


# ─────────────────────────────────────────────────────────────────────────────
# CRM column order + human-readable header names
# "Email" is handled separately via smart fallback logic (see _format_one)
# ─────────────────────────────────────────────────────────────────────────────
_CRM_FIELD_MAP = [
    # ── Contact — EMAIL handled separately (smart fallback logic) ────────────
    # ── Contact — Phone ────────────────────────────────────────────────────
    ("phone",               "Phone"),              # Maps-listed phone
    ("phones_discovered",   "Additional Phones"),  # crawled from website
    # ── Company identity ───────────────────────────────────────────────────
    ("company_name",        "Company Name"),
    ("category",            "Business Category"),
    ("industry",            "Industry"),
    ("location",            "Search Location"),
    ("address",             "Full Address"),
    ("website",             "Website"),
    # ── Company profile ────────────────────────────────────────────────────
    ("company_size_range",  "Company Size"),
    ("year_founded",        "Year Founded"),
    ("company_description", "Company Description"),
    # ── Reputation ─────────────────────────────────────────────────────────
    ("rating",              "Google Rating"),
    # ── AI Qualification (last columns) ────────────────────────────────────
    ("priority",            "Priority"),           # High / Medium / Low
    ("lead_score",          "Lead Score"),          # 0–100
]


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class CRMExporter:
    """
    Module 9 — Output Formatting & CRM Export.

    Produces minimal, clean records directly importable into any CRM.
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

        high   = sum(1 for r in crm_records if r.get("Priority") == "High")
        medium = sum(1 for r in crm_records if r.get("Priority") == "Medium")
        low    = sum(1 for r in crm_records if r.get("Priority") == "Low")
        logger.info(
            f"CRM Export formatted {len(crm_records)} leads — "
            f"High: {high} | Medium: {medium} | Low: {low}"
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
        Render any Python value into a clean string.
          list  → comma-separated  e.g. "+91 98765, +1 405 638"
          None  → ""
          bool  → "Yes" / "No"
          float → no trailing .0 unless meaningful decimal
          other → str()
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

    def _resolve_email(self, row: Dict[str, Any]) -> str:
        """
        Smart email resolution — single value for the 'Email' column.

        Priority order:
          1. best_email   (set by Module 6 — already the top pick)
          2. verified_emails[0]  (personal addresses that passed MX check)
          3. risky_emails[0]     (role/generic but domain is alive)
          4. primary_email       (raw Module 4 pick, unverified)
          5. ""                  (nothing found)
        """
        best = (row.get("best_email") or "").strip()
        if best:
            return best

        verified = [e for e in (row.get("verified_emails") or []) if e]
        if verified:
            return verified[0]

        risky = [e for e in (row.get("risky_emails") or []) if e]
        if risky:
            return risky[0]

        primary = (row.get("primary_email") or "").strip()
        return primary

    def _format_one(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single raw lead dict into a CRM-ready ordered dict."""
        crm: Dict[str, Any] = {}

        # First column: smart Email (best available)
        crm["Email"] = self._resolve_email(row)

        # Rest of columns from the field map (phone, company details, rating,
        # then Priority + Lead Score last)
        for internal_key, crm_header in _CRM_FIELD_MAP:
            crm[crm_header] = self._format_value(row.get(internal_key))

        return crm


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
