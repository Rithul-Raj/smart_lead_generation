"""
main.py  —  Smart Lead Generation AI Model
-------------------------------------------
Detagenix Internship Project

This is the SINGLE ENTRY POINT for the entire pipeline.
Run this file to start the lead generation process:

    python main.py

Pipeline flow
-------------
  Step 0  Merge previous current_leads → master_leads
          (so master always has everything before we overwrite current)

  Step 1  Show GUI input form → collect search parameters from user

  Step 2  Module 2 — Business Search Engine
          Discovers business candidates on Google Maps (no API key needed).

  Step 3  Module 3 — Company Data Extraction
          Opens each candidate's Maps page and scrapes: website, phone,
          address, category, rating, review count, website title/description.

  Step 5  Module 4 -- Contact Discovery
          Crawls each company's website and extracts: emails, extra phone
          numbers, LinkedIn / social media links, contact page URL.

  Step 6  Save current results
          output/current/current_leads.csv  <- this run's results
          output/current/current_leads.json <- this run's results

  Step 7  Merge current into master (immediately, every run)
          output/master/master_leads.csv    <- all-time accumulated data
          output/master/master_leads.json   <- all-time accumulated data
          Master is ALWAYS up to date after every run.

Adding future modules
---------------------
  Import the new module at the top of this file and call it inside
  run_pipeline() in the appropriate step. The rest of the flow stays the same.
"""

import sys
import logging
from dataclasses import asdict

# ── project modules ───────────────────────────────────────────────────────────
from input_form import LeadInputForm
from business_search_engine_playwright import BusinessSearchEnginePlaywright
from company_data_extraction_async import AsyncCompanyDataExtractor
from contact_discovery import ContactDiscovery
from output_exporter import (
    save_current_output,
    merge_current_to_master,
    CURRENT_JSON,
)

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("main")

BANNER = """
+===========================================================+
|   SMART LEAD GENERATION AI MODEL  --  Detagenix           |
+===========================================================+
"""


def run_pipeline(params: dict) -> None:
    """
    Runs the lead generation pipeline with the given search parameters.

    Args:
        params: dict with keys  num_leads (int), location (str), industry (str)
    """
    num_leads = params["num_leads"]
    location  = params["location"]
    industry  = params["industry"]

    print(BANNER)
    print(f"  Search parameters")
    print(f"  -----------------------------------------")
    print(f"  Leads     : {num_leads}")
    print(f"  Location  : {location}")
    print(f"  Industry  : {industry}")
    print()

    # (Step 0 removed -- master is now updated at the END of every run instead,
    #  so it is always current without needing to wait for the next run.)

    # ── Step 1 (already done — params came from the GUI form) ────────────────
    logger.info("Step 1 — User input collected via GUI ✔")
    print()

    # ── Step 2: Business Search Engine ───────────────────────────────────────
    logger.info("Step 2 — Module 2: Business Search Engine starting …")
    engine = BusinessSearchEnginePlaywright(headless=True)
    candidates = engine.search(
        num_leads=num_leads,
        location=location,
        industry=industry,
    )

    if not candidates:
        logger.warning("No candidates found. Exiting.")
        return

    logger.info(f"Step 2 ✔  Found {len(candidates)} candidates.")
    print()

    # ── Step 3: Company Data Extraction ──────────────────────────────────────
    logger.info("Step 3 — Module 3: Company Data Extraction starting …")
    extractor = AsyncCompanyDataExtractor(headless=True, concurrency=3)

    # Feed Module 3 the list of dicts from Module 2
    candidate_dicts = [
        {k: v for k, v in asdict(c).items() if k != "raw"}
        for c in candidates
    ]
    enriched = extractor.enrich(candidate_dicts)

    if not enriched:
        logger.warning("Extraction returned no results. Exiting.")
        return

    logger.info(f"Step 3 ✔  Enriched {len(enriched)} companies.")
    print()

    # ── Step 5: Contact Discovery ─────────────────────────────────────────────
    logger.info("Step 5 - Module 4: Contact Discovery starting ...")
    discoverer = ContactDiscovery(headless=True, concurrency=3)

    # Convert Module 3's dataclass objects to plain dicts for Module 4
    enriched_dicts = [
        {k: v for k, v in asdict(c).items() if k != "raw"}
        for c in enriched
    ]
    contact_enriched = discoverer.discover(enriched_dicts)

    logger.info(f"Step 5 [OK]  Contact discovery done for {len(contact_enriched)} companies.")
    print()

    # ── Step 6: Save current output ──────────────────────────────────────────
    logger.info("Step 6 - Saving current output files ...")
    save_current_output(contact_enriched, search_params=params)
    print()

    # ── Step 7: Merge current into master IMMEDIATELY ───────────────────────
    # Master is updated right now, not deferred to the next run.
    # This means master is ALWAYS fully up to date after every single run.
    logger.info("Step 7 - Merging current leads into master ...")
    merge_current_to_master()
    print()

    # Count companies where at least one contact field was found
    contacts_found = sum(
        1 for c in contact_enriched
        if c and (c.emails or c.linkedin_url or c.phones_discovered)
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("=" * 60)
    print(f"  [DONE]  Pipeline complete!")
    print(f"  -----------------------------------------")
    print(f"  Candidates found   : {len(candidates)}")
    print(f"  Companies enriched : {len(enriched)}")
    print(f"  Contacts found     : {contacts_found}/{len(contact_enriched)}")
    print()
    print("  Output files:")
    print("  * output/current/current_leads.csv   <- this run's results")
    print("  * output/current/current_leads.json  <- this run's results (JSON)")
    print("  * output/master/master_leads.csv     <- all-time accumulated data")
    print("  * output/master/master_leads.json    <- all-time accumulated data (JSON)")
    print("=" * 60)

    # ── Future modules placeholders ───────────────────────────────────────────
    # TODO Step 7:  Module 5 -- Lead Data Enrichment
    # TODO Step 8:  Module 6 -- Email Verification
    # TODO Step 9:  Module 7 -- AI Lead Scoring
    # TODO Step 10: Module 8 -- Deduplication & Quality Filtering
    # TODO Step 11: Module 9 -- Output Formatting & CRM Export


def main() -> None:
    """Application entry point."""

    # ── Show GUI input form ───────────────────────────────────────────────────
    logger.info("Opening input form …")
    form   = LeadInputForm()
    params = form.run()

    if params is None:
        print("Search cancelled by user. Exiting.")
        sys.exit(0)

    logger.info(
        f"Inputs received — leads={params['num_leads']}, "
        f"location='{params['location']}', industry='{params['industry']}'"
    )

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        run_pipeline(params)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
