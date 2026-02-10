#!/usr/bin/env python3
"""
Remove duplicate deals from Google Sheet using improved deduplication logic.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sheets_output import get_sheets_client, open_sheet
from dedup import generate_deal_id


def cleanup_duplicates():
    """Find and remove duplicate deals from the Deals sheet."""
    load_dotenv()

    print("=" * 60)
    print("CLEANUP DUPLICATE DEALS")
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

    # 2. Read all existing deals
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

    # 3. Group deals by deal_id (using improved deduplication logic)
    print("Analyzing for duplicates...")
    deal_groups = {}

    for row_num, row in enumerate(data_rows, start=2):  # Start at row 2 (after header)
        if len(row) == 0 or not row[col_indices.get("Acquiror", 0)].strip():
            continue  # Skip empty rows

        acquiror = row[col_indices.get("Acquiror", 2)] if len(row) > col_indices.get("Acquiror", 2) else ""
        target = row[col_indices.get("Target", 3)] if len(row) > col_indices.get("Target", 3) else ""

        if not acquiror or not target:
            continue

        deal_id = generate_deal_id(acquiror, target)

        if deal_id not in deal_groups:
            deal_groups[deal_id] = []

        deal_groups[deal_id].append({
            "row_num": row_num,
            "acquiror": acquiror,
            "target": target,
            "row_data": row
        })

    # 4. Find duplicates
    duplicates_found = []
    for deal_id, deals in deal_groups.items():
        if len(deals) > 1:
            duplicates_found.append({
                "deal_id": deal_id,
                "count": len(deals),
                "deals": deals
            })

    if not duplicates_found:
        print("✓ No duplicates found!\n")
        return 0

    print(f"✗ Found {len(duplicates_found)} duplicate deal groups:\n")

    # 5. Display duplicates and ask for confirmation
    rows_to_delete = []
    for dup in duplicates_found:
        print(f"Deal ID: {dup['deal_id']} ({dup['count']} copies)")
        for i, deal in enumerate(dup['deals'], 1):
            print(f"  Row {deal['row_num']}: {deal['acquiror']} → {deal['target']}")

        # Keep the first occurrence, mark others for deletion
        keep_row = dup['deals'][0]['row_num']
        delete_rows = [d['row_num'] for d in dup['deals'][1:]]
        rows_to_delete.extend(delete_rows)

        print(f"  → Will KEEP row {keep_row}, DELETE rows {', '.join(map(str, delete_rows))}")
        print()

    print(f"Total rows to delete: {len(rows_to_delete)}")
    print()

    # 6. Confirm before deletion
    confirm = input("Proceed with deletion? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted - no changes made")
        return 0

    # 7. Delete duplicate rows (in reverse order to preserve row numbers)
    print("\nDeleting duplicate rows...")
    rows_to_delete.sort(reverse=True)  # Delete from bottom up

    for row_num in rows_to_delete:
        deals_ws.delete_rows(row_num)
        print(f"  ✓ Deleted row {row_num}")

    print(f"\n✓ Deleted {len(rows_to_delete)} duplicate rows\n")

    print("=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
    print(f"Duplicate groups found: {len(duplicates_found)}")
    print(f"Rows deleted: {len(rows_to_delete)}")
    print(f"Remaining deals: {len(data_rows) - len(rows_to_delete)}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(cleanup_duplicates())
