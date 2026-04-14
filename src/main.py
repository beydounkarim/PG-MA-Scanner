#!/usr/bin/env python3
"""
PG M&A Deal Scanner - Main CLI Entry Point

Usage:
    python src/main.py --period last_week [--test] [--dry-run]
    python src/main.py --period 2025
    python src/main.py --period custom:2024-06-01:2024-12-31 --test
    python src/main.py --resume data/checkpoints/scan_20260216_143000.json
"""

import argparse
import json
import os
import re
import sys
import time
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
  python src/main.py --resume data/checkpoints/scan_20260216_143000.json

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
        required=False,
        help="Scan period (REQUIRED unless --resume). See examples above."
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: scan only first 10 A&B + 10 C&D companies"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: scan but don't write to Google Sheets"
    )

    parser.add_argument(
        "--exhaustive",
        action="store_true",
        help="Exhaustive mode: more web searches per query and smaller batches"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output for debugging"
    )

    parser.add_argument(
        "--resume",
        metavar="CHECKPOINT",
        help="Resume a previous scan from checkpoint JSON file"
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

    from matcher import load_company_list, fuzzy_match, split_by_tier
    from scanner import (
        run_tier1_scans, run_tier2_scans, run_tier2_ab_scans,
        run_tier3_verification, run_tier4_research
    )
    from sheets_output import (
        open_sheet, ensure_sheet_structure, load_existing_deals,
        build_dedup_state, append_new_deals, append_excluded_deals,
        append_unverified_deals, update_executive_summary, get_sheet_url
    )
    from dedup import generate_deal_id, is_new_alert, update_state_in_memory, categorize_candidate, fuzzy_dedupe_deals
    from source_validator import (
        run_pre_validation_qa, apply_pre_validation_flags, validate_all_deals
    )
    from notifier import notify_all
    from checkpoint_manager import (
        make_checkpoint_path, save_progressive, load_checkpoint,
        mark_step, is_step_done, save_excel_backup
    )

    # ------------------------------------------------------------------
    # Checkpoint: load or create
    # ------------------------------------------------------------------
    ckpt = {}       # progressive checkpoint dict
    ckpt_path = ""  # file path for checkpoint

    if args.resume:
        ckpt = load_checkpoint(args.resume)
        ckpt_path = args.resume
        # Restore scan config from checkpoint
        if not args.period:
            args.period = ckpt["config"]["period"]
        args.exhaustive = ckpt["config"].get("exhaustive", args.exhaustive)
        args.test = ckpt["config"].get("test", args.test)
        args.dry_run = ckpt["config"].get("dry_run", args.dry_run)
        print(f"\n*** RESUMING from checkpoint: {args.resume}")
        print(f"    Completed steps: {ckpt.get('completed_steps', [])}\n")
    else:
        if not args.period:
            print("Error: --period is required (unless using --resume)", file=sys.stderr)
            sys.exit(1)
        ckpt_path = make_checkpoint_path(args.period.replace(":", "_"))
        ckpt = {"completed_steps": []}

    # Resolve period to concrete dates
    try:
        start_date, end_date = resolve_period(args.period)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Save config into checkpoint
    ckpt["config"] = {
        "period": args.period,
        "start_date": start_date,
        "end_date": end_date,
        "exhaustive": args.exhaustive,
        "test": args.test,
        "dry_run": args.dry_run,
    }
    save_progressive(ckpt_path, ckpt)
    print(f"Checkpoint file: {ckpt_path}\n")

    # ------------------------------------------------------------------
    # 1. Load company list and split by tier
    # ------------------------------------------------------------------
    try:
        companies = load_company_list("data/PG_Acct_List.xlsx")
        ab_companies, cd_companies = split_by_tier(companies)

        if args.test:
            ab_companies = ab_companies[:10]
            cd_companies = cd_companies[:10]
            companies = ab_companies + cd_companies

        print(f"Loaded {len(companies)} companies ({len(ab_companies)} A&B, {len(cd_companies)} C&D)\n")
    except Exception as e:
        print(f"Error loading company list: {e}", file=sys.stderr)
        sys.exit(1)

    # Tier-aware settings
    if args.exhaustive:
        ab_max_uses = 25
        cd_max_uses = 15
        cd_batch_size = 2
        tier1_max_uses = 10
    else:
        ab_max_uses = 20
        cd_max_uses = 10
        cd_batch_size = 2
        tier1_max_uses = 5

    # Display scan configuration
    mode = "exhaustive" if args.exhaustive else "standard"
    print("=" * 60)
    print("PG M&A Deal Scanner")
    print("=" * 60)
    print(f"Period:    {args.period}")
    print(f"Dates:     {start_date} to {end_date}")
    print(f"Mode:      {mode}")
    print(f"Tier 1:    Enabled")
    print(f"Tier 2 AB: {len(ab_companies)} companies (individual, {ab_max_uses} searches each)")
    print(f"Tier 2 CD: {len(cd_companies)} companies (batches of {cd_batch_size}, {cd_max_uses} searches each)")
    print(f"Test mode: {'Yes (10 A&B + 10 C&D)' if args.test else 'No (all companies)'}")
    print(f"Dry run:   {'Yes (no writes)' if args.dry_run else 'No (live writes)'}")
    print("=" * 60)
    print()

    # ------------------------------------------------------------------
    # 2. Connect to Google Sheets and load existing deal state
    # ------------------------------------------------------------------
    try:
        spreadsheet = open_sheet()
        ensure_sheet_structure(spreadsheet)
        existing_deals = load_existing_deals(spreadsheet)
        state = build_dedup_state(existing_deals)
        sheet_url = get_sheet_url(spreadsheet)
        print(f"Connected to Google Sheets: {sheet_url}")
        print(f"Loaded {len(existing_deals)} existing deals from Sheets\n")
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}", file=sys.stderr)
        print("Ensure GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID are set in .env")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Tier 1: Industry sector scans
    # ------------------------------------------------------------------
    if is_step_done(ckpt, "tier1"):
        tier1_deals = ckpt.get("tier1_deals", [])
        print(f"TIER 1: Loaded from checkpoint ({len(tier1_deals)} deals)\n")
    else:
        tier1_deals = run_tier1_scans(start_date, end_date, max_uses=tier1_max_uses)
        ckpt["tier1_deals"] = tier1_deals
        mark_step(ckpt, "tier1")
        save_progressive(ckpt_path, ckpt)
        print(f"  [checkpoint saved after Tier 1]\n")

    # ------------------------------------------------------------------
    # 4a. Tier 2 A&B: Exhaustive individual scans
    # ------------------------------------------------------------------
    if is_step_done(ckpt, "tier2_ab"):
        tier2_ab_deals = ckpt.get("tier2_ab_deals", [])
        print(f"TIER 2 (A&B): Loaded from checkpoint ({len(tier2_ab_deals)} deals)\n")
    else:
        tier2_ab_deals = run_tier2_ab_scans(ab_companies, start_date, end_date,
                                            max_uses=ab_max_uses)
        ckpt["tier2_ab_deals"] = tier2_ab_deals
        mark_step(ckpt, "tier2_ab")
        save_progressive(ckpt_path, ckpt)
        print(f"  [checkpoint saved after Tier 2 A&B]\n")

    # ------------------------------------------------------------------
    # 4b. Tier 2 C&D: Batch scans
    # ------------------------------------------------------------------
    if is_step_done(ckpt, "tier2_cd"):
        tier2_cd_deals = ckpt.get("tier2_cd_deals", [])
        print(f"TIER 2 (C&D): Loaded from checkpoint ({len(tier2_cd_deals)} deals)\n")
    else:
        tier2_cd_deals = run_tier2_scans(cd_companies, start_date, end_date,
                                         batch_size=cd_batch_size,
                                         max_uses=cd_max_uses)
        ckpt["tier2_cd_deals"] = tier2_cd_deals
        mark_step(ckpt, "tier2_cd")
        save_progressive(ckpt_path, ckpt)
        print(f"  [checkpoint saved after Tier 2 C&D]\n")

    tier2_deals = tier2_ab_deals + tier2_cd_deals

    # ------------------------------------------------------------------
    # 5. Combine and deduplicate raw candidates
    # ------------------------------------------------------------------
    raw_candidates = tier1_deals + tier2_deals
    print(f"\nCombined Tier 1+2: {len(raw_candidates)} raw deals")

    # Deduplicate by acquiror+target
    unique_candidates = {}
    for deal in raw_candidates:
        deal_id = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))
        if deal_id not in unique_candidates:
            unique_candidates[deal_id] = deal

    raw_candidates = list(unique_candidates.values())
    print(f"Deduplicated: {len(raw_candidates)} unique candidates\n")

    # ------------------------------------------------------------------
    # 6. Fuzzy match to company list (BEFORE verification)
    # ------------------------------------------------------------------
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

    print(f"Matched {len(matched_candidates)} deals to PG accounts\n")

    # ------------------------------------------------------------------
    # 6.5. SMART DEDUPLICATION - Categorize candidates BEFORE Tier 3-4
    # ------------------------------------------------------------------
    print("SMART DEDUPLICATION: Categorizing candidates...")
    print("=" * 60)

    exact_matches = 0
    status_updates_count = 0
    new_deals_to_verify = []

    for candidate in matched_candidates:
        category, existing_state = categorize_candidate(candidate, state)

        if category == "exact_match":
            # Skip - already in Google Sheets with same status
            exact_matches += 1
        elif category == "status_update":
            # Status changed - verify this as a new alert
            status_updates_count += 1
            new_deals_to_verify.append(candidate)
        else:  # new_deal
            new_deals_to_verify.append(candidate)

    print(f"Exact matches (skip Tier 3-4): {exact_matches}")
    print(f"Status updates (run Tier 3 only): {status_updates_count}")
    print(f"New deals (run full Tier 3-4): {len(new_deals_to_verify) - status_updates_count}\n")

    # Save candidates to checkpoint so we know what to verify
    ckpt["new_deals_to_verify_count"] = len(new_deals_to_verify)
    save_progressive(ckpt_path, ckpt)

    # ------------------------------------------------------------------
    # 7. Tier 3: Deep dive verification (with per-deal checkpoint)
    # ------------------------------------------------------------------
    print(f"TIER 3: Deep Dive Verification ({len(new_deals_to_verify)} deals)")
    print("=" * 60)

    # Restore previously processed Tier 3 results on resume
    verified_deals = list(ckpt.get("tier3_verified", []))
    excluded_deals = list(ckpt.get("tier3_excluded", []))
    unverified_deals = list(ckpt.get("tier3_unverified", []))
    tier3_processed_ids = set(ckpt.get("tier3_processed_ids", []))

    for i, candidate in enumerate(new_deals_to_verify, 1):
        cand_id = generate_deal_id(candidate.get("acquiror", ""), candidate.get("target", ""))
        if cand_id in tier3_processed_ids:
            continue  # Already processed in a previous run

        print(f"[{i}/{len(new_deals_to_verify)}] Verifying: "
              f"{candidate.get('acquiror')} -> {candidate.get('target')}")

        try:
            result = run_tier3_verification(candidate)
        except Exception as e:
            print(f"    Error during Tier 3: {e}")
            result = {"verified": False, "reason": str(e)}

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

        # Progressive checkpoint after EVERY Tier 3 deal
        tier3_processed_ids.add(cand_id)
        ckpt["tier3_verified"] = verified_deals
        ckpt["tier3_excluded"] = excluded_deals
        ckpt["tier3_unverified"] = unverified_deals
        ckpt["tier3_processed_ids"] = list(tier3_processed_ids)
        save_progressive(ckpt_path, ckpt)

    mark_step(ckpt, "tier3")
    save_progressive(ckpt_path, ckpt)

    print(f"\nTier 3 complete: {len(verified_deals)} verified, "
          f"{len(excluded_deals)} excluded, {len(unverified_deals)} unverified\n")

    # ------------------------------------------------------------------
    # 8. Tier 4: Facility & opportunity research (with per-deal checkpoint)
    # ------------------------------------------------------------------
    if verified_deals:
        print("TIER 4: Facility & Opportunity Research")
        print("=" * 60)

        tier4_done_ids = set(ckpt.get("tier4_done_ids", []))

        for i, deal in enumerate(verified_deals, 1):
            deal_id = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))

            if deal_id in tier4_done_ids:
                # Already researched — opportunity field is already populated
                # (restored from checkpoint verified_deals list)
                continue

            print(f"[{i}/{len(verified_deals)}] Researching: "
                  f"{deal.get('acquiror')} -> {deal.get('target')}")

            try:
                opportunity = run_tier4_research(deal)
            except Exception as e:
                print(f"    Error during Tier 4: {e}")
                opportunity = f"MONITOR: Research error - {str(e)}"

            deal["opportunity"] = opportunity

            # Progressive checkpoint after EVERY Tier 4 deal
            tier4_done_ids.add(deal_id)
            ckpt["tier3_verified"] = verified_deals  # updated with opportunity
            ckpt["tier4_done_ids"] = list(tier4_done_ids)
            save_progressive(ckpt_path, ckpt)

        mark_step(ckpt, "tier4")
        save_progressive(ckpt_path, ckpt)
        print(f"\nTier 4 complete\n")

    # ------------------------------------------------------------------
    # 9. SOURCE VALIDATION - QA/QC GATE (mandatory, 4 stages)
    # ------------------------------------------------------------------
    print("SOURCE VALIDATION PIPELINE")
    print("=" * 60)

    if verified_deals and not is_step_done(ckpt, "source_validation"):
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

        # Save post-validation state
        ckpt["validated_verified"] = verified_deals
        ckpt["final_excluded"] = excluded_deals
        ckpt["final_unverified"] = unverified_deals
        mark_step(ckpt, "source_validation")
        save_progressive(ckpt_path, ckpt)
    elif is_step_done(ckpt, "source_validation"):
        verified_deals = ckpt.get("validated_verified", verified_deals)
        excluded_deals = ckpt.get("final_excluded", excluded_deals)
        unverified_deals = ckpt.get("final_unverified", unverified_deals)
        print("Source validation: Loaded from checkpoint\n")

    # ------------------------------------------------------------------
    # 10. Check for new alerts (dedup against Sheets state)
    # ------------------------------------------------------------------
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

    print(f"Found {len(new_deals)} new alerts (after dedup)\n")

    # Fuzzy dedup to catch duplicates with different name framing
    if len(new_deals) > 1:
        new_deals = fuzzy_dedupe_deals(new_deals, verbose=args.verbose)
        print(f"After fuzzy dedup: {len(new_deals)} unique deals\n")

    # Save final new_deals to checkpoint
    ckpt["new_deals"] = new_deals
    save_progressive(ckpt_path, ckpt)

    # ------------------------------------------------------------------
    # 10.5. Save Excel backup (always, regardless of dry-run)
    # ------------------------------------------------------------------
    excel_path = ckpt_path.replace(".json", ".xlsx")
    print(f"Saving Excel backup: {excel_path}")
    save_excel_backup(new_deals, excluded_deals, unverified_deals, excel_path)
    ckpt["excel_backup"] = excel_path
    save_progressive(ckpt_path, ckpt)
    print(f"Excel backup saved: {excel_path}\n")

    # ------------------------------------------------------------------
    # 11. Write to Google Sheets (unless dry run)
    # ------------------------------------------------------------------
    if not args.dry_run:
        print("Writing to Google Sheets with rate limiting...")
        from sheets_output import update_checkpoint_progress

        # Normalize field names for Sheets
        for deal in new_deals:
            # Map verified fields to Sheets column names
            deal.setdefault("date_rumor", "")
            deal.setdefault("date_announced", "")
            deal.setdefault("date_closed", "")

        try:
            # Write new deals
            print(f"Writing {len(new_deals)} new deals...")
            append_new_deals(spreadsheet, new_deals, args.period)
            print("New deals written")

            # Rate limit: 1 second between major operations
            time.sleep(1)

            # Write excluded deals
            print(f"Writing {len(excluded_deals)} excluded deals...")
            append_excluded_deals(spreadsheet, excluded_deals, args.period)
            print("Excluded deals written")

            # Rate limit
            time.sleep(1)

            # Write unverified deals
            print(f"Writing {len(unverified_deals)} unverified deals...")
            append_unverified_deals(spreadsheet, unverified_deals, args.period)
            print("Unverified deals written")

            # Rate limit
            time.sleep(1)

        except Exception as e:
            print(f"\nError writing to Sheets: {e}")
            print(f"Checkpoint saved at: {ckpt_path}")
            print(f"Excel backup at: {excel_path}")
            print("Fix the issue and use --resume to continue")
            sys.exit(1)

        # Refresh all_deals from sheet for accurate summary
        all_deals = load_existing_deals(spreadsheet)

        validation_stats = {
            "verified": sum(1 for d in new_deals
                          if d.get("source_validation") == "✓ Verified"),
            "re_sourced": sum(1 for d in new_deals
                            if d.get("source_validation") == "🔄 Re-sourced"),
            "unverified": len(unverified_deals),
        }

        print("Updating executive summary...")
        update_executive_summary(
            spreadsheet, new_deals, all_deals,
            len(excluded_deals), len(unverified_deals),
            args.period, validation_stats
        )
        print("Executive summary updated")

        mark_step(ckpt, "sheets_written")
        save_progressive(ckpt_path, ckpt)

        print(f"\nGoogle Sheet updated: {sheet_url}\n")
    else:
        print(f"DRY RUN - no changes written. Sheet: {sheet_url}\n")

    # 12. Send notifications (unless dry run)
    if not args.dry_run and new_deals:
        print("Sending notifications...")
        notify_all(new_deals, sheet_url)
        print()

    # 13. Summary
    mark_step(ckpt, "complete")
    save_progressive(ckpt_path, ckpt)

    print("=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)
    print(f"New deals found: {len(new_deals)}")
    print(f"Excluded (PE/financial): {len(excluded_deals)}")
    print(f"Unverified sources: {len(unverified_deals)}")
    print(f"Excel backup: {excel_path}")
    print(f"Checkpoint: {ckpt_path}")
    print(f"Google Sheet: {sheet_url}")
    print("=" * 60)

    # Append scan run metrics to reinforcement learning log
    try:
        from reinforcement import append_scan_run_log
        append_scan_run_log(
            period=args.period,
            num_companies=len(companies),
            tier1_count=len(tier1_deals),
            tier2_ab_count=len(tier2_ab_deals),
            tier2_cd_count=len(tier2_cd_deals),
            tier3_verified=len(verified_deals),
            new_deals=len(new_deals),
            excluded=len(excluded_deals),
            unverified=len(unverified_deals),
        )
        print("Reinforcement learning log updated.")
    except Exception:
        pass  # Non-critical

    return 0


if __name__ == "__main__":
    sys.exit(main())
