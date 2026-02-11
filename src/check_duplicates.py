#!/usr/bin/env python3
"""Quick script to check if specific duplicates still exist."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sheets_output import open_sheet

spreadsheet = open_sheet()
ws = spreadsheet.worksheet('Deals')
all_rows = ws.get_all_values()

# Find header
header_idx = 0
for i, row in enumerate(all_rows):
    if row and row[0] == 'PG Account Name':
        header_idx = i
        break

header = all_rows[header_idx]
col_idx = {h: i for i, h in enumerate(header)}

# Check for specific duplicates
print('Checking for duplicates...\n')

# 1. TotalEnergies → Zeeland
print('1. TotalEnergies → Zeeland Refinery:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if 'zeeland' in target:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')

# 2. Agnico Eagle → O3 Mining
print('2. Agnico Eagle → O3 Mining:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if 'o3 mining' in target:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')

# 3. BAE Systems → Ball Aerospace
print('3. BAE Systems → Ball Aerospace:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if 'ball aerospace' in target:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')

# 4. INEOS → CNOOC
print('4. INEOS → CNOOC:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if 'cnooc' in target and len(row[col_idx['Acquiror']]) > 0:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')

# 5. Woodside → OCI
print('5. Woodside → OCI:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if ('oci global' in target or 'oci clean ammonia' in target) and len(row[col_idx['Acquiror']]) > 0:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')

# 6. Svenska Cellulosa → Persson Invest
print('6. Svenska Cellulosa → Persson Invest:')
count = 0
for i, row in enumerate(all_rows[header_idx+1:], start=header_idx+2):
    if len(row) > col_idx['Target']:
        target = row[col_idx['Target']].lower()
        if 'persson invest' in target:
            print(f'  Row {i}: {row[col_idx["Acquiror"]]} → {row[col_idx["Target"]]}')
            count += 1
print(f'  Total: {count} entries\n')
