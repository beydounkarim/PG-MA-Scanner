#!/usr/bin/env python3
"""Test the improved deduplication logic."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dedup import generate_deal_id

# Test cases that should generate the same deal_id
test_cases = [
    # Rio Tinto duplicates
    ("Rio Tinto plc", "Sumitomo Chemical Company Limited (aluminum smelting assets)"),
    ("Rio Tinto plc", "Sumitomo Chemical Company Limited's stakes in NZAS and BSL"),

    # INEOS duplicates
    ("INEOS Limited", "TotalEnergies SE (specific petrochemical assets in France)"),
    ("INEOS Olefins & Polymers Europe", "TotalEnergies SE (specific petrochemical assets at Lavera, France)"),

    # Other test cases
    ("Chevron Corporation", "Hess Corp"),
    ("Chevron Corp", "Hess Corporation"),

    # With possessives
    ("Glencore plc", "Teck Resources Limited"),
    ("Glencore", "Teck Resources Limited's coal division"),

    # With "the"
    ("The Dow Chemical Company", "Union Carbide"),
    ("Dow Chemical Company", "Union Carbide"),
]

print("Testing improved deduplication logic:")
print("=" * 80)

# Test Rio Tinto duplicates
print("\n1. Rio Tinto duplicates (should be SAME):")
id1 = generate_deal_id("Rio Tinto plc", "Sumitomo Chemical Company Limited (aluminum smelting assets)")
id2 = generate_deal_id("Rio Tinto plc", "Sumitomo Chemical Company Limited's stakes in NZAS and BSL")
print(f"   Deal 1 ID: {id1}")
print(f"   Deal 2 ID: {id2}")
print(f"   Match: {'✓ YES' if id1 == id2 else '✗ NO (PROBLEM!)'}")

# Test INEOS duplicates
print("\n2. INEOS duplicates (should be SAME):")
id1 = generate_deal_id("INEOS Limited", "TotalEnergies SE (specific petrochemical assets in France)")
id2 = generate_deal_id("INEOS Olefins & Polymers Europe", "TotalEnergies SE (specific petrochemical assets at Lavera, France)")
print(f"   Deal 1 ID: {id1}")
print(f"   Deal 2 ID: {id2}")
print(f"   Match: {'✓ YES' if id1 == id2 else '✗ NO (expected - different acquirors)'}")

# Test Chevron variations
print("\n3. Chevron variations (should be SAME):")
id1 = generate_deal_id("Chevron Corporation", "Hess Corp")
id2 = generate_deal_id("Chevron Corp", "Hess Corporation")
print(f"   Deal 1 ID: {id1}")
print(f"   Deal 2 ID: {id2}")
print(f"   Match: {'✓ YES' if id1 == id2 else '✗ NO (PROBLEM!)'}")

# Test Glencore with possessives
print("\n4. Glencore with possessives (should be SAME):")
id1 = generate_deal_id("Glencore plc", "Teck Resources Limited")
id2 = generate_deal_id("Glencore", "Teck Resources Limited's coal division")
print(f"   Deal 1 ID: {id1}")
print(f"   Deal 2 ID: {id2}")
print(f"   Match: {'✓ YES' if id1 == id2 else '✗ NO (PROBLEM!)'}")

# Test "the" prefix
print("\n5. 'The' prefix variations (should be SAME):")
id1 = generate_deal_id("The Dow Chemical Company", "Union Carbide")
id2 = generate_deal_id("Dow Chemical Company", "Union Carbide")
print(f"   Deal 1 ID: {id1}")
print(f"   Deal 2 ID: {id2}")
print(f"   Match: {'✓ YES' if id1 == id2 else '✗ NO (PROBLEM!)'}")

print("\n" + "=" * 80)
print("All critical duplicates should now be caught!")
