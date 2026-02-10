#!/usr/bin/env python3
"""
Efficient Complete M&A Scan Script

Runs ONE acquisition search for all 651 companies from 2024-01-01 to 2026-02-10,
then organizes the results in the Google Sheet with visual separators by year.
Uses announcement date as the primary date for segregation.
"""

import os
import sys
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import gspread
from sheets_output import open_sheet, get_sheet_url, load_existing_deals, ensure_sheet_structure


def parse_deal_date(deal: dict) -> date:
    """
    Extract the most relevant date from a deal for sorting.

    Priority: date_announced > date_rumor > date_closed (announcement date is primary)

    Args:
        deal: Deal dictionary with date fields

    Returns:
        date object, or today's date if no valid date found
    """
    # Priority order: announcement date first (primary), then rumor, then closed
    for date_field in ['Date of Announcement', 'date_announced',
                       'Date of Rumor', 'date_rumor',
                       'Date Closed', 'date_closed']:
        date_str = deal.get(date_field, '')
        if date_str and date_str != '' and date_str != 'null':
            try:
                # Handle various date formats
                if isinstance(date_str, str):
                    # Try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    # Try MM/DD/YYYY format
                    return datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    continue

    # Default to today if no valid date found
    return date.today()


def get_period_label(deal_date: date, last_week_start: date) -> str:
    """
    Determine which period a deal belongs to based on announcement date.

    Args:
        deal_date: Date of the deal (announcement date)
        last_week_start: Start date of last week

    Returns:
        Period label string
    """
    if deal_date >= last_week_start:
        return "LAST WEEK"
    elif deal_date.year == 2026:
        return "2026 YTD"
    elif deal_date.year == 2025:
        return "2025"
    elif deal_date.year == 2024:
        return "2024"
    else:
        return "PRIOR TO 2024"


def reorganize_deals_by_period(spreadsheet: gspread.Spreadsheet, last_week_start: date) -> None:
    """
    Reorganize the deals in the Deals tab by period with visual separators.
    Uses announcement date as the primary date for segregation.

    Args:
        spreadsheet: gspread Spreadsheet object
        last_week_start: Start date of last week
    """
    print("\nReorganizing deals by announcement date...")

    ws = spreadsheet.worksheet("Deals")

    # Get all deals
    all_rows = ws.get_all_values()
    if len(all_rows) <= 1:
        print("No deals found to reorganize.")
        return

    headers = all_rows[0]
    deal_rows = all_rows[1:]

    # Convert rows to dicts for easier processing
    deals_with_rows = []
    for row in deal_rows:
        deal_dict = dict(zip(headers, row))
        deal_date = parse_deal_date(deal_dict)
        period = get_period_label(deal_date, last_week_start)
        deals_with_rows.append({
            'row': row,
            'date': deal_date,
            'period': period
        })

    # Sort by date descending (newest first)
    deals_with_rows.sort(key=lambda x: x['date'], reverse=True)

    # Group by period while maintaining chronological order within each period
    periods = ["LAST WEEK", "2026 YTD", "2025", "2024", "PRIOR TO 2024"]
    reorganized_rows = [headers]  # Start with headers

    for period in periods:
        period_deals = [d for d in deals_with_rows if d['period'] == period]

        if period_deals:
            # Add separator row
            separator = ["" for _ in headers]
            separator[0] = f"═══════════ {period} ═══════════"
            reorganized_rows.append(separator)

            # Add deals for this period
            for deal in period_deals:
                reorganized_rows.append(deal['row'])

    # Clear the entire sheet
    ws.clear()

    # Write reorganized data (update the full range at once)
    num_cols = len(headers)
    col_letter = chr(ord('A') + num_cols - 1)
    ws.update(f'A1:{col_letter}{len(reorganized_rows)}', reorganized_rows)

    # Format header row
    ws.format("1:1", {
        "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
        "textFormat": {
            "bold": True,
            "foregroundColor": {"red": 1, "green": 1, "blue": 1}
        },
    })
    ws.freeze(rows=1)

    # Format separator rows
    current_row = 2
    for period in periods:
        period_deals = [d for d in deals_with_rows if d['period'] == period]
        if period_deals:
            # Format separator row
            ws.format(f"{current_row}:{current_row}", {
                "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    "fontSize": 12
                },
                "horizontalAlignment": "CENTER"
            })
            current_row += 1 + len(period_deals)

    print(f"✓ Reorganized {len(deal_rows)} deals into {len([p for p in periods if any(d['period'] == p for d in deals_with_rows)])} periods")
    print(f"  Segregation based on: Announcement Date (primary)")


def main():
    """Main entry point."""
    load_dotenv()

    print("=" * 80)
    print("PG M&A SCANNER - COMPLETE SCAN WITH PERIOD SEPARATORS")
    print("=" * 80)
    print("\nThis will:")
    print("  1. Run ONE scan for all 651 companies (2024-01-01 to 2026-02-10)")
    print("  2. Organize results by ANNOUNCEMENT DATE with visual separators:")
    print("     • LAST WEEK (most recent)")
    print("     • 2026 YTD")
    print("     • 2025")
    print("     • 2024")
    print("\n" + "=" * 80 + "\n")

    # Verify Google Sheets connection
    print("Verifying Google Sheets connection...")
    try:
        spreadsheet = open_sheet()
        sheet_url = get_sheet_url(spreadsheet)
        print(f"✓ Connected to Google Sheet: {sheet_url}\n")
    except Exception as e:
        print(f"✗ Error connecting to Google Sheets: {e}")
        print("Please ensure GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are set in .env")
        return 1

    # Calculate last week start date
    today = date.today()
    days_since_monday = today.weekday()
    last_week_start = today - timedelta(days=days_since_monday + 7)

    # Run single comprehensive scan
    print("=" * 80)
    print("RUNNING COMPREHENSIVE SCAN")
    print("=" * 80)
    print(f"Period: 2024-01-01 to 2026-02-10")
    print(f"Companies: All 651")
    print("=" * 80 + "\n")

    # Use unbuffered output so we can see progress in real-time
    cmd = 'python3 -u src/main.py --period "custom:2024-01-01:2026-02-10"'
    exit_code = os.system(cmd)
    sys.stdout.flush()
    sys.stderr.flush()

    if exit_code != 0:
        print(f"\n✗ Scan failed with exit code: {exit_code}")
        return exit_code

    print("\n✓ Scan completed successfully!")

    # Reorganize deals by period
    print("\n" + "=" * 80)
    print("ORGANIZING RESULTS BY ANNOUNCEMENT DATE")
    print("=" * 80)

    try:
        reorganize_deals_by_period(spreadsheet, last_week_start)
    except Exception as e:
        print(f"✗ Error organizing results: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Final summary
    print("\n" + "=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print(f"\nGoogle Sheet: {sheet_url}")
    print("\nDeals are now organized by ANNOUNCEMENT DATE with visual separators:")
    print("  • LAST WEEK (newest at top)")
    print("  • 2026 YTD")
    print("  • 2025")
    print("  • 2024")
    print("\n" + "=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
