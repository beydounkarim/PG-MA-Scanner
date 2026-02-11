#!/usr/bin/env python3
"""
Clean Sheet Formatting - Remove highlights and fix text formatting.

Usage:
    python src/clean_formatting.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet


def clean_sheet_formatting():
    """
    Clean up sheet formatting:
    - Remove all background colors (yellow highlights, etc.)
    - Set text to black, normal weight
    - Keep section headers with subtle gray background
    - Keep header row formatted
    """
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    ws = spreadsheet.worksheet('Deals')

    # Get all data to find section headers
    all_rows = ws.get_all_values()
    num_rows = len(all_rows)
    num_cols = len(all_rows[0]) if all_rows else 0

    print(f"✓ Loaded sheet with {num_rows} rows and {num_cols} columns\n")

    # Define ranges
    end_col_letter = chr(ord('A') + num_cols - 1)
    full_range = f'A1:{end_col_letter}{num_rows}'

    print("Cleaning formatting...")

    # Step 1: Clear all formatting from entire sheet (except values)
    print("  Removing all background colors and text formatting...")
    ws.format(full_range, {
        'backgroundColor': {'red': 1, 'green': 1, 'blue': 1},  # White background
        'textFormat': {
            'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},  # Black text
            'bold': False,
            'fontSize': 10
        }
    })

    # Step 2: Format title row (row 1)
    print("  Formatting title row...")
    ws.format(f'A1:{end_col_letter}1', {
        'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95},  # Light gray
        'textFormat': {
            'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},
            'bold': True,
            'fontSize': 12
        },
        'horizontalAlignment': 'CENTER'
    })

    # Step 3: Format header row (row 3)
    print("  Formatting header row...")
    ws.format(f'A3:{end_col_letter}3', {
        'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85},  # Medium gray
        'textFormat': {
            'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},
            'bold': True,
            'fontSize': 10
        }
    })

    # Step 4: Format section headers (rows that start with "═══")
    print("  Formatting section headers...")
    section_header_rows = []
    for i, row in enumerate(all_rows, start=1):
        if row and row[0].startswith('═══'):
            section_header_rows.append(i)

    for row_num in section_header_rows:
        ws.format(f'A{row_num}:{end_col_letter}{row_num}', {
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},  # Light gray
            'textFormat': {
                'foregroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2},  # Dark gray text
                'bold': True,
                'fontSize': 11
            }
        })

    print(f"  ✓ Formatted {len(section_header_rows)} section headers")

    # Step 5: Set column widths for better readability
    print("  Adjusting column widths...")
    try:
        # Set specific widths for key columns
        requests = [
            {
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': ws.id,
                        'dimension': 'COLUMNS',
                        'startIndex': 0,  # PG Account Name
                        'endIndex': 1
                    },
                    'properties': {'pixelSize': 150},
                    'fields': 'pixelSize'
                }
            },
            {
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': ws.id,
                        'dimension': 'COLUMNS',
                        'startIndex': 2,  # Acquiror
                        'endIndex': 3
                    },
                    'properties': {'pixelSize': 200},
                    'fields': 'pixelSize'
                }
            },
            {
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': ws.id,
                        'dimension': 'COLUMNS',
                        'startIndex': 3,  # Target
                        'endIndex': 4
                    },
                    'properties': {'pixelSize': 200},
                    'fields': 'pixelSize'
                }
            },
            {
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': ws.id,
                        'dimension': 'COLUMNS',
                        'startIndex': 6,  # Description
                        'endIndex': 7
                    },
                    'properties': {'pixelSize': 300},
                    'fields': 'pixelSize'
                }
            },
            {
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': ws.id,
                        'dimension': 'COLUMNS',
                        'startIndex': 13,  # Opportunity
                        'endIndex': 14
                    },
                    'properties': {'pixelSize': 300},
                    'fields': 'pixelSize'
                }
            }
        ]

        spreadsheet.batch_update({'requests': requests})
        print("  ✓ Adjusted column widths")
    except Exception as e:
        print(f"  Warning: Could not adjust column widths: {e}")

    # Step 6: Add alternating row colors for data rows (subtle)
    print("  Adding subtle row striping...")
    try:
        # Apply banding (alternating row colors)
        requests = [{
            'addBanding': {
                'bandedRange': {
                    'range': {
                        'sheetId': ws.id,
                        'startRowIndex': 3,  # Start after header
                        'endRowIndex': num_rows,
                        'startColumnIndex': 0,
                        'endColumnIndex': num_cols
                    },
                    'rowProperties': {
                        'headerColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85},
                        'firstBandColor': {'red': 1, 'green': 1, 'blue': 1},
                        'secondBandColor': {'red': 0.98, 'green': 0.98, 'blue': 0.98}
                    }
                }
            }
        }]

        spreadsheet.batch_update({'requests': requests})
        print("  ✓ Added alternating row colors")
    except Exception as e:
        # May fail if banding already exists
        print(f"  Note: {e}")

    # Step 7: Ensure header row is frozen
    print("  Freezing header row...")
    try:
        ws.freeze(rows=3)
        print("  ✓ Header row frozen")
    except Exception as e:
        print(f"  Note: {e}")

    print()
    print("=" * 70)
    print("FORMATTING CLEANUP COMPLETE")
    print("=" * 70)
    print("Sheet now has professional, clean formatting:")
    print("  ✓ White background with no highlights")
    print("  ✓ Black text, normal weight")
    print("  ✓ Subtle gray backgrounds for headers and sections")
    print("  ✓ Alternating row colors for better readability")
    print("  ✓ Optimized column widths")
    print(f"\nSheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")


def main():
    """Main entry point."""
    print("=" * 70)
    print("CLEAN SHEET FORMATTING")
    print("=" * 70)
    print()

    try:
        clean_sheet_formatting()
        return 0
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
