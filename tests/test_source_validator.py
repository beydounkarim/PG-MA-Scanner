"""
Unit tests for source_validator.py
"""

import pytest
from src.source_validator import (
    run_pre_validation_qa,
    apply_pre_validation_flags,
    check_url_reachable,
    check_content_relevance,
    _name_variations,
    _parse_deal_value,
    _normalize_url,
    _get_flag_reason,
)


class TestNormalizeUrl:
    """Test URL normalization for dedup."""

    def test_basic_url(self):
        url = "https://www.example.com/path/to/article"
        normalized = _normalize_url(url)
        assert normalized == "https://www.example.com/path/to/article"

    def test_trailing_slash_removed(self):
        url = "https://www.example.com/path/"
        normalized = _normalize_url(url)
        assert normalized == "https://www.example.com/path"

    def test_lowercase_domain(self):
        url = "https://WWW.EXAMPLE.COM/path"
        normalized = _normalize_url(url)
        assert normalized == "https://www.example.com/path"

    def test_query_params_preserved(self):
        url = "https://www.example.com/path?id=123"
        normalized = _normalize_url(url)
        assert "?id=123" in normalized


class TestNameVariations:
    """Test company name variation generation."""

    def test_basic_name(self):
        variations = _name_variations("Chevron")
        assert "chevron" in variations

    def test_with_corporation_suffix(self):
        variations = _name_variations("Chevron Corporation")
        assert "chevron corporation" in variations
        assert "chevron" in variations

    def test_with_corp_suffix(self):
        variations = _name_variations("Hess Corp.")
        assert "hess corp." in variations
        assert "hess" in variations

    def test_with_inc_suffix(self):
        variations = _name_variations("Company Inc.")
        assert "company inc." in variations
        assert "company" in variations

    def test_with_limited_suffix(self):
        variations = _name_variations("BHP Limited")
        assert "bhp" in variations

    def test_multiple_variations(self):
        variations = _name_variations("Hess Corporation")
        assert len(variations) >= 2  # At least base and stripped


class TestPreValidationQA:
    """Test Stage 0: Cross-deal QA."""

    def test_duplicate_urls_detected(self):
        """Same URL used for multiple deals should be flagged."""
        deals = [
            {"acquiror": "Company A", "target": "Target A", "source_link": "https://example.com/news"},
            {"acquiror": "Company B", "target": "Target B", "source_link": "https://example.com/news"},
        ]

        qa_results = run_pre_validation_qa(deals)

        assert len(qa_results["duplicate_urls"]) > 0
        assert len(qa_results["flagged_deals"]) == 2
        assert 0 in qa_results["flagged_deals"]
        assert 1 in qa_results["flagged_deals"]

    def test_generic_url_patterns_detected(self):
        """Generic index page URLs should be flagged."""
        deals = [
            {"acquiror": "Company A", "target": "Target A",
             "source_link": "https://example.com/press-releases"},
            {"acquiror": "Company B", "target": "Target B",
             "source_link": "https://example.com/newsroom"},
        ]

        qa_results = run_pre_validation_qa(deals)

        assert len(qa_results["generic_urls"]) > 0
        assert len(qa_results["flagged_deals"]) == 2

    def test_suspicious_slugs_detected(self):
        """Fabricated slugs with both company names should be flagged."""
        deals = [
            {"acquiror": "Chevron", "target": "Hess",
             "source_link": "https://reuters.com/business/energy/chevron-hess-acquisition"},
        ]

        qa_results = run_pre_validation_qa(deals)

        # Should detect both company names in slug
        assert len(qa_results["suspicious_slugs"]) > 0
        assert 0 in qa_results["flagged_deals"]

    def test_clean_batch_no_flags(self):
        """Batch with unique valid URLs should return 0 flags."""
        deals = [
            {"acquiror": "Company A", "target": "Target A",
             "source_link": "https://reuters.com/article/2024/01/15/company-a-deal-idUSKBN123456"},
            {"acquiror": "Company B", "target": "Target B",
             "source_link": "https://bloomberg.com/news/articles/2024-01-16/company-b-acquisition"},
        ]

        qa_results = run_pre_validation_qa(deals)

        assert len(qa_results["duplicate_urls"]) == 0
        assert len(qa_results["generic_urls"]) == 0
        assert len(qa_results["flagged_deals"]) == 0

    def test_summary_generated(self):
        """Should generate human-readable summary."""
        deals = [
            {"acquiror": "Company A", "target": "Target A", "source_link": "https://example.com/news"},
            {"acquiror": "Company B", "target": "Target B", "source_link": "https://example.com/news"},
        ]

        qa_results = run_pre_validation_qa(deals)

        assert "STAGE 0" in qa_results["summary"]
        assert "Total deals analyzed" in qa_results["summary"]


class TestApplyPreValidationFlags:
    """Test flagging application."""

    def test_flagged_deals_nulled(self):
        """Flagged deals should have source_link nulled."""
        deals = [
            {"acquiror": "Company A", "target": "Target A", "source_link": "https://example.com/news"},
            {"acquiror": "Company B", "target": "Target B", "source_link": "https://example.com/news"},
        ]

        qa_results = run_pre_validation_qa(deals)
        flagged_deals = apply_pre_validation_flags(deals, qa_results)

        # Both deals should have source_link nulled
        assert flagged_deals[0]["source_link"] is None
        assert flagged_deals[1]["source_link"] is None

        # Original URL preserved
        assert flagged_deals[0]["_stage0_original_url"] == "https://example.com/news"
        assert flagged_deals[1]["_stage0_original_url"] == "https://example.com/news"

        # Reason provided
        assert "_stage0_flag_reason" in flagged_deals[0]


class TestCheckUrlReachable:
    """Test Stage 1: HTTP check."""

    def test_valid_url_returns_reachable(self):
        """Known good URL should return reachable=True."""
        # Using a reliable test URL
        result = check_url_reachable("https://www.google.com")

        assert result["reachable"] is True
        assert result["status_code"] == 200
        assert result["content"] is not None

    def test_404_url_returns_unreachable(self):
        """404 URL should return reachable=False."""
        result = check_url_reachable("https://www.google.com/this-page-definitely-does-not-exist-12345")

        assert result["reachable"] is False
        assert result["status_code"] == 404

    def test_invalid_domain_returns_error(self):
        """Invalid domain should return error."""
        result = check_url_reachable("https://this-domain-definitely-does-not-exist-12345.com")

        assert result["reachable"] is False
        assert result["error"] is not None

    def test_timeout_handling(self):
        """Timeout should be handled gracefully."""
        # Use a very short timeout on a slow endpoint
        result = check_url_reachable("https://httpbin.org/delay/10", timeout=1)

        assert result["reachable"] is False
        assert result["error"] == "Timeout"


class TestCheckContentRelevance:
    """Test Stage 2: Content matching."""

    def test_high_confidence_match(self):
        """Page with both companies + keywords should be high confidence."""
        html = """
        <html>
        <body>
        <h1>Chevron Acquires Hess Corporation for $53 Billion</h1>
        <p>Chevron Corporation announced today that it will acquire Hess Corporation
        in a landmark merger transaction valued at $53 billion.</p>
        </body>
        </html>
        """

        result = check_content_relevance(html, "Chevron", "Hess")

        assert result["acquiror_found"] is True
        assert result["target_found"] is True
        assert len(result["deal_keywords_found"]) > 0
        assert result["confidence"] == "high"
        assert result["relevant"] is True

    def test_none_confidence_wrong_page(self):
        """Page about unrelated topic should be none confidence."""
        html = """
        <html>
        <body>
        <h1>Weather Forecast for Houston</h1>
        <p>Sunny skies expected this weekend.</p>
        </body>
        </html>
        """

        result = check_content_relevance(html, "Chevron", "Hess")

        assert result["acquiror_found"] is False
        assert result["target_found"] is False
        assert result["confidence"] == "none"
        assert result["relevant"] is False

    def test_generic_page_detection(self):
        """Generic index pages should be flagged."""
        html = """
        <html>
        <head><title>Press Releases - Company News</title></head>
        <body>
        <h1>Latest Press Releases</h1>
        <p>View all our press releases here.</p>
        </body>
        </html>
        """

        result = check_content_relevance(html, "Chevron", "Hess")

        assert result["is_generic_page"] is True
        assert result["relevant"] is False  # Even if it has keywords

    def test_medium_confidence_one_party(self):
        """Page with one party + keywords should be medium confidence."""
        html = """
        <html>
        <body>
        <h1>Chevron's Recent Acquisition</h1>
        <p>Chevron completed a major acquisition this year.</p>
        </body>
        </html>
        """

        result = check_content_relevance(html, "Chevron", "SomeOtherCompany")

        assert result["acquiror_found"] is True
        assert result["confidence"] in ("medium", "low")


# Integration tests requiring actual URLs
# Uncomment when ready for live testing

"""
class TestValidationIntegration:
    def test_validate_known_good_source(self):
        '''Test with a known good Reuters/Bloomberg URL.'''
        deal = {
            "acquiror": "Chevron",
            "target": "Hess",
            "source_link": "https://www.reuters.com/...",  # Real URL
            "description": "Chevron acquiring Hess for $53B"
        }

        # Would need Anthropic client for Stage 3
        # validated = validate_deal_source(deal, client)
        # assert validated["source_validation"] == "✓ Verified"
        pass

    def test_validate_fabricated_url(self):
        '''Test with a fabricated URL that should fail and re-source.'''
        deal = {
            "acquiror": "Chevron",
            "target": "Hess",
            "source_link": "https://www.chevron.com/news/chevron-hess-acquisition",  # Fabricated
            "description": "Chevron acquiring Hess for $53B"
        }

        # Should fail Stage 1, trigger Stage 3 re-sourcing
        # validated = validate_deal_source(deal, client)
        # assert validated["source_validation"] in ("🔄 Re-sourced", "⚠️ Unverified")
        pass
"""


# Documentation for manual testing
"""
MANUAL TESTING CHECKLIST:

Stage 0 (Cross-Deal QA):
[ ] Create batch with duplicate URLs - verify both deals flagged
[ ] Create batch with /press-releases URLs - verify generic pattern detected
[ ] Create batch with both-party-names-in-slug - verify suspicious slug detected
[ ] Create batch with clean URLs - verify 0 flags

Stage 1 (HTTP Check):
[ ] Test with known good URL (Reuters article) - should return 200
[ ] Test with 404 URL - should return 404
[ ] Test with invalid domain - should return error
[ ] Test with timeout (slow endpoint) - should handle gracefully

Stage 2 (Content Match):
[ ] Test with article mentioning both companies + deal keywords - high confidence
[ ] Test with article mentioning one company + keywords - medium confidence
[ ] Test with generic news page - should detect is_generic_page
[ ] Test with unrelated article - none confidence

Stage 3 (Auto Re-sourcing):
[ ] Test with fabricated URL - should trigger re-sourcing
[ ] Verify Claude returns URLs from search results
[ ] Verify re-sourced URL passes Stages 1-2
[ ] Test with deal that has no sources - should return not found

Full Pipeline:
[ ] Run on batch of 10 deals with mix of good/bad URLs
[ ] Verify verified/re-sourced/unverified split
[ ] Verify summary stats are accurate
[ ] Verify no fabricated URLs in verified deals
"""
