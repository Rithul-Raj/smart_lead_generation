"""
Output Exporter  --  Smart Lead Generation AI Model
----------------------------------------------------
Handles ALL file I/O for the pipeline.

Folder structure
-----------------
  output/
    current/
        current_leads.csv       -- this run's results (CSV)
        current_leads.json      -- this run's results (JSON)
        current_leads_live.csv  -- live scraping buffer (Module 3)
    master/
        master_leads.csv        -- all-time accumulated data (CSV)
        master_leads.json       -- all-time accumulated data (JSON)

Merge behaviour
----------------
  After every run, current data is immediately merged into master,
  so master is ALWAYS up to date after each pipeline run.
  Merging deduplicates by company_name + address (or place_id).
"""

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import List

# ── path constants ──────────────────────────────────────────────────────────
OUTPUT_DIR      = "output"
CURRENT_DIR     = os.path.join(OUTPUT_DIR, "current")
MASTER_DIR      = os.path.join(OUTPUT_DIR, "master")

CURRENT_CSV     = os.path.join(CURRENT_DIR, "current_leads.csv")
CURRENT_JSON    = os.path.join(CURRENT_DIR, "current_leads.json")
MASTER_CSV      = os.path.join(MASTER_DIR,  "master_leads.csv")
MASTER_JSON     = os.path.join(MASTER_DIR,  "master_leads.json")
LIVE_BUFFER_CSV = os.path.join(CURRENT_DIR, "current_leads_live.csv")


# ── internal helpers ────────────────────────────────────────────────────────

def _ensure_output_dir() -> None:
    """Create output/current/ and output/master/ if they don't exist yet."""
    os.makedirs(CURRENT_DIR, exist_ok=True)
    os.makedirs(MASTER_DIR,  exist_ok=True)


def _rows_from_dataclasses(candidates: List) -> List[dict]:
    """Convert a list of dataclass instances to plain dicts, stripping 'raw'."""
    rows = []
    for c in candidates:
        row = asdict(c) if hasattr(c, "__dataclass_fields__") else dict(c)
        row.pop("raw", None)
        rows.append(row)
    return rows


def _flatten_for_csv(row: dict) -> dict:
    """
    CSV cells cannot hold Python lists. Convert any list values to a
    pipe-separated string so they fit in a single cell and remain readable.

    Example:
        ["info@acme.com", "ceo@acme.com"]  ->  "info@acme.com|ceo@acme.com"
        []                                 ->  ""  (empty string)

    JSON output is NOT affected by this — lists stay as proper JSON arrays.
    """
    flat = {}
    for k, v in row.items():
        if isinstance(v, list):
            flat[k] = "|".join(str(item) for item in v) if v else ""
        else:
            flat[k] = v
    return flat


def _write_csv(rows: List[dict], filepath: str) -> None:
    if not rows:
        return
    flat_rows = [_flatten_for_csv(r) for r in rows]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flat_rows[0].keys())
        writer.writeheader()
        writer.writerows(flat_rows)


def _write_json(rows: List[dict], filepath: str, meta: dict = None) -> None:
    payload = {
        "total_leads": len(rows),
        "generated_at": datetime.now().isoformat(),
    }
    if meta:
        payload.update(meta)
    payload["leads"] = rows
    with open(filepath, mode="w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _load_json_rows(filepath: str) -> List[dict]:
    """Load leads from a JSON file; returns [] if file doesn't exist."""
    if not os.path.isfile(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("leads", [])


def _dedup_key(row: dict) -> str:
    """
    Deduplication key for master merging.
    Uses company_name + address (lower-cased, stripped).
    If place_id is present, prefer that (more reliable).
    """
    if row.get("place_id"):
        return str(row["place_id"]).strip().lower()
    name = str(row.get("company_name") or "").strip().lower()
    addr = str(row.get("address") or "").strip().lower()
    return f"{name}|{addr}"


# ── public API ───────────────────────────────────────────────────────────────

def save_current_output(candidates: List, search_params: dict = None) -> None:
    """
    Save the results of the LATEST run to current_leads.csv + current_leads.json.
    Both files are OVERWRITTEN completely each time.

    Args:
        candidates   : list of dataclass objects (e.g. EnrichedCompany) OR plain dicts.
        search_params: optional dict with the search parameters used this run
                       (e.g. {"location": "Bangalore", "industry": "IT", "num_leads": 10}).
                       Stored in the JSON for reference.
    """
    _ensure_output_dir()
    rows = _rows_from_dataclasses(candidates)

    _write_csv(rows, CURRENT_CSV)
    _write_json(rows, CURRENT_JSON, meta={"search_params": search_params or {}})

    print(f"[OK] Current output saved  ->  {len(rows)} leads")
    print(f"     CSV : {CURRENT_CSV}")
    print(f"     JSON: {CURRENT_JSON}")


def merge_current_to_master() -> int:
    """
    Merge current_leads.json into master_leads.json + master_leads.csv.

    - Reads all existing master rows.
    - Reads all current rows.
    - Deduplicates by (place_id OR company_name+address).
    - Writes the merged set back to both master files.

    Returns:
        Number of NEW records that were added to master this call.
    """
    _ensure_output_dir()

    master_rows = _load_json_rows(MASTER_JSON)
    current_rows = _load_json_rows(CURRENT_JSON)

    if not current_rows:
        print("ℹ  No current_leads.json found — nothing to merge into master.")
        return 0

    # Build a seen-set from existing master rows
    seen = {_dedup_key(r) for r in master_rows}

    new_count = 0
    for row in current_rows:
        key = _dedup_key(row)
        if key not in seen:
            master_rows.append(row)
            seen.add(key)
            new_count += 1

    # Add a merge timestamp to each newly-added row for traceability
    now_iso = datetime.now().isoformat()
    for row in master_rows[-new_count:] if new_count else []:
        row.setdefault("merged_at", now_iso)

    _write_json(master_rows, MASTER_JSON,
                meta={"last_merged_at": now_iso})
    if master_rows:
        _write_csv(master_rows, MASTER_CSV)

    print(f"[OK] Master updated  ->  {new_count} new records added  "
          f"(total: {len(master_rows)} leads)")
    print(f"     CSV : {MASTER_CSV}")
      
    print(f"     JSON: {MASTER_JSON}")
    return new_count


def append_row_to_csv(row: dict, filepath: str = LIVE_BUFFER_CSV) -> None:
    """
    Appends ONE row to a CSV file immediately after it's scraped.
    Used by Module 3 for incremental live-saving so data isn't lost
    if the script crashes mid-run.

    Creates the file (with header) if it doesn't exist yet.

    Args:
        row     : plain dict — one lead's data.
        filepath: destination CSV path (defaults to the live scraping buffer).
    """
    row = dict(row)
    row.pop("raw", None)
    row = _flatten_for_csv(row)   # convert any list fields to pipe-separated strings

    _ensure_output_dir()
    file_exists = os.path.isfile(filepath)

    with open(filepath, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ── legacy shims (kept so old standalone test runs still work) ───────────────

def export_to_csv(candidates: List, filename: str = None, folder: str = OUTPUT_DIR) -> str:
    """
    Legacy helper — kept for backward-compatibility with old standalone
    test blocks in Module 2 / 3. New code should call save_current_output().
    """
    _ensure_output_dir()
    if not candidates:
        raise ValueError("No candidates to export.")
    rows = _rows_from_dataclasses(candidates)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.csv"
    filepath = os.path.join(folder, filename)
    _write_csv(rows, filepath)
    print(f"Saved {len(rows)} leads to: {filepath}")
    return filepath


def export_to_json(candidates: List, filename: str = None, folder: str = OUTPUT_DIR) -> str:
    """
    Legacy helper — kept for backward-compatibility with old standalone
    test blocks in Module 2 / 3. New code should call save_current_output().
    """
    _ensure_output_dir()
    if not candidates:
        raise ValueError("No candidates to export.")
    rows = _rows_from_dataclasses(candidates)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.json"
    filepath = os.path.join(folder, filename)
    _write_json(rows, filepath)
    print(f"Saved {len(rows)} leads to: {filepath}")
    return filepath