"""
Module 7: AI Lead Scoring & Prioritization
--------------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Assigns a lead_score (0–100) and a priority (High / Medium / Low) to every
qualified lead coming from Module 6 (Email Verification).

Scoring is split into four weighted pillars:

  Pillar 1 — Contact Reachability (40 pts max)
      The single most important signal: can we actually reach this company?
      • Verified personal email (non-role address)  : 30 pts
        Role / generic email only (no personal one) : 15 pts
        No email at all                             :  0 pts
      • Phone number present (Maps listing)         : 10 pts
        Note: pillars are additive — email + phone = 40 pts max.

  Pillar 2 — Digital Presence (30 pts max)
      Validates the company is active and findable online.
      • LinkedIn company URL discovered             : 15 pts
      • Working website with scraped content        :  8 pts
      • Any social media found (FB / TW / IG / YT)  :  7 pts

  Pillar 3 — Business Profile Depth (20 pts max)
      Measures how much we know about the company — used for personalisation.
      • Company description available               :  5 pts
      • Company size range known                    :  5 pts
      • Year founded known                          :  5 pts
      • Tech stack identified (≥1 technology)       :  5 pts

  Pillar 4 — Credibility Signals (10 pts max)
      Public trust indicators (Google Maps data).
      • Google Rating ≥ 4.5                         : 10 pts
      • Google Rating  4.0–4.4                      :  7 pts
      • Google Rating  3.5–3.9                      :  4 pts
      • Google Rating  3.0–3.4                      :  2 pts
      (review count > 10 is required for rating to count — avoids
       a single 5-star review from the owner inflating the score)

Priority tiers:
  High   : score ≥ 70   — well-reachable, solid profile → prioritise outreach
  Medium : score 40–69  — contactable but missing some data → nurture track
  Low    : score < 40   — insufficient data for outreach → deprioritise
  (Leads with priority = Low are dropped entirely by Module 8 / LeadFilter)

New fields added to every lead:
  lead_score : int   0–100
  priority   : str   "High" / "Medium" / "Low"
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ai_lead_scoring")


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoredLeadCompany:
    """
    Full lead record after Module 7.
    Carries all fields from Module 6 (VerifiedLeadCompany) plus scoring.
    Passed to Module 8 (LeadFilter).
    """
    # ── Module 1–5 fields ────────────────────────────────────────────────────
    company_name:              str
    address:                   Optional[str] = None
    location:                  Optional[str] = None
    industry:                  Optional[str] = None
    website:                   Optional[str] = None
    phone:                     Optional[str] = None
    category:                  Optional[str] = None
    rating:                    Optional[str] = None
    review_count:              Optional[str] = None
    website_title:             Optional[str] = None
    website_description:       Optional[str] = None
    source:                    str           = "google_maps_detail_scrape_async"
    emails:                    List[str]     = field(default_factory=list)
    primary_email:             Optional[str] = None
    phones_discovered:         List[str]     = field(default_factory=list)
    linkedin_url:              Optional[str] = None
    twitter_url:               Optional[str] = None
    facebook_url:              Optional[str] = None
    instagram_url:             Optional[str] = None
    youtube_url:               Optional[str] = None
    contact_page_url:          Optional[str] = None
    pages_crawled:             int           = 0
    # Module 5
    company_size_range:        Optional[str] = None
    employee_count_est:        Optional[str] = None
    year_founded:              Optional[str] = None
    headquarters:              Optional[str] = None
    company_description:       Optional[str] = None
    technologies_used:         List[str]     = field(default_factory=list)
    enrichment_source:         Optional[str] = None
    data_completeness_score:   float         = 0.0
    # Module 6
    verified_emails:           List[str]     = field(default_factory=list)
    risky_emails:              List[str]     = field(default_factory=list)
    invalid_emails:            List[str]     = field(default_factory=list)
    primary_email_status:      Optional[str] = None
    email_mx_valid:            Optional[bool]= None
    best_email:                Optional[str] = None
    email_verification_notes:  Optional[str] = None

    # ── Module 7 NEW fields ──────────────────────────────────────────────────
    lead_score:                int           = 0
    priority:                  str           = "Low"    # High / Medium / Low

    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring constants — change values here to tune the model
# ─────────────────────────────────────────────────────────────────────────────

# Pillar 1 — Contact Reachability (max 40)
_P1_VERIFIED_EMAIL   = 30   # personal / non-role email verified via MX
_P1_ROLE_EMAIL       = 15   # info@, sales@, etc. — valid but generic
_P1_PHONE            = 10   # any phone number from Maps or site crawl

# Pillar 2 — Digital Presence (max 30)
_P2_LINKEDIN         = 15   # LinkedIn company page URL
_P2_WEBSITE          = 8    # a working website with scraped content
_P2_SOCIAL           = 7    # any social handle (FB / TW / IG / YT)

# Pillar 3 — Business Profile Depth (max 20)
_P3_DESCRIPTION      = 5    # company description available
_P3_SIZE             = 5    # employee size range known
_P3_FOUNDED          = 5    # year founded known
_P3_TECH_STACK       = 5    # at least 1 technology identified

# Pillar 4 — Credibility Signals (max 10)
_P4_RATING_45        = 10   # rating ≥ 4.5
_P4_RATING_40        = 7    # rating 4.0–4.4
_P4_RATING_35        = 4    # rating 3.5–3.9
_P4_RATING_30        = 2    # rating 3.0–3.4
_MIN_REVIEWS_FOR_RATING = 10  # rating only counts when ≥10 reviews

# Priority thresholds
_THRESHOLD_HIGH      = 70   # score ≥ 70 → High
_THRESHOLD_MEDIUM    = 40   # score ≥ 40 → Medium  (else Low)


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class AILeadScorer:
    """
    Module 7 — AI Lead Scoring & Prioritization.
    Calculates lead_score and priority for every lead.
    """

    def score_leads(self, companies: List[Dict[str, Any]]) -> List[ScoredLeadCompany]:
        """
        Score a list of verified company dicts (from Module 6).

        Returns a list of ScoredLeadCompany objects, sorted by score descending.
        """
        logger.info(f"AI Lead Scoring: scoring {len(companies)} leads...")

        scored = [self._score_company(c) for c in companies]

        # Sort best-first so output files are naturally ranked
        scored.sort(key=lambda c: c.lead_score, reverse=True)

        counts = {"High": 0, "Medium": 0, "Low": 0}
        for c in scored:
            counts[c.priority] += 1

        logger.info(
            f"Scoring complete — "
            f"High: {counts['High']}, Medium: {counts['Medium']}, Low: {counts['Low']}"
        )
        return scored

    # ── per-company scoring ───────────────────────────────────────────────────

    def _score_company(self, company: Dict[str, Any]) -> ScoredLeadCompany:
        score      = 0
        breakdown  = {}   # for logging / debug

        # ── Pillar 1: Contact Reachability (max 40) ───────────────────────────
        verified = company.get("verified_emails") or []
        risky    = company.get("risky_emails") or []
        phone    = company.get("phone") or ""
        phones_d = company.get("phones_discovered") or []

        if verified:
            score += _P1_VERIFIED_EMAIL
            breakdown["email"] = f"+{_P1_VERIFIED_EMAIL} (verified personal)"
        elif risky:
            score += _P1_ROLE_EMAIL
            breakdown["email"] = f"+{_P1_ROLE_EMAIL} (role/generic only)"
        else:
            breakdown["email"] = "+0 (no email)"

        if phone or phones_d:
            score += _P1_PHONE
            breakdown["phone"] = f"+{_P1_PHONE}"
        else:
            breakdown["phone"] = "+0"

        # ── Pillar 2: Digital Presence (max 30) ───────────────────────────────
        if company.get("linkedin_url"):
            score += _P2_LINKEDIN
            breakdown["linkedin"] = f"+{_P2_LINKEDIN}"
        else:
            breakdown["linkedin"] = "+0"

        website = company.get("website") or ""
        website_title = company.get("website_title") or ""
        if website and website_title:
            # Website actively scraped (has title = page was reachable)
            score += _P2_WEBSITE
            breakdown["website"] = f"+{_P2_WEBSITE}"
        elif website:
            # URL present but page wasn't scraped / empty
            score += _P2_WEBSITE // 2
            breakdown["website"] = f"+{_P2_WEBSITE // 2} (URL only, no content)"
        else:
            breakdown["website"] = "+0"

        social_present = any([
            company.get("twitter_url"),
            company.get("facebook_url"),
            company.get("instagram_url"),
            company.get("youtube_url"),
        ])
        if social_present:
            score += _P2_SOCIAL
            breakdown["social"] = f"+{_P2_SOCIAL}"
        else:
            breakdown["social"] = "+0"

        # ── Pillar 3: Business Profile Depth (max 20) ─────────────────────────
        if company.get("company_description"):
            score += _P3_DESCRIPTION
            breakdown["description"] = f"+{_P3_DESCRIPTION}"

        if company.get("company_size_range"):
            score += _P3_SIZE
            breakdown["size"] = f"+{_P3_SIZE}"

        if company.get("year_founded"):
            score += _P3_FOUNDED
            breakdown["founded"] = f"+{_P3_FOUNDED}"

        if company.get("technologies_used"):
            score += _P3_TECH_STACK
            breakdown["tech"] = f"+{_P3_TECH_STACK}"

        # ── Pillar 4: Credibility Signals (max 10) ────────────────────────────
        try:
            rating       = float(str(company.get("rating") or "0"))
            review_raw   = str(company.get("review_count") or "0")
            # Strip commas from "1,204" → "1204"
            review_count = int(review_raw.replace(",", "").strip() or "0")
        except (ValueError, TypeError):
            rating       = 0.0
            review_count = 0

        if rating > 0 and review_count >= _MIN_REVIEWS_FOR_RATING:
            if rating >= 4.5:
                score += _P4_RATING_45
                breakdown["rating"] = f"+{_P4_RATING_45} (≥4.5 with {review_count} reviews)"
            elif rating >= 4.0:
                score += _P4_RATING_40
                breakdown["rating"] = f"+{_P4_RATING_40} (≥4.0 with {review_count} reviews)"
            elif rating >= 3.5:
                score += _P4_RATING_35
                breakdown["rating"] = f"+{_P4_RATING_35} (≥3.5 with {review_count} reviews)"
            elif rating >= 3.0:
                score += _P4_RATING_30
                breakdown["rating"] = f"+{_P4_RATING_30} (≥3.0 with {review_count} reviews)"
            else:
                breakdown["rating"] = "+0 (rating < 3.0)"
        elif rating > 0:
            breakdown["rating"] = f"+0 (only {review_count} reviews — below {_MIN_REVIEWS_FOR_RATING} minimum)"
        else:
            breakdown["rating"] = "+0 (no rating)"

        # ── Hard cap at 100 ───────────────────────────────────────────────────
        score = min(score, 100)

        # ── Priority assignment ───────────────────────────────────────────────
        if score >= _THRESHOLD_HIGH:
            priority = "High"
        elif score >= _THRESHOLD_MEDIUM:
            priority = "Medium"
        else:
            priority = "Low"

        logger.debug(
            f"  [{company.get('company_name','?')}]  score={score}  priority={priority}  "
            + "  ".join(f"{k}:{v}" for k, v in breakdown.items())
        )

        # ── Build output dataclass ────────────────────────────────────────────
        return ScoredLeadCompany(
            company_name        = company.get("company_name", "Unknown"),
            address             = company.get("address"),
            location            = company.get("location"),
            industry            = company.get("industry"),
            website             = company.get("website"),
            phone               = company.get("phone"),
            category            = company.get("category"),
            rating              = company.get("rating"),
            review_count        = company.get("review_count"),
            website_title       = company.get("website_title"),
            website_description = company.get("website_description"),
            source              = company.get("source", "google_maps_detail_scrape_async"),
            emails              = company.get("emails") or [],
            primary_email       = company.get("primary_email"),
            phones_discovered   = company.get("phones_discovered") or [],
            linkedin_url        = company.get("linkedin_url"),
            twitter_url         = company.get("twitter_url"),
            facebook_url        = company.get("facebook_url"),
            instagram_url       = company.get("instagram_url"),
            youtube_url         = company.get("youtube_url"),
            contact_page_url    = company.get("contact_page_url"),
            pages_crawled       = company.get("pages_crawled", 0),
            company_size_range      = company.get("company_size_range"),
            employee_count_est      = company.get("employee_count_est"),
            year_founded            = company.get("year_founded"),
            headquarters            = company.get("headquarters"),
            company_description     = company.get("company_description"),
            technologies_used       = company.get("technologies_used") or [],
            enrichment_source       = company.get("enrichment_source"),
            data_completeness_score = company.get("data_completeness_score", 0.0),
            verified_emails         = verified,
            risky_emails            = risky,
            invalid_emails          = company.get("invalid_emails") or [],
            primary_email_status    = company.get("primary_email_status"),
            email_mx_valid          = company.get("email_mx_valid"),
            best_email              = company.get("best_email"),
            email_verification_notes= company.get("email_verification_notes"),
            lead_score              = score,
            priority                = priority,
        )


if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
