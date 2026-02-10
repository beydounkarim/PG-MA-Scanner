#!/usr/bin/env python3
"""
PG M&A Deal Scanner - Main CLI Entry Point

Usage:
    python src/main.py --period last_week [--test] [--dry-run]
    python src/main.py --period 2025
    python src/main.py --period custom:2024-06-01:2024-12-31 --test
"""

import argparse
import os
import re
import sys
from datetime import date, timedelta
from typing import Tuple

# Add src directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def resolve_period(period_str: str, reference_date: date = None) -> Tuple[str, str]:
    """
    Convert a period string into concrete (start_date, end_date) as YYYY-MM-DD.

    Args:
        period_str: Period specification string
        reference_date: Reference date for relative periods (default: today)

    Returns:
        Tuple of (start_date, end_date) as YYYY-MM-DD strings

    Raises:
        ValueError: If period_str is invalid or ambiguous

    Examples:
        >>> resolve_period("last_week")
        ("2025-01-20", "2025-01-26")  # Previous Mon-Sun

        >>> resolve_period("last_month")
        ("2024-12-01", "2024-12-31")

        >>> resolve_period("last_quarter")
        ("2024-10-01", "2024-12-31")

        >>> resolve_period("last_6_months")
        ("2024-08-12", "2026-02-09")

        >>> resolve_period("2025")
        ("2025-01-01", "2025-12-31")

        >>> resolve_period("2024-Q4")
        ("2024-10-01", "2024-12-31")

        >>> resolve_period("2025-01")
        ("2025-01-01", "2025-01-31")

        >>> resolve_period("custom:2024-06-01:2024-12-31")
        ("2024-06-01", "2024-12-31")
    """
    if reference_date is None:
        reference_date = date.today()

    period_str = period_str.strip().lower()

    # Relative periods
    if period_str == "last_week":
        # Last Monday to Sunday
        days_since_monday = reference_date.weekday()  # 0=Monday, 6=Sunday
        end = reference_date - timedelta(days=days_since_monday + 1)  # Last Sunday
        start = end - timedelta(days=6)  # Last Monday

    elif period_str == "last_month":
        # Previous calendar month
        first_of_this_month = reference_date.replace(day=1)
        end = first_of_this_month - timedelta(days=1)  # Last day of previous month
        start = end.replace(day=1)  # First day of previous month

    elif period_str == "last_quarter":
        # Previous calendar quarter
        current_month = reference_date.month
        current_quarter = (current_month - 1) // 3  # 0=Q1, 1=Q2, 2=Q3, 3=Q4

        if current_quarter == 0:
            # We're in Q1, so last quarter is Q4 of previous year
            start = date(reference_date.year - 1, 10, 1)
            end = date(reference_date.year - 1, 12, 31)
        else:
            # Previous quarter in same year
            start_month = (current_quarter - 1) * 3 + 1
            end_month = start_month + 2
            start = date(reference_date.year, start_month, 1)

            # Last day of quarter
            if end_month == 12:
                end = date(reference_date.year, 12, 31)
            else:
                next_month = date(reference_date.year, end_month + 1, 1)
                end = next_month - timedelta(days=1)

    elif period_str == "last_6_months":
        # Last 182 days
        start = reference_date - timedelta(days=182)
        end = reference_date

    # Absolute periods - full year
    elif re.match(r"^\d{4}$", period_str):
        year = int(period_str)
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    # Absolute periods - specific quarter
    elif re.match(r"^\d{4}-q[1-4]$", period_str):
        year = int(period_str[:4])
        quarter = int(period_str[-1])

        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3

        start = date(year, start_month, 1)

        if end_month == 12:
            end = date(year, 12, 31)
        else:
            next_month = date(year, end_month + 1, 1)
            end = next_month - timedelta(days=1)

    # Absolute periods - specific month
    elif re.match(r"^\d{4}-\d{2}$", period_str):
        year = int(period_str[:4])
        month = int(period_str[5:7])

        if month < 1 or month > 12:
            raise ValueError(f"Invalid month: {month}. Must be 01-12.")

        start = date(year, month, 1)

        if month == 12:
            end = date(year, 12, 31)
        else:
            next_month = date(year, month + 1, 1)
            end = next_month - timedelta(days=1)

    # Custom date range
    elif period_str.startswith("custom:"):
        parts = period_str.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid custom period format: '{period_str}'. "
                f"Expected format: custom:YYYY-MM-DD:YYYY-MM-DD"
            )

        try:
            start = date.fromisoformat(parts[1])
            end = date.fromisoformat(parts[2])
        except ValueError as e:
            raise ValueError(
                f"Invalid date in custom period '{period_str}': {e}"
            )

        if start > end:
            raise ValueError(
                f"Start date {start} is after end date {end}"
            )

    else:
        raise ValueError(
            f"Invalid period: '{period_str}'. "
            f"Supported formats:\n"
            f"  Relative: last_week, last_month, last_quarter, last_6_months\n"
            f"  Year: YYYY (e.g., 2025)\n"
            f"  Quarter: YYYY-QN (e.g., 2024-Q4)\n"
            f"  Month: YYYY-MM (e.g., 2025-01)\n"
            f"  Custom: custom:YYYY-MM-DD:YYYY-MM-DD"
        )

    return (start.isoformat(), end.isoformat())


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PG M&A Deal Scanner - Monitor customer M&A activity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py --period last_week
  python src/main.py --period 2025 --test
  python src/main.py --period custom:2024-06-01:2024-12-31 --dry-run

Period formats:
  last_week, last_month, last_quarter, last_6_months
  YYYY (e.g., 2025)
  YYYY-QN (e.g., 2024-Q4)
  YYYY-MM (e.g., 2025-01)
  custom:YYYY-MM-DD:YYYY-MM-DD
        """
    )

    parser.add_argument(
        "--period",
        required=True,
        help="Scan period (REQUIRED). See examples above."
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: scan only first 20 companies"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: scan but don't write to Google Sheets"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output for debugging"
    )

    return parser.parse_args()


def main():
    """Main entry point - orchestrates the full pipeline."""
    args = parse_args()

    # Import all modules
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file

    import os
    import anthropic

    from matcher import load_company_list, fuzzy_match
    from scanner import run_tier1_scans, run_tier2_scans, run_tier3_verification, run_tier4_research
    from sheets_output import (
        open_sheet, ensure_sheet_structure, load_existing_deals,
        build_dedup_state, append_new_deals, append_excluded_deals,
        append_unverified_deals, update_executive_summary, get_sheet_url
    )
    from dedup import generate_deal_id, is_new_alert, update_state_in_memory
    from source_validator import (
        run_pre_validation_qa, apply_pre_validation_flags, validate_all_deals
    )
    from notifier import notify_all

    # Resolve period to concrete dates
    try:
        start_date, end_date = resolve_period(args.period)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Display scan configuration
    print("=" * 60)
    print("PG M&A Deal Scanner")
    print("=" * 60)
    print(f"Period:    {args.period}")
    print(f"Dates:     {start_date} to {end_date}")
    print(f"Test mode: {'Yes (20 companies)' if args.test else 'No (all companies)'}")
    print(f"Dry run:   {'Yes (no writes)' if args.dry_run else 'No (live writes)'}")
    print("=" * 60)
    print()

    # 1. Load company list
    try:
        companies = load_company_list("data/PG_Acct_List.xlsx")
        if args.test:
            companies = companies[:20]
        print(f"✓ Loaded {len(companies)} companies\n")
    except Exception as e:
        print(f"Error loading company list: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Connect to Google Sheets and load existing deal state
    try:
        spreadsheet = open_sheet()
        ensure_sheet_structure(spreadsheet)
        existing_deals = load_existing_deals(spreadsheet)
        state = build_dedup_state(existing_deals)
        sheet_url = get_sheet_url(spreadsheet)
        print(f"✓ Connected to Google Sheets: {sheet_url}")
        print(f"✓ Loaded {len(existing_deals)} existing deals from Sheets\n")
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}", file=sys.stderr)
        print("Ensure GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are set in .env")
        sys.exit(1)

    # 3. Tier 1: Industry sector scans (SKIPPED - too expensive for current rate limits)
    print("TIER 1: Skipped (using Tier 2 company-specific scans only)\n")
    tier1_deals = []

    # 4. Tier 2: Company batch verification
    tier2_deals = run_tier2_scans(companies, start_date, end_date)

    # 5. Combine and deduplicate raw candidates
    raw_candidates = tier1_deals + tier2_deals
    print(f"\n✓ Combined Tier 1+2: {len(raw_candidates)} raw deals")

    # Deduplicate by acquiror+target
    unique_candidates = {}
    for deal in raw_candidates:
        deal_id = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))
        if deal_id not in unique_candidates:
            unique_candidates[deal_id] = deal

    raw_candidates = list(unique_candidates.values())
    print(f"✓ Deduplicated: {len(raw_candidates)} unique candidates\n")

    # 6. Fuzzy match to company list (BEFORE verification)
    print("Matching deals to PG accounts...")
    matched_candidates = []

    for candidate in raw_candidates:
        # Try matching on acquiror
        match_acq = fuzzy_match(candidate.get("acquiror", ""), companies)
        # Try matching on target
        match_tgt = fuzzy_match(candidate.get("target", ""), companies)

        if match_acq or match_tgt:
            match = match_acq if match_acq else match_tgt
            candidate["pg_account_name"] = match["account_name"]
            candidate["clean_name"] = match["clean_name"]
            # Track which side is the PG customer
            candidate["pg_match_side"] = "acquiror" if match_acq else "target"
            matched_candidates.append(candidate)

    print(f"✓ Matched {len(matched_candidates)} deals to PG accounts\n")

    # 7. Tier 3: Deep dive verification (only on matched deals)
    print("TIER 3: Deep Dive Verification")
    print("=" * 60)

    verified_deals = []
    excluded_deals = []
    unverified_deals = []

    for i, candidate in enumerate(matched_candidates, 1):
        print(f"[{i}/{len(raw_candidates)}] Verifying: "
              f"{candidate.get('acquiror')} → {candidate.get('target')}")

        result = run_tier3_verification(candidate)

        if result.get("verified") is False:
            if result.get("excluded"):
                excluded_deals.append({
                    "acquiror": candidate.get("acquiror", ""),
                    "target": candidate.get("target", ""),
                    "deal_value": candidate.get("deal_value", ""),
                    "sector": candidate.get("sector", ""),
                    "description": candidate.get("description", ""),
                    "exclusion_reason": result.get("exclusion_reason", "Could not verify")
                })
            else:
                unverified_deals.append({
                    "acquiror": candidate.get("acquiror", ""),
                    "target": candidate.get("target", ""),
                    "deal_status": candidate.get("deal_status", ""),
                    "sector": candidate.get("sector", ""),
                    "description": candidate.get("description", ""),
                    "source_link": candidate.get("source_link", ""),
                    "validation_failure_reason": result.get("reason", "Unknown")
                })
        else:
            verified_deals.append(result)

    print(f"\n✓ Tier 3 complete: {len(verified_deals)} verified, "
          f"{len(excluded_deals)} excluded, {len(unverified_deals)} unverified\n")

    # 8. Tier 4: Facility & opportunity research (only on verified deals)
    if verified_deals:
        print("TIER 4: Facility & Opportunity Research")
        print("=" * 60)

        for i, deal in enumerate(verified_deals, 1):
            print(f"[{i}/{len(verified_deals)}] Researching: "
                  f"{deal.get('acquiror')} → {deal.get('target')}")
            opportunity = run_tier4_research(deal)
            deal["opportunity"] = opportunity

        print(f"\n✓ Tier 4 complete\n")

    # 9. SOURCE VALIDATION - QA/QC GATE (mandatory, 4 stages)
    print("SOURCE VALIDATION PIPELINE")
    print("=" * 60)

    if verified_deals:
        # Stage 0: Cross-deal QA
        qa_results = run_pre_validation_qa(verified_deals)
        print(qa_results["summary"])
        verified_deals = apply_pre_validation_flags(verified_deals, qa_results)

        # Stages 1-3: Individual validation
        client = anthropic.Anthropic()
        source_verified, source_failed = validate_all_deals(verified_deals, client)

        # Unverified deals go to Unverified tab
        for deal in source_failed:
            unverified_deals.append({
                "acquiror": deal.get("acquiror", ""),
                "target": deal.get("target", ""),
                "deal_status": deal.get("deal_status", ""),
                "sector": deal.get("sector", ""),
                "description": deal.get("description", ""),
                "source_link": deal.get("source_link", ""),
                "validation_failure_reason": deal.get("validation_failure_reason", "No valid source")
            })

        verified_deals = source_verified

    # 10. Check for new alerts (dedup against Sheets state)
    print("\nChecking for new alerts...")
    new_deals = []

    for deal in verified_deals:
        # Add deal_id and stages_reported
        deal_id = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))
        deal["deal_id"] = deal_id
        deal["stages_reported"] = [deal.get("deal_status", "").lower()]

        if is_new_alert(deal, state):
            new_deals.append(deal)
            update_state_in_memory(deal, state)

    print(f"✓ Found {len(new_deals)} new alerts (after dedup)\n")

    # 11. Write to Google Sheets (unless dry run)
    if not args.dry_run:
        print("Writing to Google Sheets...")

        # Normalize field names for Sheets
        for deal in new_deals:
            # Map verified fields to Sheets column names
            deal.setdefault("date_rumor", "")
            deal.setdefault("date_announced", "")
            deal.setdefault("date_closed", "")

        append_new_deals(spreadsheet, new_deals, args.period)
        append_excluded_deals(spreadsheet, excluded_deals, args.period)
        append_unverified_deals(spreadsheet, unverified_deals, args.period)

        # Refresh all_deals from sheet for accurate summary
        all_deals = load_existing_deals(spreadsheet)

        validation_stats = {
            "verified": sum(1 for d in new_deals
                          if d.get("source_validation") == "✓ Verified"),
            "re_sourced": sum(1 for d in new_deals
                            if d.get("source_validation") == "🔄 Re-sourced"),
            "unverified": len(unverified_deals),
        }

        update_executive_summary(
            spreadsheet, new_deals, all_deals,
            len(excluded_deals), len(unverified_deals),
            args.period, validation_stats
        )

        print(f"✓ Google Sheet updated: {sheet_url}\n")
    else:
        print(f"✓ DRY RUN - no changes written. Sheet: {sheet_url}\n")

    # 12. Send notifications (unless dry run)
    if not args.dry_run and new_deals:
        print("Sending notifications...")
        notify_all(new_deals, sheet_url)
        print()

    # 13. Summary
    print("=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)
    print(f"New deals found: {len(new_deals)}")
    print(f"Excluded (PE/financial): {len(excluded_deals)}")
    print(f"Unverified sources: {len(unverified_deals)}")
    print(f"Google Sheet: {sheet_url}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
