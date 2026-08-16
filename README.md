# Smart Lead Generation AI Model

> **Detagenix Internship Project — P1**
> An end-to-end AI-powered lead acquisition pipeline that discovers, enriches, verifies, scores, and exports qualified business leads with zero manual effort.

---

## Overview

The Smart Lead Generation model automatically generates qualified B2B leads based on user-defined search criteria (location, industry, number of leads). It collects business data from Google Maps, enriches it by crawling company websites, verifies contact details, scores every lead using AI, and delivers clean CRM-ready output — all from a single `python main.py` command.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the pipeline

```bash
python main.py
```

A **GUI input form** will open. Fill in:
- **Location** (e.g. `Bangalore`, `Kerala`)
- **Industry** (e.g. `IT company`, `Construction`)
- **Number of leads** to search for

The pipeline runs all 9 modules automatically and saves results to `output/`.

---

## Output Files

Only **two output files** are maintained at all times:

| File | Description |
|------|-------------|
| `output/current/current_leads.csv` | This run's results (CRM-ready CSV) |
| `output/current/current_leads.json` | This run's results (JSON with request_id) |
| `output/master/master_leads.csv` | All-time accumulated leads (CRM-ready CSV) |
| `output/master/master_leads.json` | All-time accumulated leads (JSON) |

> **Master is updated immediately after every run.** Duplicates are automatically removed across runs.

---

## JSON Output Structure

Matches the project specification (Section 20):

```json
{
  "request_id": "LG-20260810-171200",
  "location": "Bangalore",
  "industry": "Information Technology",
  "total_leads": 10,
  "generated_at": "2026-08-10T17:12:00.123456",
  "leads": [
    {
      "Priority": "High",
      "Lead Score": "94",
      "Email": "info@abctech.com",
      "Phone": "+91 98765 43210",
      "Company Name": "ABC Technologies",
      "Website": "www.abctech.com",
      "Industry": "Information Technology",
      "Search Location": "Bangalore",
      "Google Rating": "4.5"
    }
  ]
}
```

---

## CSV Output Columns

The final CRM-ready CSV contains **15 clean columns** (no internal pipeline fields):

| # | Column | Description |
|---|--------|-------------|
| 1 | Priority | High / Medium / Low (AI-determined) |
| 2 | Lead Score | 0–100 (4-pillar AI scoring) |
| 3 | Email | Best available email (verified → role → fallback) |
| 4 | Phone | Google Maps-listed phone |
| 5 | Additional Phones | Extra phones found on website |
| 6 | Company Name | |
| 7 | Business Category | Google Maps category |
| 8 | Industry | User's search term |
| 9 | Search Location | User's search location |
| 10 | Full Address | |
| 11 | Website | |
| 12 | Company Size | Employee range (e.g. 51–200) |
| 13 | Year Founded | |
| 14 | Company Description | From website/LinkedIn |
| 15 | Google Rating | Maps star rating |

---

## Pipeline — 9 Modules

```
User Input → Search → Extract → Contacts → Enrich → Verify → Score → Dedup → Format → Output
  M1          M2       M3         M4         M5       M6       M7     M8      M9
```

### Module 1 — Input Form (`input_form.py`)
GUI form built with `tkinter`. Collects location, industry, number of leads, and headless browser preference.

### Module 2 — Business Search Engine (`business_search_engine_playwright.py`)
Discovers business candidates on Google Maps using Playwright. No API key required. Returns a list of candidate companies with name, address, Maps URL.

### Module 3 — Company Data Extraction (`company_data_extraction_async.py`)
Opens each company's Google Maps listing and scrapes: website, phone, address, category, rating, review count. Uses async Playwright with concurrent workers for speed.

### Module 4 — Contact Discovery (`contact_discovery.py`)
Crawls each company's website to find: emails, extra phone numbers, LinkedIn profile, social media links, contact page URL.

### Module 5 — Lead Data Enrichment (`lead_data_enrichment.py`)
Visits company websites and LinkedIn public pages to extract: company size range, year founded, headquarters, company description, technology stack. Calculates a `data_completeness_score` (0.0–1.0).

### Module 6 — Email Verification (`email_verification.py`)
4-tier email verification cascade:
1. **Syntax check** — RFC-compliant format validation
2. **Disposable domain check** — rejects throwaway email providers
3. **DNS resolution** — confirms the domain exists
4. **MX record lookup** — confirms the domain accepts mail (via `dnspython`)

Outputs: `verified_emails`, `risky_emails` (role/generic), `invalid_emails`, `best_email`.

### Module 7 — AI Lead Scoring (`ai_lead_scoring.py`)
Scores every lead 0–100 using a **4-pillar model**:

| Pillar | Max | Signals |
|--------|-----|---------|
| Contact Reachability | 40 | Verified email (+30), role email (+15), phone (+10) |
| Digital Presence | 30 | LinkedIn (+15), website with content (+8), social media (+7) |
| Business Profile Depth | 20 | Description (+5), size (+5), founded (+5), tech stack (+5) |
| Credibility | 10 | Google Rating ≥4.5 (+10), ≥4.0 (+7), ≥3.5 (+4), ≥3.0 (+2) |

> Rating only counts when the company has ≥10 reviews (prevents fake single-star inflation).

**Priority tiers:**
- 🔴 **High** (score ≥ 70) — Prioritise for immediate outreach
- 🟡 **Medium** (score 40–69) — Nurture track
- ⚪ **Low** (score < 40) — Monitor / low effort

**All leads appear in output** regardless of score — ranked best-first. No leads are silently dropped.

### Module 8 — Deduplication (`lead_filtering.py`)
Removes intra-run duplicate leads only (same website domain, LinkedIn URL, or phone number). Cross-run deduplication (against master) happens automatically in the output exporter.

### Module 9 — CRM Export (`crm_exporter.py`)
Transforms internal pipeline data into clean, human-readable CRM rows:
- Renames snake_case fields to proper column headers
- Drops all internal/pipeline-only fields
- Smart email column (best_email → verified → risky → primary fallback)
- Lists formatted as comma-separated strings
- Output is directly importable into HubSpot, Salesforce, Zoho, etc.

---

## Folder Structure

```
P1-smart_lead_generation/
├── main.py                              ← Single entry point
├── requirements.txt                     ← Python dependencies
│
├── input_form.py                        ← Module 1: GUI
├── business_search_engine_playwright.py ← Module 2: Google Maps search
├── company_data_extraction_async.py     ← Module 3: Maps data extraction
├── contact_discovery.py                 ← Module 4: Email & contact crawl
├── lead_data_enrichment.py              ← Module 5: Website/LinkedIn enrichment
├── email_verification.py                ← Module 6: 4-tier email verification
├── ai_lead_scoring.py                   ← Module 7: AI scoring (0–100)
├── lead_filtering.py                    ← Module 8: Deduplication
├── crm_exporter.py                      ← Module 9: CRM output formatting
├── output_exporter.py                   ← File I/O: save & merge outputs
│
└── output/
    ├── current/
    │   ├── current_leads.csv            ← This run's CRM-ready results
    │   └── current_leads.json           ← This run's results (JSON)
    └── master/
        ├── master_leads.csv             ← All-time accumulated data
        └── master_leads.json            ← All-time data (JSON)
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13 |
| Browser Automation | Playwright (Chromium) |
| HTML Parsing | BeautifulSoup4 |
| Email DNS Verification | dnspython |
| GUI | tkinter (stdlib) |
| Data Format | CSV + JSON |
| Concurrency | asyncio + ThreadPoolExecutor |

---

## Integration

The output files are directly importable into any CRM:
- **HubSpot** — Import `current_leads.csv` via Contacts > Import
- **Salesforce** — Data Import Wizard with the CSV
- **Zoho CRM** — Import via the Leads module
- **Excel / Google Sheets** — Open CSV directly
