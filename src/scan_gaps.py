#!/usr/bin/env python3
"""
Follow-up scan for companies missed due to API errors in the main run.

Scans 4 A&B companies individually and 30 C&D companies in batches,
then runs Tier 3/4 verification and writes results to Sheets + Excel.

Usage:
    python src/scan_gaps.py
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from matcher import load_company_list, fuzzy_match, split_by_tier
from scanner import (
    run_tier2_ab_scans, run_tier2_scans,
    run_tier3_verification, run_tier4_research
)
from sheets_output import (
    open_sheet, ensure_sheet_structure, load_existing_deals,
    build_dedup_state, append_new_deals, append_excluded_deals,
    append_unverified_deals, update_executive_summary, get_sheet_url
)
from dedup import generate_deal_id, is_new_alert, update_state_in_memory, categorize_candidate
from source_validator import run_pre_validation_qa, apply_pre_validation_flags, validate_all_deals
from checkpoint_manager import save_progressive, make_checkpoint_path, save_excel_backup


START_DATE = "2022-01-01"
END_DATE = "2026-02-16"

# A&B companies missed (by clean_name)
MISSED_AB_NAMES = [
    "Origin Energy Australia",
    "Snowy Hydro",
    "Southern California Edison",
    "Southern Copper Corporation",
]

# C&D batch indices missed (1-indexed)
MISSED_CD_BATCHES = [84, 85, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 99, 101]


def main():
    print("=" * 60)
    print("GAP SCAN: Recovering missed companies")
    print("=" * 60)

    # Load full company list
    companies = load_company_list("data/PG_Acct_List.xlsx")
    ab_companies, cd_companies = split_by_tier(companies)

    # Extract missed A&B companies
    missed_ab = [c for c in ab_companies if c["clean_name"] in MISSED_AB_NAMES]
    print(f"Missed A&B: {len(missed_ab)} companies")

    # Extract missed C&D companies from batch indices
    missed_cd = []
    for b in MISSED_CD_BATCHES:
        start = (b - 1) * 2
        end = b * 2
        missed_cd.extend(cd_companies[start:end])
    print(f"Missed C&D: {len(missed_cd)} companies")
    print()

    # Connect to Sheets
    spreadsheet = open_sheet()
    ensure_sheet_structure(spreadsheet)
    existing_deals = load_existing_deals(spreadsheet)
    state = build_dedup_state(existing_deals)
    sheet_url = get_sheet_url(spreadsheet)
    print(f"Connected to Sheets: {sheet_url}")
    print(f"Existing deals: {len(existing_deals)}\n")

    # Checkpoint
    ckpt_path = make_checkpoint_path("gaps")
    ckpt = {"completed_steps": []}
    save_progressive(ckpt_path, ckpt)
    print(f"Checkpoint: {ckpt_path}\n")

    # --- Tier 2 A&B (exhaustive, 25 searches) ---
    tier2_ab_deals = run_tier2_ab_scans(missed_ab, START_DATE, END_DATE, max_uses=25)

    # --- Tier 2 C&D (batches of 2, 15 searches) ---
    tier2_cd_deals = run_tier2_scans(missed_cd, START_DATE, END_DATE,
                                     batch_size=2, max_uses=15)

    raw_candidates = tier2_ab_deals + tier2_cd_deals
    print(f"\nCombined: {len(raw_candidates)} raw deals")

    # Dedup
    unique = {}
    for deal in raw_candidates:
        did = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))
        if did not in unique:
            unique[did] = deal
    raw_candidates = list(unique.values())
    print(f"Deduplicated: {len(raw_candidates)} unique\n")

    # Fuzzy match
    matched = []
    for candidate in raw_candidates:
        match_acq = fuzzy_match(candidate.get("acquiror", ""), companies)
        match_tgt = fuzzy_match(candidate.get("target", ""), companies)
        if match_acq or match_tgt:
            match = match_acq if match_acq else match_tgt
            candidate["pg_account_name"] = match["account_name"]
            candidate["clean_name"] = match["clean_name"]
            candidate["pg_match_side"] = "acquiror" if match_acq else "target"
            matched.append(candidate)
    print(f"Matched to PG accounts: {len(matched)}\n")

    # Smart dedup
    to_verify = []
    for candidate in matched:
        category, _ = categorize_candidate(candidate, state)
        if category != "exact_match":
            to_verify.append(candidate)
    print(f"New deals to verify: {len(to_verify)}\n")

    # Tier 3
    print(f"TIER 3: Verifying {len(to_verify)} deals")
    print("=" * 60)
    verified = []
    excluded = []
    unverified = []

    for i, candidate in enumerate(to_verify, 1):
        print(f"[{i}/{len(to_verify)}] {candidate.get('acquiror')} -> {candidate.get('target')}")
        try:
            result = run_tier3_verification(candidate)
        except Exception as e:
            print(f"    Error: {e}")
            result = {"verified": False, "reason": str(e)}

        if result.get("verified") is False:
            if result.get("excluded"):
                excluded.append({
                    "acquiror": candidate.get("acquiror", ""),
                    "target": candidate.get("target", ""),
                    "deal_value": candidate.get("deal_value", ""),
                    "sector": candidate.get("sector", ""),
                    "description": candidate.get("description", ""),
                    "exclusion_reason": result.get("exclusion_reason", "Could not verify")
                })
            else:
                unverified.append({
                    "acquiror": candidate.get("acquiror", ""),
                    "target": candidate.get("target", ""),
                    "deal_status": candidate.get("deal_status", ""),
                    "sector": candidate.get("sector", ""),
                    "description": candidate.get("description", ""),
                    "source_link": candidate.get("source_link", ""),
                    "validation_failure_reason": result.get("reason", "Unknown")
                })
        else:
            verified.append(result)

    print(f"\nTier 3: {len(verified)} verified, {len(excluded)} excluded, {len(unverified)} unverified\n")

    # Tier 4
    if verified:
        print(f"TIER 4: Researching {len(verified)} deals")
        print("=" * 60)
        for i, deal in enumerate(verified, 1):
            print(f"[{i}/{len(verified)}] {deal.get('acquiror')} -> {deal.get('target')}")
            try:
                deal["opportunity"] = run_tier4_research(deal)
            except Exception as e:
                deal["opportunity"] = f"MONITOR: Research error - {e}"
        print()

    # Source validation
    print("SOURCE VALIDATION")
    print("=" * 60)
    if verified:
        qa_results = run_pre_validation_qa(verified)
        print(qa_results["summary"])
        verified = apply_pre_validation_flags(verified, qa_results)

        client = anthropic.Anthropic()
        source_ok, source_fail = validate_all_deals(verified, client)

        for deal in source_fail:
            unverified.append({
                "acquiror": deal.get("acquiror", ""),
                "target": deal.get("target", ""),
                "deal_status": deal.get("deal_status", ""),
                "sector": deal.get("sector", ""),
                "description": deal.get("description", ""),
                "source_link": deal.get("source_link", ""),
                "validation_failure_reason": deal.get("validation_failure_reason", "No valid source")
            })
        verified = source_ok

    # New alert check
    new_deals = []
    for deal in verified:
        did = generate_deal_id(deal.get("acquiror", ""), deal.get("target", ""))
        deal["deal_id"] = did
        deal["stages_reported"] = [deal.get("deal_status", "").lower()]
        if is_new_alert(deal, state):
            new_deals.append(deal)
            update_state_in_memory(deal, state)

    print(f"\nNew alerts: {len(new_deals)}\n")

    # Save Excel
    excel_path = ckpt_path.replace(".json", ".xlsx")
    save_excel_backup(new_deals, excluded, unverified, excel_path)
    print(f"Excel backup: {excel_path}")

    # Write to Sheets
    print("Writing to Google Sheets...")
    for deal in new_deals:
        deal.setdefault("date_rumor", "")
        deal.setdefault("date_announced", "")
        deal.setdefault("date_closed", "")

    append_new_deals(spreadsheet, new_deals, f"custom:{START_DATE}:{END_DATE}")
    time.sleep(1)
    append_excluded_deals(spreadsheet, excluded, f"custom:{START_DATE}:{END_DATE}")
    time.sleep(1)
    append_unverified_deals(spreadsheet, unverified, f"custom:{START_DATE}:{END_DATE}")
    print("Done writing to Sheets\n")

    # Summary
    print("=" * 60)
    print("GAP SCAN COMPLETE")
    print("=" * 60)
    print(f"New deals: {len(new_deals)}")
    print(f"Excluded: {len(excluded)}")
    print(f"Unverified: {len(unverified)}")
    print(f"Excel: {excel_path}")
    print(f"Sheet: {sheet_url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
