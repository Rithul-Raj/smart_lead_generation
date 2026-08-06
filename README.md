# Smart Lead Generation — AI/ML Model

Internship project at **Detagenix** | AI/ML Developer Intern

An AI-powered lead acquisition system that automatically finds business leads based on user-defined criteria (number of leads, location, industry), instead of manual research. This repo currently contains **Module 2: Business Search Engine**.

---

## 📌 Project Overview

The full Smart Lead Generation system is built as 9 modules:

| # | Module | Status |
|---|--------|--------|
| 1 | User Input Collection | Not started |
| 2 | **Business Search Engine** | ✅ Done |
| 3 | Company Data Extraction | Not started |
| 4 | Contact Discovery | Not started |
| 5 | Lead Data Enrichment | Not started |
| 6 | Email Verification | Not started |
| 7 | AI Lead Scoring | Not started |
| 8 | Deduplication & Quality Filtering | Not started |
| 9 | Output Formatting & CRM Export | Not started |

---

## ✅ Module 2: Business Search Engine

**Goal:** Given `number of leads`, `location`, and `industry`, find real candidate companies matching the criteria and hand off a clean, de-duplicated list to Module 3.

Two working versions are included:

### 1. `business_search_engine.py` — Google Places API version
- Uses Google's official Places API (Text Search).
- Reliable, structured, official data.
- Requires a **Google Places API key** (needs a Google Cloud billing account, though usage stays within the free tier for small tests).
- Falls back automatically to **mock mode** (sample data) if no API key is set, so the pipeline can still be developed/tested without one.

### 2. `business_search_engine_playwright.py` — Browser automation version (no billing needed)
- Uses [Playwright](https://playwright.dev/) to open a real Chrome browser, search Google Maps, scroll through results, and read business names/addresses directly off the page.
- **No API key or billing required.**
- More fragile than the API version — Google's page layout can change, which may require updating the CSS selectors used to find business names/addresses.
- Automatically exports results to CSV and JSON on each run.

### `output_exporter.py` — Export helper
- Shared by both versions.
- Saves the list of leads found to:
  - `output/leads_<timestamp>.csv` — spreadsheet-friendly
  - `output/leads_<timestamp>.json` — structured, for downstream modules

---

## 🛠️ Setup

### Requirements
- Python 3.10+
- VS Code (or any code editor)

### Install dependencies
```bash
pip install requests playwright
playwright install chromium
```

### Option A — Run with Playwright (no API key needed)
```bash
python business_search_engine_playwright.py
```
A Chrome window will open, search Google Maps, and collect results. CSV/JSON files will be saved automatically in the `output/` folder.

### Option B — Run with Google Places API
1. Get an API key from [Google Cloud Console](https://console.cloud.google.com/) → enable **Places API**.
2. Set it as an environment variable:
   ```bash
   export GOOGLE_PLACES_API_KEY="your_key_here"      # Mac/Linux
   setx GOOGLE_PLACES_API_KEY "your_key_here"         # Windows
   ```
3. Run:
   ```bash
   python business_search_engine.py
   ```
Without an API key set, this automatically runs in **mock mode** and returns sample data for testing.

---

## 📂 Project Structure

```
smart-lead-generation/
├── business_search_engine.py            # Module 2 - Google Places API version
├── business_search_engine_playwright.py # Module 2 - Playwright/no-API version
├── output_exporter.py                   # Shared CSV/JSON export helper
├── output/                               # Generated lead files (git-ignored)
├── .gitignore
└── README.md
```

---

## 🔄 How this fits the bigger pipeline

```
Module 1 (User Input) 
   → Module 2 (Business Search Engine)  ← this repo
   → Module 3 (Company Data Extraction)
   → Module 4 (Contact Discovery)
   → ... → Module 9 (CRM Export)
```

Module 2 outputs a list of candidates with:
```json
{
  "company_name": "ABC Technologies",
  "address": "123 Main St, Bangalore",
  "location": "Bangalore, India",
  "industry": "Information Technology"
}
```
This becomes the input for Module 3, which will enrich each company with website, phone number, and company size.

---

## 📝 Notes / Next Steps
- Decide between API version vs. Playwright version for production use (cost vs. reliability trade-off).
- Begin Module 3: Company Data Extraction, using this module's output as input.
