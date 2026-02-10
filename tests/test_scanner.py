"""
Integration tests for scanner.py

Note: These tests require Anthropic API key and make real API calls.
They should be run sparingly to avoid costs.
"""

import pytest
import os
from src.scanner import (
    build_tier1_queries,
    extract_text_from_response,
    extract_json_from_response,
    is_pe_buyer,
)


class TestBuildTier1Queries:
    """Test Tier 1 query construction."""

    def test_short_period_uses_after_before(self):
        """Periods < 3 months should use after:DATE before:DATE format."""
        queries = build_tier1_queries("2025-01-01", "2025-02-28")

        assert len(queries) > 0
        assert "after:2025-01-01 before:2025-02-28" in queries[0]

    def test_full_year_uses_year_number(self):
        """Full year should use just the year number."""
        queries = build_tier1_queries("2025-01-01", "2025-12-31")

        assert len(queries) > 0
        assert "2025" in queries[0]
        assert "after:" not in queries[0]  # Should not use after/before

    def test_multi_year_uses_year_range(self):
        """Multi-year period should use YYYY-YYYY format."""
        queries = build_tier1_queries("2024-01-01", "2025-12-31")

        assert len(queries) > 0
        assert "2024-2025" in queries[0]

    def test_all_sectors_covered(self):
        """Should generate queries for all major sectors."""
        queries = build_tier1_queries("2025-01-01", "2025-12-31")

        # Should have ~20-25 queries
        assert len(queries) >= 20
        assert len(queries) <= 30

        # Check for key sectors
        query_text = " ".join(queries).lower()
        assert "oil gas" in query_text
        assert "mining" in query_text
        assert "chemical" in query_text
        assert "utility" in query_text


class TestExtractJsonFromResponse:
    """Test JSON extraction from Claude responses."""

    def test_extract_from_json_block(self):
        """Should extract from ```json block."""
        class MockResponse:
            def __init__(self, text):
                self.content = [type('obj', (object,), {'type': 'text', 'text': text})]

        response = MockResponse('```json\n[{"deal": "test"}]\n```')
        result = extract_json_from_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["deal"] == "test"

    def test_extract_raw_json(self):
        """Should extract raw JSON without code blocks."""
        class MockResponse:
            def __init__(self, text):
                self.content = [type('obj', (object,), {'type': 'text', 'text': text})]

        response = MockResponse('[{"deal": "test"}]')
        result = extract_json_from_response(response)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_extract_embedded_json(self):
        """Should find JSON embedded in text."""
        class MockResponse:
            def __init__(self, text):
                self.content = [type('obj', (object,), {'type': 'text', 'text': text})]

        response = MockResponse('Here are the deals: [{"deal": "test"}]')
        result = extract_json_from_response(response)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_no_json_returns_empty_list(self):
        """Should return empty list if no JSON found."""
        class MockResponse:
            def __init__(self, text):
                self.content = [type('obj', (object,), {'type': 'text', 'text': text})]

        response = MockResponse('No JSON here')
        result = extract_json_from_response(response)

        assert isinstance(result, list)
        assert len(result) == 0


class TestIsPeBuyer:
    """Test PE/financial buyer detection."""

    def test_detect_kkr(self):
        assert is_pe_buyer("KKR & Co.") is True

    def test_detect_blackstone(self):
        assert is_pe_buyer("Blackstone Group") is True

    def test_detect_carlyle(self):
        assert is_pe_buyer("The Carlyle Group") is True

    def test_detect_berkshire(self):
        assert is_pe_buyer("Berkshire Hathaway") is True

    def test_case_insensitive(self):
        assert is_pe_buyer("APOLLO GLOBAL MANAGEMENT") is True

    def test_operating_company_not_detected(self):
        assert is_pe_buyer("Chevron Corporation") is False
        assert is_pe_buyer("ExxonMobil") is False

    def test_empty_string(self):
        assert is_pe_buyer("") is False


# Integration tests requiring API key
# Uncomment when ready for live testing with API costs

"""
@pytest.fixture
def anthropic_client():
    '''Fixture to provide Anthropic client.'''
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    import anthropic
    return anthropic.Anthropic()


class TestTier1Integration:
    def test_tier1_scan_last_week(self, anthropic_client):
        '''Test Tier 1 scan for last week (live API call).'''
        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=7)

        # This will make ~20-25 real API calls - expensive!
        deals = run_tier1_scans(start.isoformat(), end.isoformat())

        assert isinstance(deals, list)
        # May or may not find deals depending on timing
        if deals:
            assert "acquiror" in deals[0]
            assert "target" in deals[0]
            assert "source_link" in deals[0]


class TestTier2Integration:
    def test_tier2_scan_small_batch(self, anthropic_client):
        '''Test Tier 2 with a small batch of companies.'''
        companies = [
            {"account_name": "Chevron | NA", "clean_name": "Chevron"},
            {"account_name": "Shell | EU", "clean_name": "Shell"},
        ]

        deals = run_tier2_scans(companies, "2024-01-01", "2024-12-31")

        assert isinstance(deals, list)
        # Likely to find some deals for major companies like Chevron/Shell


class TestTier3Integration:
    def test_tier3_verify_known_deal(self, anthropic_client):
        '''Test Tier 3 verification on a known deal.'''
        candidate = {
            "acquiror": "Chevron",
            "target": "Hess",
        }

        result = run_tier3_verification(candidate)

        assert isinstance(result, dict)
        if result.get("verified") is not False:
            assert "source_link" in result
            assert "deal_value" in result


class TestTier4Integration:
    def test_tier4_research(self, anthropic_client):
        '''Test Tier 4 facility research.'''
        deal = {
            "acquiror": "Chevron",
            "target": "Hess",
            "sector": "Oil & Gas"
        }

        opportunity = run_tier4_research(deal)

        assert isinstance(opportunity, str)
        assert len(opportunity) > 0
        # Should contain classification (OFFENSIVE/DEFENSIVE/MONITOR)
        assert any(word in opportunity for word in ["OFFENSIVE", "DEFENSIVE", "MONITOR"])
"""


# Documentation for manual testing
"""
MANUAL TESTING CHECKLIST:

Tier 1 (Industry Scans):
[ ] Test with --period last_week - verify queries have after/before dates
[ ] Test with --period 2025 - verify queries use year number
[ ] Verify ~20-25 API calls made
[ ] Verify results are JSON parseable
[ ] Verify PE firms filtered out
[ ] Check cost: ~$0.75 for Tier 1

Tier 2 (Company Batches):
[ ] Test with 20 companies - verify single batch
[ ] Test with 100 companies - verify 5 batches
[ ] Verify role normalization (Acquiror/Target → acquiror/target)
[ ] Verify counterparty mapping
[ ] Check cost: ~$1.32 for full Tier 2

Tier 3 (Verification):
[ ] Test with known deal (Chevron/Hess) - should verify
[ ] Test with fabricated deal - should return verified: false
[ ] Verify all 15 fields extracted
[ ] Verify source_link is from search results (not constructed)
[ ] Check cost: ~$0.05 per deal

Tier 4 (Facility Research):
[ ] Test with major deal - should return facility details
[ ] Verify classification (OFFENSIVE/DEFENSIVE/MONITOR)
[ ] Verify recommended action present
[ ] Check cost: ~$0.08 per deal

Full Pipeline Test:
[ ] Run on --period last_week --test (20 companies)
[ ] Verify Tiers 1-4 execute in sequence
[ ] Verify total cost < $1 for test run
[ ] Verify no fabricated URLs in final output
"""
