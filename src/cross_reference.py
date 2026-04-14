"""
Cross-reference Scanner Output deals against Pitchbook M&A History.
Adds a column to the scanner output indicating Pitchbook matches.
Reports deals unique to each source.
"""

import pandas as pd
import re
import os
from difflib import SequenceMatcher

# --- Paths ---
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNER_PATH = os.path.join(BASE, "data", "Scanner Output",
                            "Agentic Scanner - PG_MA_Scanner_Deals Feb 16 2026.xlsx")
PITCHBOOK_PATH = os.path.join(BASE, "data", "Other Reference Docs",
                              "Pitchbook - M&A_History_Since2021 (1).xlsx")


def normalize_name(name):
    """Normalize company name for fuzzy matching."""
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" inc.", " inc", " corp.", " corp", " ltd.", " ltd",
                   " llc", " plc", " n.v.", " nv", " s.a.", " sa",
                   " ag", " se", " co.", " co", " group", " holdings",
                   " international", " intl", " limited"]:
        name = name.replace(suffix, "")
    # Remove parenthetical stock tickers like (NYS: VST)
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove special characters
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def fuzzy_match(name1, name2, threshold=0.80):
    """Check if two names match above threshold."""
    if not name1 or not name2:
        return False
    # Exact match after normalization
    if name1 == name2:
        return True
    # One contains the other
    if name1 in name2 or name2 in name1:
        return True
    # Sequence matcher
    ratio = SequenceMatcher(None, name1, name2).ratio()
    return ratio >= threshold


def build_name_index(names):
    """Build a dict of normalized -> original names for fast lookup."""
    index = {}
    for name in names:
        norm = normalize_name(name)
        if norm:
            index[norm] = name
    return index


def find_match(target_norm, acquiror_norm, pb_targets_norm, pb_investors_norm,
               pb_rows, threshold=0.80):
    """
    Find a matching Pitchbook row for a scanner deal.
    Returns (matched_bool, match_details_str).
    Matches on target name primarily, with acquiror as confirmation.
    """
    best_match = None
    best_score = 0

    for idx, (pb_target, pb_investor) in enumerate(zip(pb_targets_norm, pb_investors_norm)):
        # Score target match
        if not target_norm or not pb_target:
            continue

        # Exact or containment match on target
        if target_norm == pb_target:
            target_score = 1.0
        elif target_norm in pb_target or pb_target in target_norm:
            target_score = 0.95
        else:
            target_score = SequenceMatcher(None, target_norm, pb_target).ratio()

        if target_score < 0.70:
            continue

        # Boost if acquiror also matches
        acquiror_score = 0
        if acquiror_norm and pb_investor:
            if acquiror_norm == pb_investor:
                acquiror_score = 1.0
            elif acquiror_norm in pb_investor or pb_investor in acquiror_norm:
                acquiror_score = 0.95
            else:
                acquiror_score = SequenceMatcher(None, acquiror_norm, pb_investor).ratio()

        # Combined score: target is primary, acquiror is bonus
        combined = target_score * 0.6 + acquiror_score * 0.4

        if combined > best_score:
            best_score = combined
            best_match = idx

    if best_match is not None and best_score >= threshold:
        row = pb_rows.iloc[best_match]
        return True, f"PB Match: {row.get('Companies', '')} / {row.get('Investors', '')} (score={best_score:.2f})"

    return False, ""


def main():
    print("=" * 80)
    print("CROSS-REFERENCE: Scanner Output vs Pitchbook M&A History")
    print("=" * 80)

    # --- Load data ---
    print("\nLoading Scanner Output...")
    scanner_df = pd.read_excel(SCANNER_PATH, sheet_name="New Deals")
    # Filter out week-divider rows (they have NaN in Target column)
    scanner_deals = scanner_df[scanner_df['Target'].notna() & (scanner_df['Target'] != '')].copy()
    print(f"  Scanner deals (after filtering dividers): {len(scanner_deals)}")

    print("Loading Pitchbook Customers tab...")
    pb_customers = pd.read_excel(PITCHBOOK_PATH, sheet_name="Customers", header=1)
    # Drop any fully-empty rows
    pb_customers = pb_customers.dropna(how='all').reset_index(drop=True)
    print(f"  Pitchbook customer deals: {len(pb_customers)}")

    # --- Normalize names ---
    print("\nNormalizing names for matching...")
    scanner_deals['_target_norm'] = scanner_deals['Target'].apply(normalize_name)
    scanner_deals['_acquiror_norm'] = scanner_deals['Acquiror'].apply(normalize_name)

    pb_targets_norm = pb_customers['Companies'].apply(normalize_name).tolist()
    pb_investors_norm = pb_customers['Investors'].apply(normalize_name).tolist()

    # --- Cross-reference: Scanner -> Pitchbook ---
    print("\nMatching scanner deals against Pitchbook...")
    in_pitchbook = []
    match_details = []
    matched_pb_indices = set()

    for idx, row in scanner_deals.iterrows():
        found, detail = find_match(
            row['_target_norm'], row['_acquiror_norm'],
            pb_targets_norm, pb_investors_norm,
            pb_customers, threshold=0.55
        )
        in_pitchbook.append("Yes" if found else "No")
        match_details.append(detail)
        if found:
            # Track which PB rows were matched
            # Re-find the index for tracking
            for pb_idx, (pb_t, pb_i) in enumerate(zip(pb_targets_norm, pb_investors_norm)):
                t_norm = row['_target_norm']
                if t_norm and pb_t and (t_norm == pb_t or t_norm in pb_t or pb_t in t_norm or
                                        SequenceMatcher(None, t_norm, pb_t).ratio() >= 0.70):
                    matched_pb_indices.add(pb_idx)

    scanner_deals['In Pitchbook?'] = in_pitchbook
    scanner_deals['Pitchbook Match Detail'] = match_details

    # --- Stats ---
    n_in_pb = sum(1 for x in in_pitchbook if x == "Yes")
    n_new = sum(1 for x in in_pitchbook if x == "No")
    print(f"\n{'=' * 60}")
    print(f"RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total scanner deals:           {len(scanner_deals)}")
    print(f"  Also in Pitchbook:           {n_in_pb}")
    print(f"  NEW (not in Pitchbook):      {n_new}")
    print(f"")
    print(f"Total Pitchbook customer deals: {len(pb_customers)}")
    print(f"  Matched by scanner:          {len(matched_pb_indices)}")
    print(f"  Not in scanner output:       {len(pb_customers) - len(matched_pb_indices)}")

    # --- Add column to Pitchbook file ---
    print(f"\nAdding 'In Scanner Output?' column to Pitchbook Customers tab...")
    pb_in_scanner = []
    for pb_idx in range(len(pb_customers)):
        pb_in_scanner.append("Yes" if pb_idx in matched_pb_indices else "No")
    pb_customers['In Scanner Output?'] = pb_in_scanner

    # --- Save updated Pitchbook file ---
    # Read prospects tab to preserve it (same header offset)
    pb_prospects = pd.read_excel(PITCHBOOK_PATH, sheet_name="Prospects", header=1)
    pb_prospects = pb_prospects.dropna(how='all').reset_index(drop=True)

    with pd.ExcelWriter(PITCHBOOK_PATH, engine='openpyxl') as writer:
        pb_customers.to_excel(writer, sheet_name='Customers', index=False)
        pb_prospects.to_excel(writer, sheet_name='Prospects', index=False)
    print(f"  Saved updated Pitchbook file with new column.")

    # --- Save updated Scanner file ---
    # Drop internal columns before saving
    scanner_out = scanner_deals.drop(columns=['_target_norm', '_acquiror_norm'])

    # Read other sheets to preserve them
    excluded_df = pd.read_excel(SCANNER_PATH, sheet_name="Excluded")
    unverified_df = pd.read_excel(SCANNER_PATH, sheet_name="Unverified")

    # We need to re-insert the week divider rows
    # Actually, let's just write the deals sheet with the new columns alongside the original full sheet
    # Read the original full sheet including dividers
    full_scanner = pd.read_excel(SCANNER_PATH, sheet_name="New Deals")

    # Map the new columns back to the full dataframe
    full_scanner['In Pitchbook?'] = ''
    full_scanner['Pitchbook Match Detail'] = ''
    for orig_idx, row in scanner_out.iterrows():
        if orig_idx in full_scanner.index:
            full_scanner.at[orig_idx, 'In Pitchbook?'] = row['In Pitchbook?']
            full_scanner.at[orig_idx, 'Pitchbook Match Detail'] = row['Pitchbook Match Detail']

    with pd.ExcelWriter(SCANNER_PATH, engine='openpyxl') as writer:
        full_scanner.to_excel(writer, sheet_name='New Deals', index=False)
        excluded_df.to_excel(writer, sheet_name='Excluded', index=False)
        unverified_df.to_excel(writer, sheet_name='Unverified', index=False)
    print(f"  Saved updated Scanner file with 'In Pitchbook?' column.")

    # --- Print NEW deals (not in Pitchbook) ---
    new_deals = scanner_out[scanner_out['In Pitchbook?'] == 'No']
    print(f"\n{'=' * 60}")
    print(f"NEW DEALS NOT IN PITCHBOOK ({len(new_deals)} total)")
    print(f"{'=' * 60}")
    for _, row in new_deals.head(50).iterrows():
        acq = row.get('Acquiror', '?')
        tgt = row.get('Target', '?')
        date = row.get('Date Announced', row.get('Date Closed', '?'))
        status = row.get('Deal Status', '?')
        print(f"  {acq} -> {tgt} | {date} | {status}")

    if len(new_deals) > 50:
        print(f"  ... and {len(new_deals) - 50} more (see Excel file)")

    # --- Print Pitchbook deals NOT in scanner ---
    pb_not_in_scanner = pb_customers[pb_customers['In Scanner Output?'] == 'No']
    print(f"\n{'=' * 60}")
    print(f"PITCHBOOK DEALS NOT IN SCANNER ({len(pb_not_in_scanner)} total)")
    print(f"{'=' * 60}")
    for _, row in pb_not_in_scanner.head(30).iterrows():
        company = row.get('Companies', '?')
        investor = row.get('Investors', '?')
        deal_date = row.get('Deal Date', '?')
        print(f"  {investor} -> {company} | {deal_date}")

    if len(pb_not_in_scanner) > 30:
        print(f"  ... and {len(pb_not_in_scanner) - 30} more (see Excel file)")


if __name__ == "__main__":
    main()
