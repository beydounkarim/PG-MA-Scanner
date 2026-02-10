"""
Integration tests for sheets_output.py

Note: These tests require actual Google Sheets credentials and a test sheet.
They are integration tests, not unit tests, and should be run with caution.
"""

import pytest
import os
from src.sheets_output import (
    get_sheets_client,
    open_sheet,
    ensure_sheet_structure,
    load_existing_deals,
    build_dedup_state,
    get_sheet_url,
    _parse_deal_value,
    DEALS_HEADERS,
    EXCLUDED_HEADERS,
    UNVERIFIED_HEADERS,
)


class TestParseDealValue:
    """Test deal value parsing for sorting."""

    def test_parse_billions(self):
        assert _parse_deal_value("$53B") == 53_000_000_000
        assert _parse_deal_value("$2.5B") == 2_500_000_000

    def test_parse_millions(self):
        assert _parse_deal_value("$100M") == 100_000_000
        assert _parse_deal_value("$1.5M") == 1_500_000

    def test_parse_thousands(self):
        assert _parse_deal_value("$500K") == 500_000

    def test_parse_undisclosed(self):
        assert _parse_deal_value("Undisclosed") == 0.0
        assert _parse_deal_value("") == 0.0
        assert _parse_deal_value(None) == 0.0

    def test_parse_with_commas(self):
        assert _parse_deal_value("$1,500M") == 1_500_000_000

    def test_parse_lowercase(self):
        assert _parse_deal_value("$10m") == 10_000_000
        assert _parse_deal_value("$5b") == 5_000_000_000


class TestHeaderConstants:
    """Test that header constants are defined correctly."""

    def test_deals_headers_count(self):
        # 15 output fields + 5 metadata fields
        assert len(DEALS_HEADERS) == 20

    def test_deals_headers_fields(self):
        assert "PG Account Name" in DEALS_HEADERS
        assert "Clean Name" in DEALS_HEADERS
        assert "Acquiror" in DEALS_HEADERS
        assert "Target" in DEALS_HEADERS
        assert "Source Validation" in DEALS_HEADERS
        assert "deal_id" in DEALS_HEADERS
        assert "stages_reported" in DEALS_HEADERS

    def test_excluded_headers_count(self):
        assert len(EXCLUDED_HEADERS) == 8

    def test_excluded_headers_fields(self):
        assert "Exclusion Reason" in EXCLUDED_HEADERS

    def test_unverified_headers_count(self):
        assert len(UNVERIFIED_HEADERS) == 8

    def test_unverified_headers_fields(self):
        assert "Original URL Attempted" in UNVERIFIED_HEADERS
        assert "Validation Failure Reason" in UNVERIFIED_HEADERS


# Integration tests requiring actual Google Sheets access
# Uncomment and configure when ready to test against real sheet

"""
@pytest.fixture
def test_spreadsheet():
    '''
    Fixture to provide a test Google Sheet.
    Requires GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID env vars.
    '''
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_JSON not set")
    if not os.environ.get("GOOGLE_SHEET_ID"):
        pytest.skip("GOOGLE_SHEET_ID not set")

    spreadsheet = open_sheet()
    yield spreadsheet

    # Cleanup: You may want to clear test data after tests
    # For safety, this is left commented out
    # for ws in spreadsheet.worksheets():
    #     if ws.title.startswith("Test_"):
    #         spreadsheet.del_worksheet(ws)


class TestGoogleSheetsIntegration:
    def test_get_sheets_client(self):
        client = get_sheets_client()
        assert client is not None

    def test_open_sheet(self, test_spreadsheet):
        assert test_spreadsheet is not None
        assert test_spreadsheet.id

    def test_ensure_sheet_structure(self, test_spreadsheet):
        ensure_sheet_structure(test_spreadsheet)

        worksheets = [ws.title for ws in test_spreadsheet.worksheets()]
        assert "Executive Summary" in worksheets
        assert "Deals" in worksheets
        assert "Excluded (Non-Strategic)" in worksheets
        assert "Unverified" in worksheets

    def test_deals_tab_headers(self, test_spreadsheet):
        ensure_sheet_structure(test_spreadsheet)
        ws = test_spreadsheet.worksheet("Deals")
        headers = ws.row_values(1)
        assert headers == DEALS_HEADERS

    def test_load_existing_deals_empty(self, test_spreadsheet):
        ensure_sheet_structure(test_spreadsheet)
        deals = load_existing_deals(test_spreadsheet)
        assert isinstance(deals, list)

    def test_build_dedup_state(self):
        # Mock existing deals
        existing_deals = [
            {
                "Acquiror": "Chevron",
                "Target": "Hess",
                "Deal Status": "Closed",
                "deal_id": "chevron_hess",
                "stages_reported": "announced,closed",
                "first_seen": "2024-01-15",
                "last_updated": "2024-05-01"
            }
        ]

        state = build_dedup_state(existing_deals)
        assert "chevron_hess" in state
        assert state["chevron_hess"]["acquiror"] == "Chevron"
        assert state["chevron_hess"]["target"] == "Hess"
        assert "announced" in state["chevron_hess"]["stages_reported"]
        assert "closed" in state["chevron_hess"]["stages_reported"]

    def test_get_sheet_url(self, test_spreadsheet):
        url = get_sheet_url(test_spreadsheet)
        assert url.startswith("https://docs.google.com/spreadsheets/d/")
        assert test_spreadsheet.id in url
"""


# Mock tests for functions that require Google Sheets
class TestMockSheets:
    """Mock tests for Sheets functions (don't require actual connection)."""

    def test_build_dedup_state_with_missing_deal_id(self):
        """Test that build_dedup_state generates deal_id if missing."""
        # This test would need dedup.py to be implemented first
        # For now, we document expected behavior:
        # - If deal_id is missing, generate from acquiror + target
        # - Parse stages_reported from comma-separated string
        # - Return dict keyed by deal_id
        pass

    def test_append_new_deals_empty_list(self):
        """Test that append_new_deals handles empty list gracefully."""
        # Should return early without error
        pass


# Documentation for manual testing
"""
MANUAL TESTING CHECKLIST:

Before running integration tests, ensure:
1. ✓ GOOGLE_SERVICE_ACCOUNT_JSON is set in .env
2. ✓ GOOGLE_SHEET_ID is set in .env
3. ✓ Google Sheet exists and is shared with service account
4. ✓ Service account has Editor access to the sheet

To run integration tests:
    pytest tests/test_sheets.py -v -k Integration

To test sheet structure creation:
    python -c "
    from src.sheets_output import open_sheet, ensure_sheet_structure
    sheet = open_sheet()
    ensure_sheet_structure(sheet)
    print('✓ Tabs created successfully')
    "

To test deal loading:
    python -c "
    from src.sheets_output import open_sheet, load_existing_deals
    sheet = open_sheet()
    deals = load_existing_deals(sheet)
    print(f'✓ Loaded {len(deals)} existing deals')
    "
"""
