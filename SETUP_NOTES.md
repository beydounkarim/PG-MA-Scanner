# Setup Notes

## Phase 2 Complete - Next Steps

### Required: Add Company List

You need to place your `PG_Acct_List.xlsx` file in the `data/` directory.

**Required format:**
- File must have two sheets: `A&B Customers` and `C&D Customers`
- Each sheet must have columns: `Account Name` and `Clean Name`
- Example row: `Account Name: "Chevron | NA"`, `Clean Name: "Chevron"`

**Expected:**
- ~651 unique companies after deduplication on `clean_name`
- 17 duplicate `clean_name` entries will be automatically removed (keeping first occurrence)

### Test Period Resolution

You can now test the period resolver:

```bash
# Test period resolution
python src/main.py --period last_week --dry-run
python src/main.py --period 2025 --dry-run
python src/main.py --period custom:2024-06-01:2024-12-31 --dry-run
```

Expected output:
```
============================================================
PG M&A Deal Scanner
============================================================
Period:    last_week
Dates:     2025-02-03 to 2025-02-09
Test mode: No (all companies)
Dry run:   Yes (no writes)
============================================================
```

### Test Company Matcher (when Excel file is ready)

```bash
# Run unit tests
pytest tests/test_matcher.py -v

# Test fuzzy matching manually
python -c "
from src.matcher import load_company_list, fuzzy_match
companies = load_company_list('data/PG_Acct_List.xlsx')
print(f'Loaded {len(companies)} companies')
print(fuzzy_match('Chevron Corporation', companies))
"
```

## What's Implemented

### Phase 1 ✓
- `.env.example` - Environment variable template
- `.gitignore` - Git ignore rules
- `requirements.txt` - Python dependencies
- `README.md` - Project documentation

### Phase 2 ✓
- `src/matcher.py` - Company list loader + fuzzy matching
  - `load_company_list()` - Loads from Excel, deduplicates
  - `fuzzy_match()` - Matches deal companies to PG accounts
  - `normalize_company_name()` - Strips suffixes for comparison
- `src/main.py` - CLI entry point
  - `resolve_period()` - Converts period strings to date ranges
  - `parse_args()` - CLI argument parsing
  - `main()` - Main entry point (pipeline pending)
- `tests/test_matcher.py` - Unit tests for matcher
- `data/` - Directory for PG_Acct_List.xlsx

## Next: Phase 3

Phase 3 will implement Google Sheets integration. Before proceeding, you'll need:

1. **Google Cloud Service Account:**
   - Create a Google Cloud project
   - Enable Google Sheets API and Google Drive API
   - Create a service account and download JSON credentials
   - Store JSON in `.env` as `GOOGLE_SERVICE_ACCOUNT_JSON`

2. **Google Sheet:**
   - Create a new Google Sheet
   - Copy the Sheet ID from the URL
   - Share the sheet with your service account email (Editor access)
   - Store Sheet ID in `.env` as `GOOGLE_SHEET_ID`

3. **Environment Setup:**
   - Copy `.env.example` to `.env`
   - Fill in your API keys and credentials

Ready to proceed with Phase 3 when you have these prerequisites ready!
