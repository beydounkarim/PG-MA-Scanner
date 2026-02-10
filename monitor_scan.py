#!/usr/bin/env python3
"""
Real-time scan monitoring script.

Monitors the progress of the M&A scan and displays key metrics.
"""

import os
import sys
import time
from datetime import datetime

def parse_log_for_stats(log_file):
    """
    Parse the log file and extract key statistics.

    Returns:
        dict with scan statistics
    """
    stats = {
        'companies_loaded': None,
        'tier2_deals': None,
        'verified_deals': None,
        'excluded_deals': None,
        'unverified_deals': None,
        'new_deals': None,
        'current_phase': 'Initializing...',
        'sheet_url': None,
        'complete': False,
        'error': None,
        'last_activity': None
    }

    if not os.path.exists(log_file):
        stats['error'] = "Log file not found"
        return stats

    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()

        # Track the most recent timestamp
        stats['last_activity'] = datetime.now().strftime('%H:%M:%S')

        for line in lines:
            line = line.strip()

            # Parse key events
            if 'Loaded' in line and 'companies' in line:
                # Extract number: "✓ Loaded 651 companies"
                try:
                    stats['companies_loaded'] = int(line.split()[1])
                except:
                    pass

            elif 'TIER 1:' in line:
                stats['current_phase'] = 'Tier 1: Industry Sector Scans'

            elif 'TIER 2:' in line:
                stats['current_phase'] = 'Tier 2: Company Batch Verification'

            elif 'Tier 2 complete:' in line:
                try:
                    # "Tier 2 complete: 45 total deals"
                    stats['tier2_deals'] = int(line.split(':')[1].strip().split()[0])
                except:
                    pass

            elif 'TIER 3:' in line:
                stats['current_phase'] = 'Tier 3: Deep Dive Verification'

            elif 'Tier 3 complete:' in line:
                try:
                    # "✓ Tier 3 complete: 12 verified, 5 excluded, 3 unverified"
                    parts = line.split(':')[1].strip()
                    stats['verified_deals'] = int(parts.split('verified')[0].strip())
                    if 'excluded' in parts:
                        stats['excluded_deals'] = int(parts.split()[2])
                    if 'unverified' in parts:
                        stats['unverified_deals'] = int(parts.split()[4])
                except:
                    pass

            elif 'TIER 4:' in line:
                stats['current_phase'] = 'Tier 4: Facility & Opportunity Research'

            elif 'SOURCE VALIDATION' in line:
                stats['current_phase'] = 'Source Validation Pipeline'

            elif 'Found' in line and 'new alerts' in line:
                try:
                    # "✓ Found 8 new alerts (after dedup)"
                    stats['new_deals'] = int(line.split()[1])
                except:
                    pass

            elif 'Writing to Google Sheets' in line:
                stats['current_phase'] = 'Writing to Google Sheets'

            elif 'ORGANIZING RESULTS' in line:
                stats['current_phase'] = 'Organizing Results by Period'

            elif 'Google Sheet:' in line and 'http' in line:
                try:
                    stats['sheet_url'] = line.split('Google Sheet:')[1].strip()
                except:
                    pass

            elif 'COMPLETE!' in line or 'SCAN COMPLETE' in line:
                stats['complete'] = True
                stats['current_phase'] = 'Complete!'

            elif 'Error' in line or 'Failed' in line or 'failed' in line:
                if not stats['error']:
                    stats['error'] = line

    except Exception as e:
        stats['error'] = f"Error reading log: {e}"

    return stats


def format_stats(stats):
    """
    Format statistics for display.
    """
    output = []
    output.append("=" * 80)
    output.append("PG M&A SCANNER - LIVE MONITORING")
    output.append("=" * 80)
    output.append(f"Last Activity: {stats['last_activity']}")
    output.append("")

    # Current phase
    output.append(f"Current Phase: {stats['current_phase']}")
    output.append("")

    # Progress metrics
    output.append("PROGRESS:")
    if stats['companies_loaded']:
        output.append(f"  ✓ Companies Loaded: {stats['companies_loaded']}")

    if stats['tier2_deals'] is not None:
        output.append(f"  ✓ Tier 2 Deals Found: {stats['tier2_deals']}")

    if stats['verified_deals'] is not None:
        output.append(f"  ✓ Verified Deals: {stats['verified_deals']}")

    if stats['excluded_deals'] is not None:
        output.append(f"  ✓ Excluded Deals: {stats['excluded_deals']}")

    if stats['unverified_deals'] is not None:
        output.append(f"  ✓ Unverified Deals: {stats['unverified_deals']}")

    if stats['new_deals'] is not None:
        output.append(f"  ✓ New Deals (after dedup): {stats['new_deals']}")

    output.append("")

    # Status
    if stats['complete']:
        output.append("STATUS: ✓ COMPLETE!")
        if stats['sheet_url']:
            output.append(f"Google Sheet: {stats['sheet_url']}")
    elif stats['error']:
        output.append(f"STATUS: ⚠️  ERROR")
        output.append(f"  {stats['error']}")
    else:
        output.append("STATUS: 🔄 Running...")

    output.append("=" * 80)

    return "\n".join(output)


def monitor_scan(log_file, refresh_interval=5):
    """
    Monitor the scan in real-time.

    Args:
        log_file: Path to the log file
        refresh_interval: Seconds between updates
    """
    print("\nStarting scan monitoring...")
    print(f"Log file: {log_file}")
    print(f"Refresh interval: {refresh_interval} seconds")
    print("\nPress Ctrl+C to stop monitoring\n")

    try:
        while True:
            # Clear screen
            os.system('clear' if os.name == 'posix' else 'cls')

            # Get current stats
            stats = parse_log_for_stats(log_file)

            # Display formatted stats
            print(format_stats(stats))

            # Check if complete
            if stats['complete']:
                print("\n✓ Scan completed successfully!")
                print("\nMonitoring stopped. Check the Google Sheet for results.")
                break

            if stats['error'] and 'failed' in stats['error'].lower():
                print("\n⚠️  Scan encountered an error. Check the log file for details.")
                print(f"\nFull log: {log_file}")
                break

            # Wait before next update
            time.sleep(refresh_interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
        print(f"The scan is still running in the background.")
        print(f"\nTo check progress manually, run:")
        print(f"  tail -f {log_file}")


def main():
    """Main entry point."""
    # Default log file location
    default_log = "/private/tmp/claude-501/-Users-karimbeydoun-Library-CloudStorage-OneDrive-Personal-Repos-PG-M-A-Scanner/tasks/b420257.output"

    # Allow custom log file as argument
    log_file = sys.argv[1] if len(sys.argv) > 1 else default_log

    # Refresh interval (default 5 seconds)
    refresh_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    # Start monitoring
    monitor_scan(log_file, refresh_interval)


if __name__ == "__main__":
    main()
