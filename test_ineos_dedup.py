#!/usr/bin/env python3
"""Test INEOS deduplication specifically."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dedup import generate_deal_id

# INEOS duplicates from the sheet
print("Testing INEOS duplicate detection:")
print("=" * 80)

id1 = generate_deal_id("INEOS Limited", "TotalEnergies SE (specific petrochemical assets in France)")
id2 = generate_deal_id("INEOS Olefins & Polymers Europe", "TotalEnergies SE (specific petrochemical assets at Lavera, France)")

print(f"Deal 1: INEOS Limited → TotalEnergies SE")
print(f"  ID: {id1}")
print()
print(f"Deal 2: INEOS Olefins & Polymers Europe → TotalEnergies SE")
print(f"  ID: {id2}")
print()
print(f"Result: {'✓ MATCH (will be deduplicated)' if id1 == id2 else '✗ NO MATCH (will be treated as separate deals)'}")
print()

# Additional INEOS test cases
print("\nAdditional INEOS variations:")
test_cases = [
    ("INEOS Group Limited", "Target A"),
    ("INEOS Holdings", "Target A"),
    ("INEOS Energy", "Target A"),
    ("INEOS Chemicals", "Target A"),
]

ids = [generate_deal_id(acq, tgt) for acq, tgt in test_cases]
for i, (acq, tgt) in enumerate(test_cases):
    print(f"{acq} → {tgt}: {ids[i]}")

all_same = len(set(ids)) == 1
print(f"\n{'✓ All normalize to same ID' if all_same else '✗ Different IDs (may be intentional)'}")
