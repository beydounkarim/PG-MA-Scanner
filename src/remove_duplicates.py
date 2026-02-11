#!/usr/bin/env python3
"""
Remove Duplicates - Find and remove duplicate deals based on acquiror + target.

Usage:
    python src/remove_duplicates.py
    python src/remove_duplicates.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from collections import defaultdict

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet


def identify_duplicates(spreadsheet) -> dict:
    """
    Identify duplicate deals based on acquiror + target.

    Returns:
        Dict with duplicate info
    """
    ws = spreadsheet.worksheet('Deals')
    all_rows = ws.get_all_values()

    # Find header
    header_row_idx = 0
    for i, row in enumerate(all_rows):
        if row and row[0] == 'PG Account Name':
            header_row_idx = i
            break

    header = all_rows[header_row_idx]
    col_idx = {h: i for i, h in enumerate(header)}

    # Track deals by normalized acquiror+target
    deal_tracker = defaultdict(list)

    for row_num, row in enumerate(all_rows[header_row_idx + 1:], start=header_row_idx + 2):
        if not any(row) or row[0].startswith('═══') or row[0].startswith('M&A'):
            continue

        acquiror = row[col_idx['Acquiror']].strip().lower() if len(row) > col_idx['Acquiror'] else ''
        target = row[col_idx['Target']].strip().lower() if len(row) > col_idx['Target'] else ''

        if acquiror and target:
            key = f'{acquiror}|||{target}'
            deal_tracker[key].append({
                'row': row_num,
                'acquiror_display': row[col_idx['Acquiror']],
                'target_display': row[col_idx['Target']],
                'status': row[col_idx['Deal Status']] if len(row) > col_idx['Deal Status'] else ''
            })

    # Find duplicates - keep first, mark rest for deletion
    duplicates = []
    for key, instances in deal_tracker.items():
        if len(instances) > 1:
            # Sort by row number to keep the first occurrence
            instances_sorted = sorted(instances, key=lambda x: x['row'])
            keep_row = instances_sorted[0]['row']
            delete_rows = [inst['row'] for inst in instances_sorted[1:]]

            duplicates.append({
                'deal': f"{instances_sorted[0]['acquiror_display']} → {instances_sorted[0]['target_display']}",
                'status': instances_sorted[0]['status'],
                'keep_row': keep_row,
                'delete_rows': delete_rows,
                'count': len(instances)
            })

    return {
        'duplicates': duplicates,
        'total_to_delete': sum(len(d['delete_rows']) for d in duplicates)
    }


def backup_sheet(spreadsheet) -> str:
    """Create backup before deletion."""
    backup_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "backups"
    )
    os.makedirs(backup_dir, exist_ok=True)

    backup_data = {}
    for worksheet in spreadsheet.worksheets():
        sheet_name = worksheet.title
        all_values = worksheet.get_all_values()
        backup_data[sheet_name] = all_values

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_dedup_{timestamp}.json")

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    return backup_file


def delete_duplicates(spreadsheet, duplicates: dict, dry_run: bool = False) -> int:
    """
    Delete duplicate rows.

    Args:
        spreadsheet: Google Spreadsheet object
        duplicates: Dict from identify_duplicates()
        dry_run: If True, only show what would be deleted

    Returns:
        Number of rows deleted
    """
    ws = spreadsheet.worksheet('Deals')

    rows_to_delete = []
    for dup in duplicates['duplicates']:
        rows_to_delete.extend(dup['delete_rows'])

    # Sort in descending order (delete from bottom to top)
    rows_to_delete.sort(reverse=True)

    print(f"\nRows to delete: {len(rows_to_delete)}")

    if dry_run:
        print("\n[DRY RUN] Would delete the following rows:")
        for row in rows_to_delete:
            print(f"  Row {row}")
        return 0

    # Delete rows with rate limiting
    print("\nDeleting duplicate rows...")
    deleted_count = 0

    for row_num in rows_to_delete:
        ws.delete_rows(row_num)
        deleted_count += 1
        print(f"  Deleted row {row_num} ({deleted_count}/{len(rows_to_delete)})")

        # Rate limit: 1 second between deletes
        if deleted_count < len(rows_to_delete):
            time.sleep(1)

    print(f"\n✓ Deleted {len(rows_to_delete)} duplicate rows")
    return len(rows_to_delete)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remove duplicate deals from Google Sheets"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("REMOVE DUPLICATE DEALS")
    print("=" * 70)
    print()

    # Connect to Sheets
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    print("✓ Connected\n")

    # Identify duplicates
    print("Analyzing duplicates...")
    duplicates = identify_duplicates(spreadsheet)

    print(f"✓ Found {len(duplicates['duplicates'])} duplicate sets")
    print(f"✓ Total rows to delete: {duplicates['total_to_delete']}\n")

    # Show duplicates
    print("DUPLICATE SETS:")
    print("-" * 70)
    for i, dup in enumerate(duplicates['duplicates'], 1):
        print(f"{i}. {dup['deal']} (Status: {dup['status']})")
        print(f"   Keep row {dup['keep_row']}, delete rows {dup['delete_rows']}")

    if not duplicates['duplicates']:
        print("No duplicates found!")
        return 0

    print()

    # Create backup if not dry run
    if not args.dry_run:
        print("Creating backup...")
        backup_file = backup_sheet(spreadsheet)
        print(f"✓ Backup saved: {backup_file}\n")

        response = input("Proceed with deletion? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return 1

    # Delete duplicates
    deleted_count = delete_duplicates(spreadsheet, duplicates, dry_run=args.dry_run)

    if not args.dry_run:
        # Get final count
        ws = spreadsheet.worksheet('Deals')
        all_rows = ws.get_all_values()
        # Count non-empty, non-header, non-section rows
        final_count = sum(1 for r in all_rows if any(r) and not r[0].startswith('═══') and not r[0].startswith('M&A') and r[0] != 'PG Account Name' and r[0] != '')

        print()
        print("=" * 70)
        print("CLEANUP COMPLETE")
        print("=" * 70)
        print(f"Rows deleted:     {deleted_count}")
        print(f"Final deal count: {final_count}")
        print(f"Backup saved at:  {backup_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
