"""
Google Sheets integration module.

Google Sheets serves as the single source of truth - both data store and output.
No local JSON files. All state lives in the Deals tab.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import time
from datetime import date, datetime
from typing import Optional


# Column headers for the 4 tabs
DEALS_HEADERS = [
    "PG Account Name", "Clean Name", "Acquiror", "Target",
    "Deal Status", "Sector", "Description",
    "Date of Rumor", "Date of Announcement", "Date Closed",
    "Deal Value ($)", "Source", "Source Link",
    "Potential Opportunity for PG", "Source Validation",
    # Hidden metadata columns (P onwards)
    "deal_id", "stages_reported", "first_seen", "last_updated", "scan_period"
]

EXCLUDED_HEADERS = [
    "Acquiror", "Target", "Deal Value ($)", "Sector",
    "Description", "Exclusion Reason", "Date Found", "scan_period"
]

UNVERIFIED_HEADERS = [
    "Acquiror", "Target", "Deal Status", "Sector", "Description",
    "Original URL Attempted", "Validation Failure Reason",
    "Date Found", "scan_period"
]


def get_sheets_client() -> gspread.Client:
    """
    Authenticate with Google Sheets using a service account.

    Reads credentials from GOOGLE_SERVICE_ACCOUNT_JSON environment variable.
    In local dev: reads from .env file
    In GitHub Actions: reads from secret injected as env var

    Returns:
        Authenticated gspread Client

    Raises:
        ValueError: If GOOGLE_SERVICE_ACCOUNT_JSON not set or invalid
        Exception: If authentication fails
    """
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set. "
            "Please set it in your .env file or GitHub Secrets."
        )

    try:
        # Parse JSON string to dict
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}"
        )
    except Exception as e:
        raise Exception(f"Failed to create credentials: {e}")

    try:
        client = gspread.authorize(creds)
    except Exception as e:
        raise Exception(f"Failed to authorize with Google Sheets: {e}")

    return client


def open_sheet() -> gspread.Spreadsheet:
    """
    Open the PG M&A Scanner Google Sheet.

    Returns:
        gspread Spreadsheet object

    Raises:
        ValueError: If GOOGLE_SHEET_ID not set
        gspread.exceptions.SpreadsheetNotFound: If sheet doesn't exist or not shared
    """
    client = get_sheets_client()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")

    if not sheet_id:
        raise ValueError(
            "GOOGLE_SHEET_ID environment variable not set. "
            "Please set it in your .env file or GitHub Secrets."
        )

    try:
        spreadsheet = client.open_by_key(sheet_id)
    except gspread.exceptions.SpreadsheetNotFound:
        raise gspread.exceptions.SpreadsheetNotFound(
            f"Spreadsheet with ID '{sheet_id}' not found. "
            f"Ensure the sheet exists and is shared with your service account email."
        )

    return spreadsheet


def ensure_sheet_structure(spreadsheet: gspread.Spreadsheet) -> None:
    """
    Create tabs and headers if they don't exist.
    Safe to call on every run - idempotent.

    Creates 4 tabs:
    - Executive Summary (free-form, rebuilt each run)
    - Deals (15 output fields + 5 metadata fields)
    - Excluded (Non-Strategic) (8 fields)
    - Unverified (7 fields)

    Args:
        spreadsheet: gspread Spreadsheet object
    """
    tab_configs = {
        "Executive Summary": [],  # Free-form, rebuilt each run
        "Deals": DEALS_HEADERS,
        "Excluded (Non-Strategic)": EXCLUDED_HEADERS,
        "Unverified": UNVERIFIED_HEADERS,
    }

    existing_tabs = [ws.title for ws in spreadsheet.worksheets()]

    for tab_name, headers in tab_configs.items():
        if tab_name not in existing_tabs:
            # Create new tab
            ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=25)

            if headers:
                # Add header row
                ws.append_row(headers)

                # Format header row: bold, dark blue background, white text
                ws.format("1:1", {
                    "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1}
                    },
                })

                # Freeze header row
                ws.freeze(rows=1)

                # Hide metadata columns for Deals tab (columns P-T)
                if tab_name == "Deals":
                    # Hide columns 16-20 (P-T): deal_id, stages_reported, first_seen, last_updated, scan_period
                    requests = [{
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": ws.id,
                                "dimension": "COLUMNS",
                                "startIndex": 15,  # Column P (0-indexed)
                                "endIndex": 20     # Up to but not including column U
                            },
                            "properties": {
                                "hiddenByUser": True
                            },
                            "fields": "hiddenByUser"
                        }
                    }]
                    spreadsheet.batch_update({"requests": requests})

        else:
            # Tab exists - verify headers are present
            ws = spreadsheet.worksheet(tab_name)
            if headers:
                existing_headers = ws.row_values(1)
                if not existing_headers or existing_headers != headers:
                    # Update headers if missing or different
                    ws.update('1:1', [headers])

            # Ensure metadata columns are hidden for existing Deals tab
            if tab_name == "Deals":
                requests = [{
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": 15,  # Column P (0-indexed)
                            "endIndex": 20     # Up to but not including column U
                        },
                        "properties": {
                            "hiddenByUser": True
                        },
                        "fields": "hiddenByUser"
                    }
                }]
                spreadsheet.batch_update({"requests": requests})


def load_existing_deals(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    """
    Read all existing deals from the Deals tab.

    Returns list of dicts with all 15 fields + metadata.
    Used by dedup.py to determine what's already been reported.

    Args:
        spreadsheet: gspread Spreadsheet object

    Returns:
        List of deal dicts, or empty list if Deals tab doesn't exist
    """
    try:
        ws = spreadsheet.worksheet("Deals")
        records = ws.get_all_records()
        return records
    except gspread.exceptions.WorksheetNotFound:
        return []


def build_dedup_state(existing_deals: list[dict]) -> dict:
    """
    Convert the flat list of Sheets rows into the dedup state dict.

    Keyed by deal_id, tracks stages_reported.
    This replaces load_state() from the old deal_state.json approach.

    Args:
        existing_deals: List of dicts from load_existing_deals()

    Returns:
        Dict keyed by deal_id with structure:
        {
            "deal_id": {
                "acquiror": str,
                "target": str,
                "deal_id": str,
                "stages_reported": list[str],
                "first_seen": str,
                "last_updated": str,
                "current_status": str
            }
        }
    """
    from dedup import generate_deal_id  # Import here to avoid circular dependency

    state = {}

    for deal in existing_deals:
        deal_id = deal.get("deal_id", "")

        # Generate deal_id if missing (for legacy data)
        if not deal_id:
            deal_id = generate_deal_id(
                deal.get("Acquiror", ""), deal.get("Target", "")
            )

        if deal_id not in state:
            # Parse stages_reported (stored as comma-separated string)
            stages_str = deal.get("stages_reported", "")
            stages_reported = [s.strip() for s in stages_str.split(",") if s.strip()]

            state[deal_id] = {
                "acquiror": deal.get("Acquiror", ""),
                "target": deal.get("Target", ""),
                "deal_id": deal_id,
                "stages_reported": stages_reported,
                "first_seen": deal.get("first_seen", ""),
                "last_updated": deal.get("last_updated", ""),
                "current_status": deal.get("Deal Status", "")
            }
        else:
            # Deal already exists in state - update stages_reported if needed
            status = deal.get("Deal Status", "").lower()
            if status and status not in state[deal_id]["stages_reported"]:
                state[deal_id]["stages_reported"].append(status)

    return state


def append_new_deals(
    spreadsheet: gspread.Spreadsheet,
    new_deals: list[dict],
    scan_period: str
) -> None:
    """
    Append new deals to the Deals tab.

    Inserts at row 2 (just below headers) so newest deals appear at the top.
    Applies yellow highlighting to new rows.

    Args:
        spreadsheet: gspread Spreadsheet object
        new_deals: List of deal dicts
        scan_period: Period string (e.g., "last_week", "2025")
    """
    if not new_deals:
        return

    ws = spreadsheet.worksheet("Deals")
    today = date.today().isoformat()

    rows_to_insert = []
    for deal in new_deals:
        row = [
            deal.get("pg_account_name", ""),
            deal.get("clean_name", ""),
            deal.get("acquiror", ""),
            deal.get("target", ""),
            deal.get("deal_status", ""),
            deal.get("sector", ""),
            deal.get("description", ""),
            deal.get("date_rumor", ""),
            deal.get("date_announced", ""),
            deal.get("date_closed", ""),
            deal.get("deal_value", ""),
            deal.get("source", ""),
            deal.get("source_link", ""),
            deal.get("opportunity", ""),
            deal.get("source_validation", ""),
            # Metadata
            deal.get("deal_id", ""),
            ",".join(deal.get("stages_reported", [])),
            deal.get("first_seen", today),
            today,  # last_updated
            scan_period,
        ]
        rows_to_insert.append(row)

    # Insert at row 2 (below headers) so newest deals are at top
    ws.insert_rows(rows_to_insert, row=2)

    # Highlight new rows yellow
    num_new = len(rows_to_insert)
    ws.format(f"2:{1 + num_new}", {
        "backgroundColor": {"red": 1, "green": 1, "blue": 0.6}
    })


def append_rows_with_rate_limit(
    ws: gspread.Worksheet,
    rows: list[list],
    delay: float = 1.0
) -> None:
    """
    Append multiple rows to worksheet using batch API with rate limiting.

    Uses ws.append_rows() for efficient batch writing.
    Adds delay after write to stay under 60 writes/minute quota.

    Args:
        ws: Worksheet to write to
        rows: List of row data (each row is a list of values)
        delay: Seconds to wait after write (default: 1.0)

    Raises:
        gspread.exceptions.APIError: If write fails
    """
    if not rows:
        return

    # Batch write all rows at once
    ws.append_rows(rows, value_input_option='RAW')

    # Rate limiting: Wait 1 second to stay under 60 writes/min
    time.sleep(delay)


def save_checkpoint(
    new_deals: list[dict],
    excluded_deals: list[dict],
    unverified_deals: list[dict],
    scan_period: str,
    start_date: str,
    end_date: str,
    validation_stats: dict,
    total_companies: int,
    test_mode: bool = False
) -> str:
    """
    Save scan results to checkpoint JSON file.

    Creates checkpoint file in data/checkpoints/ directory for retry/recovery.

    Args:
        new_deals: List of verified new deals
        excluded_deals: List of excluded deals
        unverified_deals: List of unverified deals
        scan_period: Period string (e.g., "2025-01", "last_week")
        start_date: Scan start date (YYYY-MM-DD)
        end_date: Scan end date (YYYY-MM-DD)
        validation_stats: Dict with verified/re_sourced/unverified counts
        total_companies: Number of companies scanned
        test_mode: Whether scan was in test mode

    Returns:
        Path to created checkpoint file

    Raises:
        OSError: If checkpoint directory cannot be created or file cannot be written
    """
    # Ensure checkpoint directory exists
    checkpoint_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "checkpoints"
    )
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Generate checkpoint filename
    timestamp = datetime.now().isoformat().replace(":", "-")
    filename = f"checkpoint_{scan_period}_{timestamp}.json"
    filepath = os.path.join(checkpoint_dir, filename)

    # Build checkpoint structure
    checkpoint = {
        "metadata": {
            "scan_period": scan_period,
            "scan_dates": {
                "start_date": start_date,
                "end_date": end_date
            },
            "timestamp": datetime.now().isoformat(),
            "total_companies_scanned": total_companies,
            "test_mode": test_mode
        },
        "deals": {
            "new_deals": new_deals,
            "excluded_deals": excluded_deals,
            "unverified_deals": unverified_deals
        },
        "write_progress": {
            "new_deals_written": False,
            "excluded_deals_written": False,
            "unverified_deals_written": False,
            "executive_summary_written": False,
            "completed": False,
            "last_write_timestamp": None,
            "error_log": []
        },
        "validation_stats": validation_stats
    }

    # Write checkpoint file (pretty-printed for debugging)
    with open(filepath, 'w') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    return filepath


def update_checkpoint_progress(
    checkpoint_path: str,
    step: str,
    success: bool = True,
    error: str = None
) -> None:
    """
    Update checkpoint file with write progress.

    Args:
        checkpoint_path: Path to checkpoint JSON file
        step: Step that completed ("new_deals", "excluded_deals", "unverified_deals", "executive_summary")
        success: Whether step succeeded
        error: Error message if step failed
    """
    with open(checkpoint_path, 'r') as f:
        checkpoint = json.load(f)

    # Update progress
    step_key = f"{step}_written"
    if step_key in checkpoint["write_progress"]:
        checkpoint["write_progress"][step_key] = success
        checkpoint["write_progress"]["last_write_timestamp"] = datetime.now().isoformat()

        if not success and error:
            checkpoint["write_progress"]["error_log"].append({
                "step": step,
                "timestamp": datetime.now().isoformat(),
                "error": error
            })

        # Check if all steps completed
        all_done = (
            checkpoint["write_progress"]["new_deals_written"] and
            checkpoint["write_progress"]["excluded_deals_written"] and
            checkpoint["write_progress"]["unverified_deals_written"] and
            checkpoint["write_progress"]["executive_summary_written"]
        )
        checkpoint["write_progress"]["completed"] = all_done

    # Write back
    with open(checkpoint_path, 'w') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def append_excluded_deals(
    spreadsheet: gspread.Spreadsheet,
    excluded_deals: list[dict],
    scan_period: str
) -> None:
    """
    Append PE/financial/IPO deals to the Excluded tab.

    Uses batch write for efficiency (1 API call instead of N calls).

    Args:
        spreadsheet: gspread Spreadsheet object
        excluded_deals: List of excluded deal dicts
        scan_period: Period string
    """
    if not excluded_deals:
        return

    ws = spreadsheet.worksheet("Excluded (Non-Strategic)")
    today = date.today().isoformat()

    # Build all rows first
    rows_to_append = []
    for deal in excluded_deals:
        row = [
            deal.get("acquiror", ""),
            deal.get("target", ""),
            deal.get("deal_value", ""),
            deal.get("sector", ""),
            deal.get("description", ""),
            deal.get("exclusion_reason", ""),
            today,
            scan_period,
        ]
        rows_to_append.append(row)

    # Batch write with rate limiting
    append_rows_with_rate_limit(ws, rows_to_append)


def append_unverified_deals(
    spreadsheet: gspread.Spreadsheet,
    unverified_deals: list[dict],
    scan_period: str
) -> None:
    """
    Append deals with no valid source to the Unverified tab.

    Uses batch write for efficiency (1 API call instead of N calls).

    Args:
        spreadsheet: gspread Spreadsheet object
        unverified_deals: List of unverified deal dicts
        scan_period: Period string
    """
    if not unverified_deals:
        return

    ws = spreadsheet.worksheet("Unverified")
    today = date.today().isoformat()

    # Build all rows first
    rows_to_append = []
    for deal in unverified_deals:
        row = [
            deal.get("acquiror", ""),
            deal.get("target", ""),
            deal.get("deal_status", ""),
            deal.get("sector", ""),
            deal.get("description", ""),
            deal.get("source_link", ""),  # The failed URL
            deal.get("validation_failure_reason", ""),
            today,
            scan_period,
        ]
        rows_to_append.append(row)

    # Batch write with rate limiting
    append_rows_with_rate_limit(ws, rows_to_append)


def update_executive_summary(
    spreadsheet: gspread.Spreadsheet,
    new_deals: list[dict],
    all_deals: list[dict],
    excluded_count: int,
    unverified_count: int,
    scan_period: str,
    validation_stats: dict
) -> None:
    """
    Overwrite the Executive Summary tab with current stats.

    This is rebuilt from scratch each run using the full Deals tab data.

    Args:
        spreadsheet: gspread Spreadsheet object
        new_deals: List of new deals found this run
        all_deals: List of all deals (from Deals tab)
        excluded_count: Number of excluded deals this run
        unverified_count: Number of unverified deals this run
        scan_period: Period string
        validation_stats: Dict with keys: verified, re_sourced, unverified
    """
    ws = spreadsheet.worksheet("Executive Summary")
    ws.clear()

    today = date.today().isoformat()
    total = len(all_deals)
    new_count = len(new_deals)

    # Build summary rows
    summary = [
        ["PG M&A Deal Scanner - Executive Summary"],
        [""],
        [f"Last scan: {today} | Period: {scan_period}"],
        [""],
        ["OVERVIEW"],
        [f"Total deals tracked: {total}"],
        [f"New this cycle: {new_count}"],
        [f"Excluded (PE/financial): {excluded_count}"],
        [f"Unverified (no source): {unverified_count}"],
        [""],
        ["SOURCE VALIDATION"],
        [f"✓ Verified: {validation_stats.get('verified', 0)}"],
        [f"🔄 Re-sourced: {validation_stats.get('re_sourced', 0)}"],
        [f"⚠️ Unverified: {validation_stats.get('unverified', 0)}"],
        [""],
        ["DEALS BY STATUS"],
    ]

    # Count by status
    status_counts = {}
    for deal in all_deals:
        status = deal.get("Deal Status", deal.get("deal_status", "Unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in sorted(status_counts.items()):
        summary.append([f"  {status}: {count}"])

    # Count by sector
    summary.append([""])
    summary.append(["DEALS BY SECTOR"])
    sector_counts = {}
    for deal in all_deals:
        sector = deal.get("Sector", deal.get("sector", "Unknown"))
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    for sector, count in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True):
        summary.append([f"  {sector}: {count}"])

    summary.append([""])
    summary.append(["TOP NEW DEALS THIS CYCLE"])

    # Top 5 new deals by value (attempt to parse deal_value)
    sorted_new_deals = sorted(
        new_deals,
        key=lambda d: _parse_deal_value(d.get("deal_value", "")),
        reverse=True
    )

    for deal in sorted_new_deals[:5]:
        acquiror = deal.get("acquiror", "?")
        target = deal.get("target", "?")
        value = deal.get("deal_value", "Undisclosed")
        summary.append([f"  {acquiror} → {target} ({value})"])

    if new_count > 5:
        summary.append([f"  ...and {new_count - 5} more"])

    # Write summary
    ws.update(f"A1:A{len(summary)}", summary)

    # Format title
    ws.format("A1", {
        "textFormat": {"bold": True, "fontSize": 14},
    })

    # Format section headers
    ws.format("A5", {"textFormat": {"bold": True}})
    ws.format("A11", {"textFormat": {"bold": True}})
    ws.format("A16", {"textFormat": {"bold": True}})


def _parse_deal_value(value_str: str) -> float:
    """
    Parse deal value string to float for sorting.

    Examples:
        "$53B" -> 53000000000
        "$2.5M" -> 2500000
        "Undisclosed" -> 0
    """
    if not value_str or value_str == "Undisclosed":
        return 0.0

    value_str = value_str.replace("$", "").replace(",", "").strip().upper()

    # Extract number and multiplier
    import re
    match = re.match(r"([\d.]+)\s*([BMK])?", value_str)
    if not match:
        return 0.0

    number = float(match.group(1))
    multiplier = match.group(2)

    if multiplier == "B":
        return number * 1_000_000_000
    elif multiplier == "M":
        return number * 1_000_000
    elif multiplier == "K":
        return number * 1_000
    else:
        return number


def get_sheet_url(spreadsheet: gspread.Spreadsheet) -> str:
    """
    Return the shareable URL for the Google Sheet.

    Args:
        spreadsheet: gspread Spreadsheet object

    Returns:
        URL string (e.g., "https://docs.google.com/spreadsheets/d/SHEET_ID")
    """
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
