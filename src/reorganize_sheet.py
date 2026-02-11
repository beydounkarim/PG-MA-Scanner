#!/usr/bin/env python3
"""
Reorganize Google Sheets - Sort deals by announcement date with section headers.

Usage:
    python src/reorganize_sheet.py
    python src/reorganize_sheet.py --dry-run
"""

import argparse
import os
import sys
from datetime import datetime, date
from collections import defaultdict
from typing import Optional

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet


def parse_date(date_str: str) -> Optional[date]:
    """Parse date string to date object."""
    if not date_str or date_str.strip() == "":
        return None

    # Try common date formats
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%b %d, %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    return None


def categorize_by_period(deals: list[dict]) -> dict:
    """
    Categorize deals by time period based on available dates.

    Date hierarchy (in order of preference):
    1. Date of Announcement
    2. Date Closed
    3. Date of Rumor

    Returns:
        Dict with keys: 'prior_2024', '2024', '2025', 'ytd_2026', 'last_week', 'no_date'
    """
    periods = {
        'prior_2024': [],
        '2024': [],
        '2025': [],
        'ytd_2026': [],
        'last_week': [],
        'no_date': []
    }

    today = date.today()
    last_week_start = date(2026, 2, 3)  # Roughly 7 days ago from Feb 11, 2026
    ytd_2026_start = date(2026, 1, 1)

    for deal in deals:
        # Try dates in order of preference
        announce_date = parse_date(deal.get('Date of Announcement', ''))
        if not announce_date:
            announce_date = parse_date(deal.get('Date Closed', ''))
        if not announce_date:
            announce_date = parse_date(deal.get('Date of Rumor', ''))

        if not announce_date:
            periods['no_date'].append(deal)
        elif announce_date >= last_week_start:
            periods['last_week'].append(deal)
        elif announce_date >= ytd_2026_start:
            periods['ytd_2026'].append(deal)
        elif announce_date.year == 2025:
            periods['2025'].append(deal)
        elif announce_date.year == 2024:
            periods['2024'].append(deal)
        else:
            periods['prior_2024'].append(deal)

    # Sort each period by date (most recent first), using fallback hierarchy
    def get_sort_date(deal):
        """Get the best available date for sorting."""
        d = parse_date(deal.get('Date of Announcement', ''))
        if not d:
            d = parse_date(deal.get('Date Closed', ''))
        if not d:
            d = parse_date(deal.get('Date of Rumor', ''))
        return d or date.min

    for period in periods:
        periods[period].sort(key=get_sort_date, reverse=True)

    return periods


def create_section_header(title: str, num_cols: int) -> list:
    """Create a section header row."""
    row = [''] * num_cols
    row[0] = f"═══ {title.upper()} ═══"
    return row


def reorganize_sheet(dry_run: bool = False) -> None:
    """
    Reorganize the Deals sheet by announcement date with section headers.

    Args:
        dry_run: If True, only show what would be done
    """
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    ws = spreadsheet.worksheet('Deals')

    # Get all data
    all_rows = ws.get_all_values()

    # Find header row (should be row 3, but let's be safe)
    header_row_idx = 0
    for i, row in enumerate(all_rows):
        if row and row[0] == 'PG Account Name':
            header_row_idx = i
            break

    header = all_rows[header_row_idx]
    data_rows = all_rows[header_row_idx + 1:]

    print(f"✓ Loaded {len(all_rows)} total rows")
    print(f"✓ Header found at row {header_row_idx + 1}")
    print(f"✓ Processing {len(data_rows)} data rows\n")

    # Get column indices
    col_idx = {h: i for i, h in enumerate(header)}
    num_cols = len(header)

    # Convert rows to dicts
    deals = []
    for row in data_rows:
        if not any(row):  # Skip completely empty rows
            continue

        deal = {}
        for col_name, idx in col_idx.items():
            deal[col_name] = row[idx] if idx < len(row) else ''
        deals.append(deal)

    print(f"Processing {len(deals)} deals...")

    # Categorize by period
    periods = categorize_by_period(deals)

    print("\nDEALS BY PERIOD:")
    print("=" * 70)
    print(f"Prior to 2024:     {len(periods['prior_2024'])} deals")
    print(f"2024:              {len(periods['2024'])} deals")
    print(f"2025:              {len(periods['2025'])} deals")
    print(f"YTD 2026:          {len(periods['ytd_2026'])} deals")
    print(f"Last Week:         {len(periods['last_week'])} deals")
    print(f"No Date:           {len(periods['no_date'])} deals")
    print()

    if dry_run:
        print("[DRY RUN] Sheet would be reorganized with sections")
        return

    # Build new sheet structure
    new_rows = []

    # Add description row at top
    desc_row = [''] * num_cols
    desc_row[0] = "M&A DEALS - ORGANIZED BY ANNOUNCEMENT DATE (Most Recent First)"
    new_rows.append(desc_row)

    # Add empty row
    new_rows.append([''] * num_cols)

    # Add header
    new_rows.append(header)

    # Add sections in order
    sections = [
        ('LAST WEEK (Feb 3-11, 2026)', 'last_week'),
        ('YEAR TO DATE 2026 (Jan 1 - Feb 11, 2026)', 'ytd_2026'),
        ('2025 DEALS', '2025'),
        ('2024 DEALS', '2024'),
        ('PRIOR TO 2024', 'prior_2024'),
        ('NO ANNOUNCEMENT DATE', 'no_date'),
    ]

    for section_title, period_key in sections:
        if periods[period_key]:
            # Add section header
            new_rows.append([''] * num_cols)  # Empty row before section
            new_rows.append(create_section_header(section_title, num_cols))
            new_rows.append([''] * num_cols)  # Empty row after header

            # Add deals
            for deal in periods[period_key]:
                row = []
                for col_name in header:
                    row.append(deal.get(col_name, ''))
                new_rows.append(row)

    print(f"Reorganizing sheet with {len(new_rows)} total rows...")

    # Clear the sheet
    ws.clear()

    # Write new structure
    # Update in batches to avoid rate limits
    batch_size = 100
    for i in range(0, len(new_rows), batch_size):
        batch = new_rows[i:i + batch_size]
        start_row = i + 1

        # Determine range
        end_row = start_row + len(batch) - 1
        end_col_letter = chr(ord('A') + num_cols - 1)
        range_name = f'A{start_row}:{end_col_letter}{end_row}'

        ws.update(range_name, batch, value_input_option='RAW')
        print(f"  Updated rows {start_row}-{end_row}")

    # Format section headers (bold and larger)
    print("\nFormatting section headers...")

    # Find all section header rows
    for row_idx, row in enumerate(new_rows, start=1):
        if row[0].startswith('═══'):
            # Format this row
            try:
                ws.format(f'A{row_idx}:{chr(ord("A") + num_cols - 1)}{row_idx}', {
                    'textFormat': {'bold': True, 'fontSize': 12},
                    'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
                })
            except Exception as e:
                print(f"  Warning: Could not format row {row_idx}: {e}")

    # Format description row (first row)
    try:
        ws.format(f'A1:{chr(ord("A") + num_cols - 1)}1', {
            'textFormat': {'bold': True, 'fontSize': 14},
            'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
        })
    except Exception as e:
        print(f"  Warning: Could not format description row: {e}")

    # Freeze header row (row 3)
    try:
        ws.freeze(rows=3)
        print("✓ Froze header row")
    except Exception as e:
        print(f"  Warning: Could not freeze header: {e}")

    print()
    print("=" * 70)
    print("REORGANIZATION COMPLETE")
    print("=" * 70)
    print(f"Total rows written: {len(new_rows)}")
    print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reorganize Deals sheet by announcement date"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("REORGANIZE DEALS SHEET BY ANNOUNCEMENT DATE")
    print("=" * 70)
    print()

    try:
        reorganize_sheet(dry_run=args.dry_run)
        return 0
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
