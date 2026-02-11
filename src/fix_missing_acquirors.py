#!/usr/bin/env python3
"""
Fix Missing Acquirors - Extract acquiror names from descriptions.

Usage:
    python src/fix_missing_acquirors.py
    python src/fix_missing_acquirors.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet
import anthropic


def extract_acquiror_from_description(description: str, target: str) -> str:
    """
    Use Claude to extract the acquiror name from the description.

    Args:
        description: Deal description text
        target: Target company name

    Returns:
        Extracted acquiror name
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""Extract ONLY the acquiror company name from this M&A deal description.

Target company: {target}

Description: {description}

Return ONLY the acquiror's full legal name (e.g., "ExxonMobil Corporation" or "3R Petroleum Óleo e Gás S.A.").
Do not include any explanation, just the company name."""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text.strip()


def fix_missing_acquirors(dry_run: bool = False) -> None:
    """
    Fix all deals with missing Acquiror fields.

    Args:
        dry_run: If True, only show what would be updated
    """
    # Load the missing acquiror deals
    with open('/tmp/missing_acquiror_deals.json', 'r') as f:
        deals = json.load(f)

    print(f"Processing {len(deals)} deals with missing Acquiror...")
    print()

    # Extract acquiror for each deal
    updates = []

    for i, deal in enumerate(deals, 1):
        row_num = deal['row_number']
        target = deal['target']
        description = deal['description']

        print(f"[{i}/{len(deals)}] Row {row_num}: Extracting acquiror...")
        print(f"  Target: {target}")

        try:
            acquiror = extract_acquiror_from_description(description, target)
            print(f"  ✓ Found: {acquiror}")

            updates.append({
                'row_number': row_num,
                'acquiror': acquiror
            })

            # Rate limit: 0.5 second between API calls
            time.sleep(0.5)

        except Exception as e:
            print(f"  ✗ Error: {e}")
            updates.append({
                'row_number': row_num,
                'acquiror': None,
                'error': str(e)
            })

        print()

    # Save extraction results
    backup_file = f"/tmp/acquiror_fixes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, 'w') as f:
        json.dump(updates, f, indent=2)
    print(f"Saved extraction results to: {backup_file}\n")

    if dry_run:
        print("[DRY RUN] Would update the following rows:")
        for update in updates:
            if update.get('acquiror'):
                print(f"  Row {update['row_number']}: {update['acquiror']}")
        return

    # Connect to Google Sheets and update
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    ws = spreadsheet.worksheet('Deals')
    header = ws.row_values(1)
    acquiror_col = header.index('Acquiror') + 1  # 1-indexed for gspread

    print("Updating Acquiror fields...\n")

    successful = 0
    failed = 0

    for update in updates:
        if update.get('acquiror'):
            row_num = update['row_number']
            acquiror = update['acquiror']

            try:
                # Update single cell
                ws.update_cell(row_num, acquiror_col, acquiror)
                print(f"✓ Row {row_num}: Updated to '{acquiror}'")
                successful += 1

                # Rate limit: 1 second between writes
                time.sleep(1)

            except Exception as e:
                print(f"✗ Row {row_num}: Failed - {e}")
                failed += 1
        else:
            print(f"⊘ Row {update['row_number']}: Skipped (extraction failed)")
            failed += 1

    print()
    print("=" * 70)
    print("UPDATE COMPLETE")
    print("=" * 70)
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Backup file: {backup_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix missing Acquiror fields in Google Sheets"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("FIX MISSING ACQUIRORS")
    print("=" * 70)
    print()

    try:
        fix_missing_acquirors(dry_run=args.dry_run)
        return 0
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
