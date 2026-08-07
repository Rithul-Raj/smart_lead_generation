"""
Output Exporter
----------------
Small helper used by Module 2 (and later modules) to save a list of
BusinessCandidate results to disk as either a CSV file or a JSON file.

Why a separate file?
    Keeping "saving to disk" separate from "searching for businesses"
    is good practice - each file has ONE clear job. Module 9
    (Output Formatting & CRM Export) will later build on this same idea.
"""

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import List


def _make_output_folder(folder: str = "output") -> str:
    """Creates an 'output' folder next to your script if it doesn't exist yet."""
    os.makedirs(folder, exist_ok=True)
    return folder


def export_to_csv(candidates: List, filename: str = None, folder: str = "output") -> str:
    """
    Saves a list of BusinessCandidate objects to a CSV file.
    CSV = a simple spreadsheet-style file, opens directly in Excel/Sheets.

    Returns:
        the full path of the file that was created
    """
    if not candidates:
        raise ValueError("No candidates to export - the list is empty.")

    folder = _make_output_folder(folder)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.csv"
    filepath = os.path.join(folder, filename)

    rows = [asdict(c) for c in candidates]
    for row in rows:
        row.pop("raw", None)  # skip the messy internal debug data

    fieldnames = rows[0].keys()

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(candidates)} leads to: {filepath}")
    return filepath


def append_row_to_csv(row: dict, filepath: str) -> None:
    """
    Appends ONE row to a CSV file, writing the header first if the file
    is brand new. Used for incremental saving - call this right after each
    company is processed, instead of waiting to save everything at the end.

    Why this matters: if the script crashes or gets rate-limited halfway
    through 100 companies, you keep the 60 you already finished instead of
    losing everything.
    """
    row = dict(row)
    row.pop("raw", None)

    file_exists = os.path.isfile(filepath)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(filepath, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def export_to_json(candidates: List, filename: str = None, folder: str = "output") -> str:
    """
    Saves a list of BusinessCandidate objects to a JSON file.
    JSON = a structured text format, easy for other programs/APIs to read.

    Returns:
        the full path of the file that was created
    """
    if not candidates:
        raise ValueError("No candidates to export - the list is empty.")

    folder = _make_output_folder(folder)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.json"
    filepath = os.path.join(folder, filename)

    rows = [asdict(c) for c in candidates]
    for row in rows:
        row.pop("raw", None)

    output = {
        "total_leads": len(rows),
        "generated_at": datetime.now().isoformat(),
        "leads": rows,
    }

    with open(filepath, mode="w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(candidates)} leads to: {filepath}")
    return filepath