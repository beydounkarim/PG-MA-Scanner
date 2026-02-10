#!/usr/bin/env python3
"""
Complete Historical M&A Scan Script

Runs acquisition searches for all 651 companies across:
- 2024 (full year)
- 2025 (full year)
- 2026 YTD (Jan 1 - Feb 10)
- Last Week

Each period is run separately with visual breaks in the Google Sheet.
"""

import os
import sys
from datetime import date
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sheets_output import open_sheet, get_sheet_url
import gspread


def add_separator_row(spreadsheet: gspread.Spreadsheet, period_label: str) -> None:
    """
    Add a visual separator row to the Deals tab.

    Args:
        spreadsheet: gspread Spreadsheet object
        period_label: Label for the period (e.g., "2024", "2025", "2026 YTD", "LAST WEEK")
    """
    ws = spreadsheet.worksheet("Deals")

    # Create a separator row with the period label in the first column
    separator_row = [f"═══════════ {period_label} ═══════════", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]

    # Insert at row 2 (just below headers)
    ws.insert_row(separator_row, index=2)

    # Format the separator row with dark background and white text
    ws.format("2:2", {
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
        "textFormat": {
            "bold": True,
            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
            "fontSize": 12
        },
        "horizontalAlignment": "CENTER"
    })

    print(f"✓ Added separator for {period_label}")


def run_period_scan(period: str, period_label: str) -> int:
    """
    Run the scanner for a specific period.

    Args:
        period: Period string for main.py (e.g., "custom:2024-01-01:2024-12-31")
        period_label: Human-readable label (e.g., "2024")

    Returns:
        Exit code from main.py
    """
    print("\n" + "=" * 80)
    print(f"STARTING SCAN FOR {period_label}")
    print("=" * 80 + "\n")

    # Run main.py with the specified period
    cmd = f'python3 src/main.py --period "{period}"'
    exit_code = os.system(cmd)

    if exit_code == 0:
        print(f"\n✓ Successfully completed scan for {period_label}\n")
    else:
        print(f"\n✗ Error during scan for {period_label} (exit code: {exit_code})\n")

    return exit_code


def main():
    """Main orchestrator for running all period scans."""
    load_dotenv()

    print("=" * 80)
    print("PG M&A SCANNER - COMPLETE HISTORICAL SCAN")
    print("=" * 80)
    print("\nThis will scan all 651 companies for acquisitions across:")
    print("  • 2024 (full year)")
    print("  • 2025 (full year)")
    print("  • 2026 YTD (Jan 1 - Feb 10)")
    print("  • Last Week (most recent activity)")
    print("\n" + "=" * 80)

    # Verify Google Sheets connection
    print("\nVerifying Google Sheets connection...")
    try:
        spreadsheet = open_sheet()
        sheet_url = get_sheet_url(spreadsheet)
        print(f"✓ Connected to Google Sheet: {sheet_url}\n")
    except Exception as e:
        print(f"✗ Error connecting to Google Sheets: {e}")
        print("Please ensure GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are set in .env")
        return 1

    # Define scan periods (in reverse chronological order for display)
    scans = [
        {
            "period": "last_week",
            "label": "LAST WEEK (Most Recent)",
        },
        {
            "period": "custom:2026-01-01:2026-02-10",
            "label": "2026 YTD",
        },
        {
            "period": "custom:2025-01-01:2025-12-31",
            "label": "2025",
        },
        {
            "period": "custom:2024-01-01:2024-12-31",
            "label": "2024",
        },
    ]

    total_scans = len(scans)
    failed_scans = []

    # Run each scan
    for i, scan_config in enumerate(scans, 1):
        period = scan_config["period"]
        label = scan_config["label"]

        print(f"\n{'#' * 80}")
        print(f"SCAN {i} of {total_scans}: {label}")
        print(f"{'#' * 80}\n")

        # Add separator row BEFORE running the scan
        # (This way new deals will appear above the separator)
        try:
            add_separator_row(spreadsheet, label)
        except Exception as e:
            print(f"⚠️  Warning: Could not add separator row: {e}")

        # Run the scan
        exit_code = run_period_scan(period, label)

        if exit_code != 0:
            failed_scans.append((label, exit_code))
            print(f"\n⚠️  WARNING: Scan for {label} failed, but continuing with remaining scans...")

        # Add a delay between scans to avoid rate limiting
        if i < total_scans:
            print("\nWaiting 30 seconds before next scan to avoid rate limits...")
            import time
            time.sleep(30)

    # Final summary
    print("\n" + "=" * 80)
    print("ALL SCANS COMPLETE")
    print("=" * 80)
    print(f"\nTotal scans run: {total_scans}")
    print(f"Successful: {total_scans - len(failed_scans)}")
    print(f"Failed: {len(failed_scans)}")

    if failed_scans:
        print("\nFailed scans:")
        for label, code in failed_scans:
            print(f"  • {label} (exit code: {code})")

    print(f"\nGoogle Sheet: {sheet_url}")
    print("\n" + "=" * 80)

    # Return non-zero exit code if any scans failed
    return 1 if failed_scans else 0


if __name__ == "__main__":
    sys.exit(main())
