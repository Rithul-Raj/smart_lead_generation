"""
Module 7: AI Lead Scoring & Prioritization
--------------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
Takes the verified leads from Module 6 and calculates a final lead_score
(0-100) and assigns a lead_tier (Hot, Warm, Cold) based on data completeness
and the likelihood of the lead being reachable and qualified.

Scoring Criteria (100 points total):
  - Has Verified Email            : +25 pts
  - Has Any Email (risky)         : +10 pts (mutually exclusive with verified)
  - Has Phone Number              : +15 pts
  - Has LinkedIn URL              : +10 pts
  - Has Tech Stack                : +15 pts (indicates modern company)
  - Has Company Size/Employees    : +10 pts
  - High Data Completeness (>0.7) : +15 pts
  - High Rating (>4.0)            : +10 pts

Tiers:
  - Hot  : >= 75 (Highly reachable, full profile)
  - Warm : 50 - 74 (Missing some data, but reachable)
  - Cold : < 50 (Sparse data, hard to reach)

New fields added to every lead record:
  lead_score : int (0-100)
  lead_tier  : str ("Hot", "Warm", "Cold")
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
    Carries all fields from Module 6 (VerifiedLeadCompany) plus scoring fields.
    Passed to Module 8 (Deduplication & Quality Filtering).
    """
    # ── Module 1-5 fields ────────────────────────────────────────────────────
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
    lead_tier:                 str           = "Cold"

    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class AILeadScorer:
    """
    Module 7 — AI Lead Scoring & Prioritization.
    Calculates lead_score and lead_tier for every lead.
    """

    def score_leads(self, companies: List[Dict[str, Any]]) -> List[ScoredLeadCompany]:
        """
        Score a list of companies.
        
        Args:
            companies: list of dicts from Module 6 (VerifiedLeadCompany output).
        Returns:
            List[ScoredLeadCompany]
        """
        logger.info(f"AI Lead Scoring: processing {len(companies)} companies")
        results = []
        
        tier_counts = {"Hot": 0, "Warm": 0, "Cold": 0}

        for company in companies:
            scored_lead = self._score_company(company)
            results.append(scored_lead)
            tier_counts[scored_lead.lead_tier] += 1
            
        logger.info(
            f"Scoring complete: Hot={tier_counts['Hot']}, "
            f"Warm={tier_counts['Warm']}, Cold={tier_counts['Cold']}"
        )
        return results

    def _score_company(self, company: Dict[str, Any]) -> ScoredLeadCompany:
        score = 0
        
        # 1. Email (max 25)
        verified_emails = company.get("verified_emails") or []
        risky_emails = company.get("risky_emails") or []
        if verified_emails:
            score += 25
        elif risky_emails:
            score += 10
            
        # 2. Phone (max 15)
        phone = company.get("phone")
        phones_discovered = company.get("phones_discovered") or []
        if phone or phones_discovered:
            score += 15
            
        # 3. LinkedIn (max 10)
        if company.get("linkedin_url"):
            score += 10
            
        # 4. Tech Stack (max 15)
        technologies_used = company.get("technologies_used") or []
        if technologies_used:
            score += 15
            
        # 5. Company Size (max 10)
        if company.get("company_size_range") or company.get("employee_count_est"):
            score += 10
            
        # 6. Data Completeness (max 15)
        completeness = company.get("data_completeness_score", 0.0)
        if completeness >= 0.7:
            score += 15
        elif completeness >= 0.4:
            score += 7
            
        # 7. Rating (max 10)
        try:
            rating_str = str(company.get("rating", "0"))
            rating_float = float(rating_str)
            if rating_float >= 4.0:
                score += 10
            elif rating_float >= 3.0:
                score += 5
        except (ValueError, TypeError):
            pass
            
        # Cap score at 100 (though max sum is exactly 100 based on rules above)
        score = min(score, 100)
        
        # Determine tier
        if score >= 75:
            tier = "Hot"
        elif score >= 50:
            tier = "Warm"
        else:
            tier = "Cold"
            
        # Build dataclass
        result = ScoredLeadCompany(
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
            technologies_used       = technologies_used,
            enrichment_source       = company.get("enrichment_source"),
            data_completeness_score = completeness,
            verified_emails         = verified_emails,
            risky_emails            = risky_emails,
            invalid_emails          = company.get("invalid_emails") or [],
            primary_email_status    = company.get("primary_email_status"),
            email_mx_valid          = company.get("email_mx_valid"),
            best_email              = company.get("best_email"),
            email_verification_notes= company.get("email_verification_notes"),
            lead_score              = score,
            lead_tier               = tier
        )
        return result

if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
