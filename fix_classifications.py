#!/usr/bin/env python3
"""
Re-run Tier 4 classification on all existing deals in Google Sheet.
This script updates the "Potential Opportunity for PG" column with
corrected OFFENSIVE/DEFENSIVE/MONITOR classifications.
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sheets_output import get_sheets_client, open_sheet
from scanner import run_tier4_research
from matcher import load_company_list, fuzzy_match


def fix_all_classifications():
    """Re-run Tier 4 on all existing deals and update the sheet."""
    load_dotenv()

    print("=" * 60)
    print("FIX OPPORTUNITY CLASSIFICATIONS")
    print("=" * 60)
    print()

    # 1. Connect to Google Sheets
    print("Connecting to Google Sheets...")
    try:
        spreadsheet = open_sheet()
        deals_ws = spreadsheet.worksheet("Deals")
        print(f"✓ Connected to Google Sheets\n")
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return 1

    # 2. Load company list for matching
    print("Loading company list...")
    companies = load_company_list("data/PG_Acct_List.xlsx")
    print(f"✓ Loaded {len(companies)} companies\n")

    # 3. Read all existing deals
    print("Reading existing deals from sheet...")
    all_rows = deals_ws.get_all_values()

    if len(all_rows) <= 1:
        print("No deals found in sheet")
        return 0

    headers = all_rows[0]
    data_rows = all_rows[1:]

    # Find column indices
    col_indices = {}
    for i, header in enumerate(headers):
        col_indices[header] = i

    print(f"✓ Found {len(data_rows)} existing deals\n")

    # 4. Process each deal
    print("Re-running Tier 4 classification...")
    print("=" * 60)

    updates = []

    for row_num, row in enumerate(data_rows, start=2):  # Start at row 2 (after header)
        if len(row) == 0 or not row[col_indices.get("Acquiror", 0)].strip():
            continue  # Skip empty rows

        acquiror = row[col_indices.get("Acquiror", 2)] if len(row) > col_indices.get("Acquiror", 2) else ""
        target = row[col_indices.get("Target", 3)] if len(row) > col_indices.get("Target", 3) else ""
        sector = row[col_indices.get("Sector", 5)] if len(row) > col_indices.get("Sector", 5) else ""

        if not acquiror or not target:
            continue

        print(f"[{row_num-1}/{len(data_rows)}] {acquiror} → {target}")

        # Re-match to get pg_match_side
        match_acq = fuzzy_match(acquiror, companies)
        match_tgt = fuzzy_match(target, companies)

        # Build deal dict with matching info
        deal = {
            "acquiror": acquiror,
            "target": target,
            "sector": sector
        }

        if match_acq or match_tgt:
            match = match_acq if match_acq else match_tgt
            deal["pg_account_name"] = match["account_name"]
            deal["clean_name"] = match["clean_name"]
            deal["pg_match_side"] = "acquiror" if match_acq else "target"

        # Run Tier 4 with updated logic
        try:
            opportunity = run_tier4_research(deal)

            # Store update for batch write
            updates.append({
                "row": row_num,
                "opportunity": opportunity
            })

            print(f"  ✓ Updated: {opportunity.split(':')[0]}")

            time.sleep(2)  # Rate limiting

        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue

    # 5. Write all updates to sheet
    if updates:
        print(f"\n✓ Re-classified {len(updates)} deals\n")
        print("Writing updates to Google Sheets...")

        opportunity_col = col_indices.get("Potential Opportunity for PG", 13) + 1  # 1-indexed for sheets API

        for update in updates:
            cell = f"{chr(64 + opportunity_col)}{update['row']}"  # Convert to A1 notation
            deals_ws.update(cell, [[update['opportunity']]])
            time.sleep(1)  # Rate limiting for sheets API

        print(f"✓ Updated {len(updates)} cells in column {chr(64 + opportunity_col)}\n")
    else:
        print("\nNo updates to write\n")

    print("=" * 60)
    print("CLASSIFICATION FIX COMPLETE")
    print("=" * 60)
    print(f"Deals re-classified: {len(updates)}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(fix_all_classifications())
