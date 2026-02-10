"""
Unit tests for matcher.py
"""

import pytest
from src.matcher import load_company_list, fuzzy_match, normalize_company_name


# Mock company list for testing
MOCK_COMPANIES = [
    {"account_name": "Chevron | NA", "clean_name": "Chevron"},
    {"account_name": "BHP | APAC", "clean_name": "BHP"},
    {"account_name": "Shell | EU", "clean_name": "Shell"},
    {"account_name": "Exxon Mobil | NA", "clean_name": "ExxonMobil"},
    {"account_name": "Rio Tinto | APAC", "clean_name": "Rio Tinto"},
]


class TestNormalizeCompanyName:
    """Test company name normalization."""

    def test_remove_corporation_suffix(self):
        assert normalize_company_name("Chevron Corporation") == "chevron"

    def test_remove_corp_suffix(self):
        assert normalize_company_name("Hess Corp.") == "hess"
        assert normalize_company_name("Hess Corp") == "hess"

    def test_remove_inc_suffix(self):
        assert normalize_company_name("Koch Industries Inc.") == "koch industries"
        assert normalize_company_name("Koch Industries Inc") == "koch industries"

    def test_remove_ltd_suffix(self):
        assert normalize_company_name("BHP Group Ltd.") == "bhp"
        assert normalize_company_name("BHP Group Limited") == "bhp"

    def test_remove_llc_suffix(self):
        assert normalize_company_name("Private Company LLC") == "private company"

    def test_remove_holdings_suffix(self):
        assert normalize_company_name("Investment Holdings") == "investment"

    def test_lowercase_conversion(self):
        assert normalize_company_name("UPPERCASE COMPANY") == "uppercase company"

    def test_whitespace_normalization(self):
        assert normalize_company_name("  Extra   Spaces  Corp  ") == "extra   spaces"

    def test_empty_input(self):
        assert normalize_company_name("") == ""
        assert normalize_company_name(None) == ""


class TestFuzzyMatch:
    """Test fuzzy matching logic."""

    def test_exact_match(self):
        result = fuzzy_match("Chevron", MOCK_COMPANIES)
        assert result is not None
        assert result["clean_name"] == "Chevron"

    def test_partial_match_with_suffix(self):
        result = fuzzy_match("Chevron Corporation", MOCK_COMPANIES)
        assert result is not None
        assert result["clean_name"] == "Chevron"

    def test_case_insensitive_match(self):
        result = fuzzy_match("chevron", MOCK_COMPANIES)
        assert result is not None
        assert result["clean_name"] == "Chevron"

    def test_abbreviation_match(self):
        result = fuzzy_match("BHP Group", MOCK_COMPANIES)
        assert result is not None
        assert result["clean_name"] == "BHP"

    def test_no_match_below_threshold(self):
        result = fuzzy_match("RandomCompanyNotInList", MOCK_COMPANIES, threshold=80)
        assert result is None

    def test_custom_threshold(self):
        # Lower threshold should match more liberally
        result = fuzzy_match("Chevr", MOCK_COMPANIES, threshold=50)
        assert result is not None
        assert result["clean_name"] == "Chevron"

    def test_empty_company_name(self):
        result = fuzzy_match("", MOCK_COMPANIES)
        assert result is None

        result = fuzzy_match(None, MOCK_COMPANIES)
        assert result is None

    def test_empty_company_list(self):
        result = fuzzy_match("Chevron", [])
        assert result is None

    def test_returns_account_name(self):
        result = fuzzy_match("Shell", MOCK_COMPANIES)
        assert result is not None
        assert result["account_name"] == "Shell | EU"
        assert result["clean_name"] == "Shell"


class TestLoadCompanyList:
    """Test company list loading from Excel."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_company_list("nonexistent.xlsx")
        assert "Company list not found" in str(exc_info.value)

    # Note: Actual file loading tests would require a real Excel file
    # or mocking openpyxl. For now, we document expected behavior:

    # def test_load_from_both_sheets(self):
    #     # Would verify both A&B and C&D sheets are loaded
    #     pass

    # def test_deduplication_on_clean_name(self):
    #     # Would verify that duplicate clean_names keep first occurrence
    #     pass

    # def test_missing_required_sheet(self):
    #     # Would raise ValueError if A&B or C&D sheet missing
    #     pass

    # def test_missing_required_columns(self):
    #     # Would raise ValueError if Account Name or Clean Name columns missing
    #     pass


# Integration test example (requires actual Excel file)
# Uncomment and use when PG_Acct_List.xlsx is available
"""
class TestIntegration:
    def test_load_actual_company_list(self):
        companies = load_company_list("data/PG_Acct_List.xlsx")
        assert len(companies) == 651  # Expected count after deduplication

        # Verify structure
        assert all("account_name" in c for c in companies)
        assert all("clean_name" in c for c in companies)

        # Test fuzzy matching against real list
        chevron = fuzzy_match("Chevron Corporation", companies)
        assert chevron is not None
        assert "chevron" in chevron["clean_name"].lower()
"""
