#!/usr/bin/env python3
"""
Remove the Executive Summary tab from the Google Sheet.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sheets_output import open_sheet


def remove_exec_summary():
    """Remove the Executive Summary tab."""
    load_dotenv()

    print("Removing Executive Summary tab from Google Sheet...")

    # Connect to Google Sheets
    try:
        spreadsheet = open_sheet()
        print(f"✓ Connected to Google Sheets")
    except Exception as e:
        print(f"✗ Error connecting to Google Sheets: {e}")
        return 1

    # Try to delete the Executive Summary worksheet
    try:
        ws = spreadsheet.worksheet("Executive Summary")
        spreadsheet.del_worksheet(ws)
        print("✓ Removed 'Executive Summary' tab")
        return 0
    except Exception as e:
        if "not found" in str(e).lower():
            print("'Executive Summary' tab not found - may already be deleted")
            return 0
        else:
            print(f"✗ Error removing tab: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(remove_exec_summary())
