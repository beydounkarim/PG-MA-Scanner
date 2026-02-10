#!/usr/bin/env python3
"""
Quick scan status checker - shows current progress without continuous monitoring.
"""

import os
import sys
from datetime import datetime

def check_status(log_file):
    """
    Check the current status of the scan.
    """
    if not os.path.exists(log_file):
        print("❌ Log file not found. Scan may not have started yet.")
        return

    stats = {
        'companies': None,
        'tier2_deals': None,
        'verified': None,
        'new_deals': None,
        'phase': 'Starting...',
        'complete': False,
        'sheet_url': None
    }

    with open(log_file, 'r') as f:
        lines = f.readlines()

    # Parse log
    for line in lines:
        if 'Loaded' in line and 'companies' in line:
            try:
                stats['companies'] = int(line.split()[1])
            except:
                pass
        elif 'TIER 2:' in line:
            stats['phase'] = 'Tier 2: Company Verification'
        elif 'Tier 2 complete:' in line:
            try:
                stats['tier2_deals'] = int(line.split(':')[1].strip().split()[0])
            except:
                pass
        elif 'TIER 3:' in line:
            stats['phase'] = 'Tier 3: Deep Dive Verification'
        elif 'Tier 3 complete:' in line:
            try:
                parts = line.split(':')[1].strip()
                stats['verified'] = int(parts.split('verified')[0].strip())
            except:
                pass
        elif 'TIER 4:' in line:
            stats['phase'] = 'Tier 4: Facility Research'
        elif 'SOURCE VALIDATION' in line:
            stats['phase'] = 'Source Validation'
        elif 'Found' in line and 'new alerts' in line:
            try:
                stats['new_deals'] = int(line.split()[1])
            except:
                pass
        elif 'ORGANIZING RESULTS' in line:
            stats['phase'] = 'Organizing by Period'
        elif 'COMPLETE!' in line:
            stats['complete'] = True
            stats['phase'] = 'Complete!'
        elif 'Google Sheet:' in line and 'http' in line:
            stats['sheet_url'] = line.split('Google Sheet:')[1].strip()

    # Display status
    print("\n" + "=" * 70)
    print("PG M&A SCANNER - CURRENT STATUS")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nCurrent Phase: {stats['phase']}")
    print("\nProgress:")

    if stats['companies']:
        print(f"  ✓ Companies loaded: {stats['companies']}")
    if stats['tier2_deals'] is not None:
        print(f"  ✓ Tier 2 deals found: {stats['tier2_deals']}")
    if stats['verified'] is not None:
        print(f"  ✓ Verified deals: {stats['verified']}")
    if stats['new_deals'] is not None:
        print(f"  ✓ New deals (after dedup): {stats['new_deals']}")

    if stats['complete']:
        print("\n✅ STATUS: COMPLETE")
        if stats['sheet_url']:
            print(f"\n📊 Google Sheet: {stats['sheet_url']}")
    else:
        print("\n🔄 STATUS: Running...")
        print("\nTo check again, run:")
        print(f"  python3 check_scan_status.py")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    log_file = "/private/tmp/claude-501/-Users-karimbeydoun-Library-CloudStorage-OneDrive-Personal-Repos-PG-M-A-Scanner/tasks/b420257.output"

    if len(sys.argv) > 1:
        log_file = sys.argv[1]

    check_status(log_file)
