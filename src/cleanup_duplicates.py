#!/usr/bin/env python3
"""
Cleanup Script - Remove duplicate deals from Google Sheets.

Backs up data first, then removes 114 duplicate entries while preserving
the 7 legitimate status updates (keeping the "Closed" version).

Usage:
    python src/cleanup_duplicates.py
    python src/cleanup_duplicates.py --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet


def backup_sheet_data(spreadsheet, backup_dir: str = None) -> str:
    """
    Create a backup of all sheet data to JSON file.

    Returns:
        Path to backup file
    """
    if backup_dir is None:
        backup_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "backups"
        )

    os.makedirs(backup_dir, exist_ok=True)

    # Get all worksheets
    backup_data = {}
    for worksheet in spreadsheet.worksheets():
        sheet_name = worksheet.title
        all_values = worksheet.get_all_values()
        backup_data[sheet_name] = all_values
        print(f"  Backed up '{sheet_name}': {len(all_values)} rows")

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_{timestamp}.json")

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    return backup_file


def identify_duplicates(spreadsheet) -> dict:
    """
    Identify duplicate deals and categorize them.

    Returns:
        Dict with 'true_duplicates' and 'status_updates' lists
    """
    ws = spreadsheet.worksheet('Deals')
    headers = ws.row_values(1)
    all_rows = ws.get_all_values()[1:]

    # Get column indices
    col_idx = {header: i for i, header in enumerate(headers)}

    # Map deals by ID
    deal_map = defaultdict(list)

    for row_num, row in enumerate(all_rows, 2):  # Start at row 2 (after header)
        if len(row) > col_idx.get('scan_period', 0):
            scan_period = row[col_idx['scan_period']] if 'scan_period' in col_idx else ''
            if scan_period == 'custom:2024-01-01:2026-02-10':
                acquiror = row[col_idx['Acquiror']] if 'Acquiror' in col_idx and col_idx['Acquiror'] < len(row) else ''
                target = row[col_idx['Target']] if 'Target' in col_idx and col_idx['Target'] < len(row) else ''
                status = row[col_idx['Deal Status']] if 'Deal Status' in col_idx and col_idx['Deal Status'] < len(row) else ''

                deal_id = f'{acquiror.strip().lower()}_{target.strip().lower()}'
                if acquiror.strip() and target.strip():
                    deal_map[deal_id].append({
                        'row': row_num,
                        'acquiror': acquiror,
                        'target': target,
                        'status': status.lower() if status else ''
                    })

    # Categorize duplicates
    true_duplicates = []
    status_updates = []

    for deal_id, instances in deal_map.items():
        if len(instances) > 1:
            statuses = set(inst['status'] for inst in instances if inst['status'])

            if len(statuses) > 1:
                # Different statuses - status update
                # Keep the "Closed" version, delete others
                closed_row = None
                other_rows = []

                for inst in instances:
                    if inst['status'] == 'closed':
                        closed_row = inst['row']
                    else:
                        other_rows.append(inst['row'])

                if closed_row and other_rows:
                    status_updates.append({
                        'deal': f"{instances[0]['acquiror']} → {instances[0]['target']}",
                        'keep_row': closed_row,
                        'delete_rows': other_rows,
                        'statuses': sorted(statuses)
                    })
            else:
                # Same status - true duplicate
                # Keep first occurrence, delete rest
                rows_sorted = sorted([inst['row'] for inst in instances])
                true_duplicates.append({
                    'deal': f"{instances[0]['acquiror']} → {instances[0]['target']}",
                    'status': instances[0]['status'],
                    'keep_row': rows_sorted[0],
                    'delete_rows': rows_sorted[1:]
                })

    return {
        'true_duplicates': true_duplicates,
        'status_updates': status_updates
    }


def delete_duplicate_rows(spreadsheet, duplicates: dict, dry_run: bool = False) -> int:
    """
    Delete duplicate rows from the Deals sheet with rate limiting.

    Args:
        spreadsheet: Google Spreadsheet object
        duplicates: Dict from identify_duplicates()
        dry_run: If True, only show what would be deleted

    Returns:
        Number of rows deleted
    """
    import time

    ws = spreadsheet.worksheet('Deals')

    # Collect all rows to delete
    rows_to_delete = []

    for dup in duplicates['true_duplicates']:
        rows_to_delete.extend(dup['delete_rows'])

    for dup in duplicates['status_updates']:
        rows_to_delete.extend(dup['delete_rows'])

    # Sort in descending order (delete from bottom to top to avoid index shifting)
    rows_to_delete.sort(reverse=True)

    print(f"\nRows to delete: {len(rows_to_delete)}")

    if dry_run:
        print("\n[DRY RUN] Would delete the following rows:")
        for row in rows_to_delete[:20]:
            print(f"  Row {row}")
        if len(rows_to_delete) > 20:
            print(f"  ... and {len(rows_to_delete) - 20} more")
        return 0

    # Delete rows in batches with rate limiting
    # Google Sheets API: 60 write requests per minute
    # Strategy: Delete 20 rows, then wait 20 seconds (= 3 batches per minute)
    print("\nDeleting duplicate rows with rate limiting...")
    batch_size = 20
    deleted_count = 0

    for i in range(0, len(rows_to_delete), batch_size):
        batch = rows_to_delete[i:i + batch_size]

        # Delete each row in the batch
        for row_num in batch:
            ws.delete_rows(row_num)
            deleted_count += 1

        print(f"  Deleted {deleted_count}/{len(rows_to_delete)} rows...")

        # Rate limit: wait 20 seconds after each batch (except the last one)
        if i + batch_size < len(rows_to_delete):
            print(f"  Rate limiting: waiting 20 seconds...")
            time.sleep(20)

    print(f"✓ Deleted {len(rows_to_delete)} duplicate rows")
    return len(rows_to_delete)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Clean up duplicate deals in Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what will be deleted
  python src/cleanup_duplicates.py --dry-run

  # Actually delete duplicates (with backup)
  python src/cleanup_duplicates.py
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("GOOGLE SHEETS DUPLICATE CLEANUP")
    print("=" * 70)
    print()

    # Connect to Sheets
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    print("✓ Connected\n")

    # Create backup
    if not args.dry_run:
        print("Creating backup...")
        backup_file = backup_sheet_data(spreadsheet)
        print(f"✓ Backup saved: {backup_file}\n")

    # Identify duplicates
    print("Analyzing duplicates...")
    duplicates = identify_duplicates(spreadsheet)

    print(f"✓ Found {len(duplicates['true_duplicates'])} true duplicates")
    print(f"✓ Found {len(duplicates['status_updates'])} status updates\n")

    # Show summary
    print("DUPLICATE BREAKDOWN")
    print("-" * 70)

    print("\nTrue Duplicates (first 10):")
    for dup in duplicates['true_duplicates'][:10]:
        print(f"  {dup['deal']} (status: {dup['status']})")
        print(f"    Keep row {dup['keep_row']}, delete rows {dup['delete_rows']}")
    if len(duplicates['true_duplicates']) > 10:
        print(f"  ... and {len(duplicates['true_duplicates']) - 10} more")

    print("\nStatus Updates (keeping 'Closed' version):")
    for dup in duplicates['status_updates']:
        print(f"  {dup['deal']} (statuses: {', '.join(dup['statuses'])})")
        print(f"    Keep row {dup['keep_row']} (Closed), delete rows {dup['delete_rows']}")

    # Calculate total
    total_to_delete = sum(len(d['delete_rows']) for d in duplicates['true_duplicates'])
    total_to_delete += sum(len(d['delete_rows']) for d in duplicates['status_updates'])

    print()
    print("=" * 70)
    print(f"TOTAL ROWS TO DELETE: {total_to_delete}")
    print("=" * 70)
    print()

    # Confirm if not dry run
    if not args.dry_run:
        response = input("Proceed with deletion? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return 1

    # Delete duplicates
    deleted_count = delete_duplicate_rows(spreadsheet, duplicates, dry_run=args.dry_run)

    if not args.dry_run:
        # Get final count
        ws = spreadsheet.worksheet('Deals')
        final_count = len([r for r in ws.get_all_values()[1:] if any(r)])

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
