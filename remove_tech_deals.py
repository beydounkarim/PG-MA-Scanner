#!/usr/bin/env python3
"""
Remove technology sector deals from the Google Sheet.
Specifically removes Google and Microsoft acquisitions.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sheets_output import open_sheet

# Tech companies to filter out
TECH_COMPANIES = [
    'google',
    'alphabet',
    'microsoft',
    'apple',
    'meta',
    'facebook',
    'amazon',
    'netflix',
    'tesla',
    'nvidia',
    'intel',
    'amd',
    'oracle',
    'salesforce',
    'adobe',
    'ibm',
]


def is_tech_deal(acquiror: str, target: str) -> bool:
    """
    Check if a deal involves a tech company.

    Args:
        acquiror: Acquiror company name
        target: Target company name

    Returns:
        True if either side is a tech company
    """
    acquiror_lower = acquiror.lower()
    target_lower = target.lower()

    for tech_company in TECH_COMPANIES:
        if tech_company in acquiror_lower or tech_company in target_lower:
            return True

    return False


def remove_tech_deals():
    """Remove tech deals from the Deals tab."""
    load_dotenv()

    print("=" * 70)
    print("REMOVING TECH SECTOR DEALS FROM GOOGLE SHEET")
    print("=" * 70)
    print()

    # Connect to Google Sheets
    try:
        spreadsheet = open_sheet()
        print(f"✓ Connected to Google Sheets")
    except Exception as e:
        print(f"✗ Error connecting to Google Sheets: {e}")
        return 1

    # Get the Deals worksheet
    ws = spreadsheet.worksheet("Deals")
    all_rows = ws.get_all_values()

    if len(all_rows) <= 1:
        print("No deals found in the sheet.")
        return 0

    headers = all_rows[0]
    deal_rows = all_rows[1:]

    # Find tech deals to remove
    tech_deal_indices = []
    tech_deals_info = []

    for idx, row in enumerate(deal_rows, start=2):  # start=2 because row 1 is headers
        if len(row) < 4:
            continue

        # Get acquiror and target (columns 3 and 4, index 2 and 3)
        acquiror = row[2] if len(row) > 2 else ""
        target = row[3] if len(row) > 3 else ""

        if is_tech_deal(acquiror, target):
            tech_deal_indices.append(idx)
            tech_deals_info.append(f"  • {acquiror} → {target}")

    if not tech_deal_indices:
        print("✓ No tech deals found. Sheet is clean!")
        return 0

    # Display found tech deals
    print(f"Found {len(tech_deal_indices)} tech sector deal(s) to remove:")
    print()
    for deal_info in tech_deals_info:
        print(deal_info)
    print()

    # Remove rows (start from the bottom to avoid index shifting)
    print("Removing tech deals...")
    for row_num in reversed(tech_deal_indices):
        ws.delete_rows(row_num)
        print(f"  ✓ Removed row {row_num}")

    print()
    print(f"✓ Removed {len(tech_deal_indices)} tech deal(s) from the sheet")
    print()

    # Also move them to Excluded tab
    print("Adding tech deals to Excluded tab...")
    excluded_ws = spreadsheet.worksheet("Excluded (Non-Strategic)")

    for idx, row in enumerate(deal_rows):
        if (idx + 2) in tech_deal_indices:  # idx+2 because we started at row 2
            acquiror = row[2] if len(row) > 2 else ""
            target = row[3] if len(row) > 3 else ""
            deal_value = row[10] if len(row) > 10 else ""
            sector = row[5] if len(row) > 5 else "Technology"
            description = row[6] if len(row) > 6 else ""

            excluded_ws.append_row([
                acquiror,
                target,
                deal_value,
                sector,
                description,
                "Technology sector (excluded per user preference)",
                "",  # Date Found (empty)
                "manual_cleanup"  # scan_period
            ])

    print(f"✓ Added {len(tech_deal_indices)} tech deal(s) to Excluded tab")
    print()
    print("=" * 70)
    print("COMPLETE!")
    print("=" * 70)
    print(f"Removed {len(tech_deal_indices)} tech deals from Deals tab")
    print("Tech deals are now in the 'Excluded (Non-Strategic)' tab")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(remove_tech_deals())
