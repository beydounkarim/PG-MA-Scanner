#!/usr/bin/env python3
"""
Retry Script - Resume Google Sheets writes from checkpoint.

Usage:
    python src/retry_write.py
    python src/retry_write.py --checkpoint data/checkpoints/checkpoint_2025-01_*.json
    python src/retry_write.py --force
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

from sheets_output import (
    open_sheet, ensure_sheet_structure, load_existing_deals,
    append_new_deals, append_excluded_deals, append_unverified_deals,
    update_executive_summary, get_sheet_url, update_checkpoint_progress
)


def find_latest_checkpoint(checkpoint_dir: str = None) -> str:
    """
    Find the most recent checkpoint file.

    Args:
        checkpoint_dir: Directory to search (default: data/checkpoints/)

    Returns:
        Path to latest checkpoint file

    Raises:
        FileNotFoundError: If no checkpoints found
    """
    if checkpoint_dir is None:
        checkpoint_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "checkpoints"
        )

    if not os.path.exists(checkpoint_dir):
        raise FileNotFoundError(f"Checkpoint directory not found: {checkpoint_dir}")

    # Find all checkpoint files
    checkpoints = [
        f for f in os.listdir(checkpoint_dir)
        if f.startswith("checkpoint_") and f.endswith(".json")
    ]

    if not checkpoints:
        raise FileNotFoundError(f"No checkpoint files found in {checkpoint_dir}")

    # Sort by modification time, newest first
    checkpoints.sort(
        key=lambda f: os.path.getmtime(os.path.join(checkpoint_dir, f)),
        reverse=True
    )

    return os.path.join(checkpoint_dir, checkpoints[0])


def load_checkpoint(checkpoint_path: str) -> dict:
    """
    Load checkpoint JSON file.

    Args:
        checkpoint_path: Path to checkpoint file

    Returns:
        Checkpoint dict

    Raises:
        FileNotFoundError: If checkpoint doesn't exist
        json.JSONDecodeError: If checkpoint is invalid JSON
    """
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")

    with open(checkpoint_path, 'r') as f:
        checkpoint = json.load(f)

    return checkpoint


def write_to_sheets(
    checkpoint: dict,
    checkpoint_path: str,
    force_overwrite: bool = False
) -> None:
    """
    Write checkpoint data to Google Sheets.

    Resumes from where previous write failed, unless force_overwrite=True.

    Args:
        checkpoint: Checkpoint dict
        checkpoint_path: Path to checkpoint file
        force_overwrite: If True, rewrite everything regardless of progress
    """
    # Connect to Sheets
    print("Connecting to Google Sheets...")
    spreadsheet = open_sheet()
    ensure_sheet_structure(spreadsheet)
    sheet_url = get_sheet_url(spreadsheet)
    print(f"✓ Connected: {sheet_url}\n")

    # Extract data
    new_deals = checkpoint["deals"]["new_deals"]
    excluded_deals = checkpoint["deals"]["excluded_deals"]
    unverified_deals = checkpoint["deals"]["unverified_deals"]
    scan_period = checkpoint["metadata"]["scan_period"]
    progress = checkpoint["write_progress"]

    # Normalize field names
    for deal in new_deals:
        deal.setdefault("date_rumor", "")
        deal.setdefault("date_announced", "")
        deal.setdefault("date_closed", "")

    print("=" * 60)
    print("RESUMING WRITE FROM CHECKPOINT")
    print("=" * 60)
    print(f"New deals:        {len(new_deals)}")
    print(f"Excluded deals:   {len(excluded_deals)}")
    print(f"Unverified deals: {len(unverified_deals)}")
    print()

    # Step 1: New Deals
    if not progress["new_deals_written"] or force_overwrite:
        try:
            print(f"[1/4] Writing {len(new_deals)} new deals...")
            append_new_deals(spreadsheet, new_deals, scan_period)
            update_checkpoint_progress(checkpoint_path, "new_deals", success=True)
            print("✓ New deals written")
            time.sleep(1)  # Rate limit
        except Exception as e:
            error_msg = f"Failed to write new deals: {e}"
            print(f"✗ {error_msg}")
            update_checkpoint_progress(checkpoint_path, "new_deals", success=False, error=str(e))
            raise
    else:
        print("[1/4] New deals already written (skipping)")

    # Step 2: Excluded Deals
    if not progress["excluded_deals_written"] or force_overwrite:
        try:
            print(f"[2/4] Writing {len(excluded_deals)} excluded deals...")
            append_excluded_deals(spreadsheet, excluded_deals, scan_period)
            update_checkpoint_progress(checkpoint_path, "excluded_deals", success=True)
            print("✓ Excluded deals written")
            time.sleep(1)  # Rate limit
        except Exception as e:
            error_msg = f"Failed to write excluded deals: {e}"
            print(f"✗ {error_msg}")
            update_checkpoint_progress(checkpoint_path, "excluded_deals", success=False, error=str(e))
            raise
    else:
        print("[2/4] Excluded deals already written (skipping)")

    # Step 3: Unverified Deals
    if not progress["unverified_deals_written"] or force_overwrite:
        try:
            print(f"[3/4] Writing {len(unverified_deals)} unverified deals...")
            append_unverified_deals(spreadsheet, unverified_deals, scan_period)
            update_checkpoint_progress(checkpoint_path, "unverified_deals", success=True)
            print("✓ Unverified deals written")
            time.sleep(1)  # Rate limit
        except Exception as e:
            error_msg = f"Failed to write unverified deals: {e}"
            print(f"✗ {error_msg}")
            update_checkpoint_progress(checkpoint_path, "unverified_deals", success=False, error=str(e))
            raise
    else:
        print("[3/4] Unverified deals already written (skipping)")

    # Step 4: Executive Summary
    if not progress["executive_summary_written"] or force_overwrite:
        try:
            print("[4/4] Updating executive summary...")
            all_deals = load_existing_deals(spreadsheet)
            validation_stats = checkpoint["validation_stats"]

            update_executive_summary(
                spreadsheet, new_deals, all_deals,
                len(excluded_deals), len(unverified_deals),
                scan_period, validation_stats
            )
            update_checkpoint_progress(checkpoint_path, "executive_summary", success=True)
            print("✓ Executive summary updated")
        except Exception as e:
            error_msg = f"Failed to update executive summary: {e}"
            print(f"✗ {error_msg}")
            update_checkpoint_progress(checkpoint_path, "executive_summary", success=False, error=str(e))
            raise
    else:
        print("[4/4] Executive summary already written (skipping)")

    print()
    print("=" * 60)
    print("WRITE COMPLETE")
    print("=" * 60)
    print(f"Google Sheet: {sheet_url}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Retry Google Sheets write from checkpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Retry latest checkpoint
  python src/retry_write.py

  # Retry specific checkpoint
  python src/retry_write.py --checkpoint data/checkpoints/checkpoint_2025-01_*.json

  # Force overwrite (rewrite everything)
  python src/retry_write.py --force
        """
    )

    parser.add_argument(
        "--checkpoint",
        help="Path to specific checkpoint file (default: latest)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite all data (ignore write progress)"
    )

    args = parser.parse_args()

    # Find checkpoint
    try:
        if args.checkpoint:
            checkpoint_path = args.checkpoint
            print(f"Using specified checkpoint: {checkpoint_path}")
        else:
            checkpoint_path = find_latest_checkpoint()
            print(f"Using latest checkpoint: {checkpoint_path}")

        checkpoint = load_checkpoint(checkpoint_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading checkpoint: {e}", file=sys.stderr)
        return 1

    print()

    # Display checkpoint metadata
    metadata = checkpoint["metadata"]
    print("CHECKPOINT METADATA")
    print("=" * 60)
    print(f"Scan period:     {metadata['scan_period']}")
    print(f"Date range:      {metadata['scan_dates']['start_date']} to {metadata['scan_dates']['end_date']}")
    print(f"Created:         {metadata['timestamp']}")
    print(f"Companies:       {metadata['total_companies_scanned']}")
    print(f"Test mode:       {metadata['test_mode']}")
    print()

    # Write to Sheets
    try:
        write_to_sheets(checkpoint, checkpoint_path, force_overwrite=args.force)
        return 0
    except Exception as e:
        print(f"\n✗ Write failed: {e}", file=sys.stderr)
        print(f"\nCheckpoint preserved at: {checkpoint_path}")
        print("Check the error_log in checkpoint file for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
