#!/usr/bin/env python3
"""
Smart Deduplication - Use LLM to identify semantic duplicates.

Usage:
    python src/smart_dedup.py
    python src/smart_dedup.py --dry-run
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
import anthropic


def normalize_name(name: str) -> str:
    """Normalize company name for fuzzy matching."""
    # Remove common suffixes
    suffixes = [
        ' Limited', ' Ltd', ' Ltd.', ' LLC', ' L.L.C.', ' Inc', ' Inc.',
        ' Corporation', ' Corp', ' Corp.', ' plc', ' PLC', ' S.A.', ' SE',
        ' Pty Ltd', ' N.V.', ' NV', ' AG', ' GmbH'
    ]

    normalized = name.strip()
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()

    return normalized.lower()


def are_deals_duplicates(deal1: dict, deal2: dict, client: anthropic.Anthropic) -> bool:
    """
    Use LLM to determine if two deals are duplicates.

    Returns:
        True if deals are duplicates, False otherwise
    """
    prompt = f"""You are analyzing M&A deals for duplicates. Two deals are duplicates if they represent the SAME transaction, even if worded differently.

Deal 1:
Acquiror: {deal1['acquiror']}
Target: {deal1['target']}
Status: {deal1['status']}

Deal 2:
Acquiror: {deal2['acquiror']}
Target: {deal2['target']}
Status: {deal2['status']}

Are these the SAME deal (same acquiror acquiring same target)?

IMPORTANT rules:
- If one acquiror is empty/missing but targets match closely, consider it a duplicate (the empty one is likely incomplete data)
- Company name variations count as same (e.g., "Ltd" vs "Limited", "Corp" vs "Corporation", "BD" vs "Becton Dickinson")
- Different descriptions of same asset count as same (e.g., "45% stake in X" vs "X (45% stake)")
- Parent company vs subsidiary of same entity count as same (e.g., "OCI Global" vs "OCI Clean Ammonia Holding")
- Additional details in one description don't make it different (e.g., "Persson Invest AB" vs "Persson Invest AB (seller of 50% stake)")
- If targets clearly refer to the same company/asset and acquirors match or one is missing, answer YES

Answer with ONLY "YES" or "NO"."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )

        answer = message.content[0].text.strip().upper()
        return answer == "YES"
    except Exception as e:
        print(f"  Error checking duplicates: {e}")
        return False


def identify_duplicates_smart(spreadsheet) -> dict:
    """
    Identify duplicates using LLM-based semantic matching.

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

    # Extract all deals
    deals = []
    for row_num, row in enumerate(all_rows[header_row_idx + 1:], start=header_row_idx + 2):
        if not any(row) or row[0].startswith('═══') or row[0].startswith('M&A'):
            continue

        acquiror = row[col_idx['Acquiror']].strip() if len(row) > col_idx['Acquiror'] else ''
        target = row[col_idx['Target']].strip() if len(row) > col_idx['Target'] else ''

        if target:  # At least need a target
            deals.append({
                'row': row_num,
                'acquiror': acquiror,
                'target': target,
                'status': row[col_idx['Deal Status']].strip() if len(row) > col_idx['Deal Status'] else '',
                'acquiror_norm': normalize_name(acquiror),
                'target_norm': normalize_name(target)
            })

    print(f"Loaded {len(deals)} deals for analysis")

    # First pass: exact normalized matching (fast)
    print("\nPhase 1: Exact normalized matching...")
    exact_groups = defaultdict(list)
    for deal in deals:
        key = f"{deal['acquiror_norm']}|||{deal['target_norm']}"
        exact_groups[key].append(deal)

    exact_duplicates = []
    for key, group in exact_groups.items():
        if len(group) > 1:
            group_sorted = sorted(group, key=lambda x: x['row'])
            exact_duplicates.append({
                'deals': group,
                'keep_row': group_sorted[0]['row'],
                'delete_rows': [d['row'] for d in group_sorted[1:]]
            })

    print(f"  Found {len(exact_duplicates)} exact duplicate groups ({sum(len(g['delete_rows']) for g in exact_duplicates)} rows to delete)")

    # Second pass: LLM-based semantic matching for remaining deals
    print("\nPhase 2: Semantic matching with LLM...")

    # Remove exact duplicates from consideration
    exact_dup_rows = set()
    for dup in exact_duplicates:
        for row in dup['delete_rows']:
            exact_dup_rows.add(row)

    remaining_deals = [d for d in deals if d['row'] not in exact_dup_rows]
    print(f"  Checking {len(remaining_deals)} remaining deals...")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    semantic_duplicates = []
    checked_pairs = set()

    # Compare deals with similar normalized names
    for i, deal1 in enumerate(remaining_deals):
        if i % 50 == 0 and i > 0:
            print(f"    Progress: {i}/{len(remaining_deals)} deals checked...")

        for deal2 in remaining_deals[i+1:]:
            # Skip if already checked
            pair_key = tuple(sorted([deal1['row'], deal2['row']]))
            if pair_key in checked_pairs:
                continue

            # Quick filter: only check if targets are similar
            # (targets are the primary identifier for deals)
            tgt1_norm = deal1['target_norm']
            tgt2_norm = deal2['target_norm']

            # Extract key words (remove common words like "stake", "owned", etc.)
            stop_words = ['stake', 'owned', 'by', 'in', 'the', 'a', 'an', 'of', 'and',
                         'or', 'for', 'to', 'from', '45%', '50%', '51%', '100%',
                         'division', 'business', 'unit', 'group', 'company']

            def extract_key_words(text):
                words = text.split()
                return [w for w in words if len(w) > 2 and w not in stop_words and not w[0].isdigit()]

            tgt1_keywords = set(extract_key_words(tgt1_norm))
            tgt2_keywords = set(extract_key_words(tgt2_norm))

            # Check if there's significant overlap in key words (at least 2 common words)
            common_keywords = tgt1_keywords & tgt2_keywords
            keyword_overlap = len(common_keywords) >= 2

            # Also check traditional overlap
            traditional_overlap = (tgt1_norm in tgt2_norm or tgt2_norm in tgt1_norm or
                                  tgt1_norm[:20] == tgt2_norm[:20])

            tgt_similar = traditional_overlap or keyword_overlap

            # Compare with LLM if targets are similar
            # (This catches cases with empty/mismatched acquirors, variations, etc.)
            if tgt_similar:
                checked_pairs.add(pair_key)

                # Use LLM to check if duplicate
                if are_deals_duplicates(deal1, deal2, client):
                    semantic_duplicates.append({
                        'deal1': deal1,
                        'deal2': deal2,
                        'keep_row': min(deal1['row'], deal2['row']),
                        'delete_rows': [max(deal1['row'], deal2['row'])]
                    })
                    print(f"    Found duplicate: {deal1['acquiror']} → {deal1['target']}")

                # Rate limit
                time.sleep(0.3)

    print(f"  Found {len(semantic_duplicates)} semantic duplicates ({sum(len(d['delete_rows']) for d in semantic_duplicates)} rows to delete)")

    # Combine results
    all_duplicates = []

    # Add exact duplicates
    for dup in exact_duplicates:
        all_duplicates.append({
            'deal': f"{dup['deals'][0]['acquiror']} → {dup['deals'][0]['target']}",
            'status': dup['deals'][0]['status'],
            'type': 'exact',
            'keep_row': dup['keep_row'],
            'delete_rows': dup['delete_rows'],
            'count': len(dup['deals'])
        })

    # Add semantic duplicates
    for dup in semantic_duplicates:
        all_duplicates.append({
            'deal': f"{dup['deal1']['acquiror']} → {dup['deal1']['target']}",
            'status': dup['deal1']['status'],
            'type': 'semantic',
            'keep_row': dup['keep_row'],
            'delete_rows': dup['delete_rows'],
            'count': 2
        })

    return {
        'duplicates': all_duplicates,
        'total_to_delete': sum(len(d['delete_rows']) for d in all_duplicates)
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
    backup_file = os.path.join(backup_dir, f"backup_smart_dedup_{timestamp}.json")

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    return backup_file


def delete_duplicates(spreadsheet, duplicates: dict, dry_run: bool = False) -> int:
    """Delete duplicate rows."""
    ws = spreadsheet.worksheet('Deals')

    rows_to_delete = []
    for dup in duplicates['duplicates']:
        rows_to_delete.extend(dup['delete_rows'])

    # Sort in descending order (delete from bottom to top)
    rows_to_delete.sort(reverse=True)

    print(f"\nTotal rows to delete: {len(rows_to_delete)}")

    if dry_run:
        print("\n[DRY RUN] Would delete the following rows:")
        for row in rows_to_delete[:30]:
            print(f"  Row {row}")
        if len(rows_to_delete) > 30:
            print(f"  ... and {len(rows_to_delete) - 30} more")
        return 0

    # Delete rows with rate limiting
    print("\nDeleting duplicate rows...")
    deleted_count = 0

    for row_num in rows_to_delete:
        ws.delete_rows(row_num)
        deleted_count += 1

        if deleted_count % 10 == 0:
            print(f"  Deleted {deleted_count}/{len(rows_to_delete)} rows...")

        # Rate limit: 1 second between deletes
        if deleted_count < len(rows_to_delete):
            time.sleep(1)

    print(f"\n✓ Deleted {len(rows_to_delete)} duplicate rows")
    return len(rows_to_delete)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Smart deduplication using LLM semantic matching"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("SMART DEDUPLICATION (LLM-BASED)")
    print("=" * 70)
    print()

    # Connect to Sheets
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    print("✓ Connected\n")

    # Identify duplicates
    print("Analyzing duplicates with LLM semantic matching...")
    print("This may take several minutes for semantic analysis...")
    print()

    duplicates = identify_duplicates_smart(spreadsheet)

    print()
    print("=" * 70)
    print(f"FOUND {len(duplicates['duplicates'])} DUPLICATE SETS")
    print(f"TOTAL ROWS TO DELETE: {duplicates['total_to_delete']}")
    print("=" * 70)
    print()

    # Show first 20 duplicates
    if duplicates['duplicates']:
        print("DUPLICATE SETS (showing first 20):")
        print("-" * 70)
        for i, dup in enumerate(duplicates['duplicates'][:20], 1):
            print(f"{i}. [{dup['type'].upper()}] {dup['deal']}")
            print(f"   Keep row {dup['keep_row']}, delete rows {dup['delete_rows']}")

        if len(duplicates['duplicates']) > 20:
            print(f"\n... and {len(duplicates['duplicates']) - 20} more")
        print()

    if not duplicates['duplicates']:
        print("No duplicates found!")
        return 0

    # Create backup if not dry run
    if not args.dry_run:
        print("Creating backup...")
        backup_file = backup_sheet(spreadsheet)
        print(f"✓ Backup saved: {backup_file}\n")

        response = input(f"Proceed with deleting {duplicates['total_to_delete']} rows? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return 1

    # Delete duplicates
    deleted_count = delete_duplicates(spreadsheet, duplicates, dry_run=args.dry_run)

    if not args.dry_run and deleted_count > 0:
        print()
        print("=" * 70)
        print("CLEANUP COMPLETE")
        print("=" * 70)
        print(f"Rows deleted: {deleted_count}")
        print(f"Backup: {backup_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
