"""
Module 6: Email Verification
------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

What this module does
----------------------
For every lead coming from Module 5, this module verifies ALL discovered
email addresses (the `emails` list) using a 4-tier check cascade:

  Tier 1  Syntax validation        — RFC-compliant email format regex
  Tier 2  Disposable domain check  — known temp-mail providers blocklist
  Tier 3  DNS domain resolution    — does the domain exist at all?
  Tier 4  MX record check          — does the domain have mail servers?

Each email is tagged with a status:
  "valid"         — passed all 4 tiers and is a personal/company address
  "risky"         — passed tiers 1-4 but is a generic role address
                    (info@, sales@, contact@, etc.) that may have low reply rates
  "invalid"       — failed syntax check OR domain does not exist
  "unverifiable"  — syntax OK, but DNS lookup timed out / errored

New fields added to every lead record:
  verified_emails          : List[str]  — emails that passed all checks
  risky_emails             : List[str]  — valid but role/generic addresses
  invalid_emails           : List[str]  — failed syntax or dead domain
  primary_email_status     : str        — status of the current primary_email
  email_mx_valid           : bool       — does the primary domain have MX records?
  best_email               : str        — best reachable email (verified > risky > primary)
  email_verification_notes : str        — human-readable summary

No paid API needed.
Dependencies: dnspython (optional but recommended for MX checks)
  Install: pip install dnspython
Fallback: Python socket module (domain resolution only, no MX check)
"""

import re
import socket
import logging
import functools
import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("email_verification")

# ── optional dnspython import ─────────────────────────────────────────────────
try:
    import dns.resolver
    import dns.exception
    _HAS_DNSPYTHON = True
    logger.info("dnspython available — MX record checks enabled.")
except ImportError:
    _HAS_DNSPYTHON = False
    logger.warning(
        "dnspython not installed — MX checks will use socket fallback. "
        "For better accuracy: pip install dnspython"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# RFC 5322 simplified email regex — catches most real-world valid addresses
_EMAIL_SYNTAX_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Known disposable / temporary email domains
# These are throwaway inboxes — not useful for CRM lead outreach
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com",
    "throwam.com", "yopmail.com", "tempmail.com", "dispostable.com",
    "trashmail.com", "fakeinbox.com", "sharklasers.com", "guerrillamailblock.com",
    "grr.la", "guerrillamail.info", "guerrillamail.biz", "guerrillamail.de",
    "guerrillamail.net", "guerrillamail.org", "spam4.me", "trashmail.at",
    "trashmail.io", "trashmail.me", "trashmail.net", "discard.email",
    "maildrop.cc", "mailnull.com", "spamgourmet.com", "getairmail.com",
    "tempr.email", "tempm.com", "moakt.com", "mohmal.com",
    "mintemail.com", "mailtemp.info", "dropmail.me", "33mail.com",
    "tempinbox.com", "spamfree24.org", "mailexpire.com",
})

# Generic role / department addresses — valid but impersonal
# Replies from these are less likely in a cold-email sales context
# NOTE: 'hello' and 'hi' are intentionally NOT here — many startups use
#       hello@ as their primary reachable inbox (not a department alias)
_ROLE_PREFIXES = frozenset({
    "info", "contact", "enquiry", "enquiries",
    "sales", "support", "help", "admin", "hr", "careers", "jobs",
    "feedback", "service", "office", "team", "marketing",
    "noreply", "no-reply", "donotreply", "bounce", "webmaster",
    "postmaster", "accounts", "billing", "finance", "legal",
    "privacy", "security", "press", "media", "pr", "partner",
    "partners", "reseller", "vendor", "suppliers", "procurement",
    "whistleblower", "complaints", "abuse", "spam", "newsletter",
    "unsubscribe", "notifications", "alerts", "updates", "mailer",
    "mailer-daemon", "do-not-reply",
})

# DNS / socket lookup timeout in seconds
_DNS_TIMEOUT = 5

# Max workers for parallel per-email DNS checks (one thread per email)
_MAX_WORKERS = 10


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VerifiedLeadCompany:
    """
    Full lead record after Module 6.
    Carries all fields from Module 5 (EnrichedLeadCompany) plus email
    verification fields added here.  Passed to Module 7 (AI Lead Scoring).
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

    # ── Module 6 NEW fields ──────────────────────────────────────────────────
    verified_emails:           List[str]     = field(default_factory=list)   # passed all checks
    risky_emails:              List[str]     = field(default_factory=list)   # valid but role/generic
    invalid_emails:            List[str]     = field(default_factory=list)   # failed / dead domain
    primary_email_status:      Optional[str] = None   # "valid" / "risky" / "invalid" / "unverifiable"
    email_mx_valid:            Optional[bool]= None   # True if primary domain has MX records
    best_email:                Optional[str] = None   # best reachable email
    email_verification_notes:  Optional[str] = None   # human-readable summary

    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Per-email check result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmailCheckResult:
    email:              str
    status:             str        # "valid" / "risky" / "invalid" / "unverifiable"
    syntax_ok:          bool = False
    is_disposable:      bool = False
    is_role_address:    bool = False
    domain_resolves:    bool = False
    mx_records_found:   bool = False
    failure_reason:     Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class EmailVerifier:
    """
    Module 6 — verifies all email addresses for every lead.

    Usage (called from main.py):
        verifier = EmailVerifier()
        verified_leads = verifier.verify(lead_enriched_dicts)
    """

    def __init__(self, max_workers: int = _MAX_WORKERS, dns_timeout: int = _DNS_TIMEOUT):
        self.max_workers = max_workers
        self.dns_timeout = dns_timeout
        self._domain_cache: Dict[str, Tuple[bool, bool]] = {}
        # cache: domain -> (resolves: bool, has_mx: bool)

    # ── public entry point ────────────────────────────────────────────────────

    def verify(self, companies: List[Dict[str, Any]]) -> List["VerifiedLeadCompany"]:
        """
        Verify all email addresses for a list of companies.

        Args:
            companies: list of dicts from Module 5 (EnrichedLeadCompany output).
        Returns:
            List[VerifiedLeadCompany]
        """
        logger.info(
            f"Email Verification: processing {len(companies)} companies "
            f"({self.max_workers} parallel DNS workers)"
        )

        results = []
        total_emails   = 0
        total_verified = 0

        for company in companies:
            result = self._verify_company(company)
            results.append(result)
            total_emails   += len(result.emails)
            total_verified += len(result.verified_emails)

            logger.info(
                f"  [{result.company_name}]  "
                f"emails={len(result.emails)}  "
                f"verified={len(result.verified_emails)}  "
                f"risky={len(result.risky_emails)}  "
                f"invalid={len(result.invalid_emails)}  "
                f"primary_status={result.primary_email_status or '-'}"
            )

        logger.info(
            f"Email Verification complete: "
            f"{total_verified}/{total_emails} emails verified across "
            f"{len(companies)} companies."
        )
        return results

    # ── per-company verification ──────────────────────────────────────────────

    def _verify_company(self, company: Dict[str, Any]) -> "VerifiedLeadCompany":
        """Verify all emails for one company and return a VerifiedLeadCompany."""

        result = VerifiedLeadCompany(
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
            # Module 5 fields
            company_size_range      = company.get("company_size_range"),
            employee_count_est      = company.get("employee_count_est"),
            year_founded            = company.get("year_founded"),
            headquarters            = company.get("headquarters"),
            company_description     = company.get("company_description"),
            technologies_used       = company.get("technologies_used") or [],
            enrichment_source       = company.get("enrichment_source"),
            data_completeness_score = company.get("data_completeness_score", 0.0),
        )

        if not result.emails:
            result.primary_email_status     = "no_email"
            result.email_verification_notes = "No emails found for this company."
            return result

        # Check all emails in parallel (DNS I/O bound)
        email_results = self._check_emails_parallel(result.emails)

        # Bucket into verified / risky / invalid
        for er in email_results:
            if er.status == "valid":
                result.verified_emails.append(er.email)
            elif er.status == "risky":
                result.risky_emails.append(er.email)
            else:
                result.invalid_emails.append(er.email)

        # ── Determine primary email status ────────────────────────────────────
        primary = result.primary_email
        if primary:
            primary_result = next(
                (er for er in email_results if er.email.lower() == primary.lower()),
                None
            )
            if primary_result:
                result.primary_email_status = primary_result.status
                result.email_mx_valid       = primary_result.mx_records_found
            else:
                result.primary_email_status = "unknown"

        # ── Select best_email ─────────────────────────────────────────────────
        # Priority: verified (personal) > verified (role) > risky > current primary
        if result.verified_emails:
            result.best_email = result.verified_emails[0]
        elif result.risky_emails:
            result.best_email = result.risky_emails[0]
        else:
            result.best_email = result.primary_email

        # ── Update data_completeness_score to account for email verification ──
        if result.verified_emails or result.risky_emails:
            # Email is reachable — keep or slightly boost the score
            pass
        else:
            # No reachable email — reduce completeness slightly
            result.data_completeness_score = max(
                0.0,
                round(result.data_completeness_score - 0.125, 3)
            )

        # ── Human-readable notes ──────────────────────────────────────────────
        notes_parts = []
        if result.verified_emails:
            notes_parts.append(f"{len(result.verified_emails)} verified")
        if result.risky_emails:
            notes_parts.append(f"{len(result.risky_emails)} risky (role/generic)")
        if result.invalid_emails:
            notes_parts.append(f"{len(result.invalid_emails)} invalid")
        result.email_verification_notes = (
            "; ".join(notes_parts) if notes_parts else "No emails verified."
        )

        return result

    # ── parallel DNS checking ──────────────────────────────────────────────────

    def _check_emails_parallel(self, emails: List[str]) -> List[EmailCheckResult]:
        """Check a list of emails in parallel using a thread pool (DNS I/O)."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._check_one_email, e): e for e in emails}
            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    email = futures[future]
                    results.append(EmailCheckResult(
                        email=email, status="unverifiable",
                        failure_reason=str(exc)
                    ))
        return results

    # ── per-email 4-tier check ─────────────────────────────────────────────────

    def _check_one_email(self, email: str) -> EmailCheckResult:
        """
        Run the 4-tier verification cascade for a single email address.
        Returns an EmailCheckResult with the final status.
        """
        email = email.strip().lower()
        result = EmailCheckResult(email=email, status="unknown")

        # ── Tier 1: Syntax ─────────────────────────────────────────────────────
        if not _EMAIL_SYNTAX_RE.match(email):
            result.status = "invalid"
            result.failure_reason = "invalid syntax"
            return result
        result.syntax_ok = True

        domain = email.split("@")[1]

        # ── Tier 2: Disposable domain ──────────────────────────────────────────
        if domain in _DISPOSABLE_DOMAINS:
            result.is_disposable = True
            result.status = "invalid"
            result.failure_reason = "disposable / temporary email domain"
            return result

        # ── Tier 3: Domain DNS resolution ─────────────────────────────────────
        domain_resolves, has_mx = self._check_domain(domain)
        result.domain_resolves = domain_resolves
        result.mx_records_found = has_mx

        if not domain_resolves:
            result.status = "invalid"
            result.failure_reason = "domain does not resolve (DNS lookup failed)"
            return result

        # ── Tier 4: Role / generic address check ──────────────────────────────
        local_part = email.split("@")[0]
        result.is_role_address = local_part in _ROLE_PREFIXES

        # ── Final status ───────────────────────────────────────────────────────
        if not domain_resolves:
            result.status = "invalid"
        elif not has_mx:
            # Domain resolves (A record) but no mail server — unverifiable
            result.status = "unverifiable"
            result.failure_reason = "domain has no MX records (mail server not found)"
        elif result.is_role_address:
            result.status = "risky"
        else:
            result.status = "valid"

        return result

    # ── domain DNS helpers ────────────────────────────────────────────────────

    def _check_domain(self, domain: str) -> Tuple[bool, bool]:
        """
        Check if a domain:
          - resolves at all (A/AAAA record lookup via socket)
          - has MX records (mail servers configured)

        Returns (resolves: bool, has_mx: bool)
        Results are cached so the same domain is never checked twice in a run.
        """
        if domain in self._domain_cache:
            return self._domain_cache[domain]

        resolves = False
        has_mx   = False

        # Domain resolution check (socket — always available)
        try:
            socket.setdefaulttimeout(self.dns_timeout)
            socket.getaddrinfo(domain, None)
            resolves = True
        except (socket.gaierror, socket.timeout, OSError):
            resolves = False

        # MX record check
        if resolves:
            if _HAS_DNSPYTHON:
                has_mx = self._check_mx_dnspython(domain)
            else:
                # Fallback: if domain resolves but we can't check MX,
                # assume MX exists (optimistic fallback to avoid over-blocking)
                has_mx = True

        self._domain_cache[domain] = (resolves, has_mx)
        return resolves, has_mx

    def _check_mx_dnspython(self, domain: str) -> bool:
        """Use dnspython to check for MX records. Returns True if MX records found."""
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout  = self.dns_timeout
            resolver.lifetime = self.dns_timeout
            answers = resolver.resolve(domain, "MX")
            return len(answers) > 0
        except (dns.exception.DNSException, Exception):
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Standalone usage note
# ─────────────────────────────────────────────────────────────────────────────
# Run the full pipeline:
#     python main.py
#
# To test this module in isolation:
#     from email_verification import EmailVerifier
#     import json
#     with open("output/current/current_leads.json") as f:
#         data = json.load(f)
#     results = EmailVerifier().verify(data["leads"])
#     for r in results:
#         print(r.company_name, r.best_email, r.primary_email_status,
#               r.verified_emails, r.invalid_emails)
#
if __name__ == "__main__":
    print("Run 'python main.py' to launch the full pipeline.")
    print("See the comment block above for isolation testing.")
