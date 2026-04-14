#!/usr/bin/env python3
"""
Clean Sheet Formatting - Remove highlights and fix text formatting.

Works with the date-grouped sheet structure. Preserves section headers
("═══" rows) with gray formatting, and uses blue (#2F5496) header style.

Usage:
    python src/clean_formatting.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet, HEADER_BG, HEADER_TEXT, SECTION_BG, SECTION_TEXT


def clean_sheet_formatting():
    """
    Clean up sheet formatting:
    - Remove all background colors (yellow highlights, etc.)
    - Set text to black, normal weight
    - Keep section headers ("═══" rows) with gray background
    - Keep header row with blue background
    """
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    ws = spreadsheet.worksheet('Deals')

    # Get all data to find section headers
    all_rows = ws.get_all_values()
    num_rows = len(all_rows)
    num_cols = len(all_rows[0]) if all_rows else 0

    print(f"Loaded sheet with {num_rows} rows and {num_cols} columns\n")

    # Define ranges
    end_col_letter = chr(ord('A') + num_cols - 1)
    full_range = f'A1:{end_col_letter}{num_rows}'

    print("Cleaning formatting...")

    # Step 1: Clear all formatting from entire sheet
    print("  Removing all background colors and text formatting...")
    ws.format(full_range, {
        'backgroundColor': {'red': 1, 'green': 1, 'blue': 1},
        'textFormat': {
            'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},
            'bold': False,
            'fontSize': 10
        }
    })

    # Step 2: Format header row (row 1) with blue
    print("  Formatting header row...")
    ws.format(f'A1:{end_col_letter}1', {
        'backgroundColor': HEADER_BG,
        'textFormat': {
            'foregroundColor': HEADER_TEXT,
            'bold': True,
            'fontSize': 10
        },
    })

    # Step 3: Format section headers (rows starting with "═══")
    print("  Formatting section headers...")
    section_header_rows = []
    for i, row in enumerate(all_rows, start=1):
        if row and row[0].startswith('═══'):
            section_header_rows.append(i)

    for row_num in section_header_rows:
        ws.format(f'A{row_num}:{end_col_letter}{row_num}', {
            'backgroundColor': SECTION_BG,
            'textFormat': {
                'foregroundColor': SECTION_TEXT,
                'bold': True,
                'fontSize': 11
            }
        })

    print(f"  Formatted {len(section_header_rows)} section headers")

    # Step 4: Set column widths
    print("  Adjusting column widths...")
    try:
        requests = [
            _col_width_request(ws.id, 0, 1, 150),   # PG Account Name
            _col_width_request(ws.id, 2, 3, 200),   # Acquiror
            _col_width_request(ws.id, 3, 4, 200),   # Target
            _col_width_request(ws.id, 6, 7, 300),   # Description
            _col_width_request(ws.id, 13, 14, 300), # Opportunity
        ]
        spreadsheet.batch_update({'requests': requests})
        print("  Adjusted column widths")
    except Exception as e:
        print(f"  Warning: Could not adjust column widths: {e}")

    # Step 5: Freeze header row
    print("  Freezing header row...")
    try:
        ws.freeze(rows=1)
        print("  Header row frozen")
    except Exception as e:
        print(f"  Note: {e}")

    print()
    print("=" * 60)
    print("FORMATTING CLEANUP COMPLETE")
    print("=" * 60)
    print("Sheet formatting cleaned:")
    print("  - White background, black text")
    print("  - Blue header row (#2F5496)")
    print("  - Gray section headers for date groups")
    print("  - Optimized column widths")
    print(f"\nSheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")


def _col_width_request(sheet_id, start, end, width):
    """Build a column width update request."""
    return {
        'updateDimensionProperties': {
            'range': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': start,
                'endIndex': end,
            },
            'properties': {'pixelSize': width},
            'fields': 'pixelSize',
        }
    }


def main():
    """Main entry point."""
    print("=" * 60)
    print("CLEAN SHEET FORMATTING")
    print("=" * 60)
    print()

    try:
        clean_sheet_formatting()
        return 0
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
