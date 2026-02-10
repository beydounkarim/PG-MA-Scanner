#!/usr/bin/env python3
"""
Simple test script to search for M&A activity for a single company.
Tests the full pipeline with minimal API calls.
"""

import os
import sys
from dotenv import load_dotenv
import anthropic

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from scanner import extract_json_from_response

def test_single_company(company_name: str, year: str = "2025"):
    """
    Search for M&A activity for a single company.

    Args:
        company_name: Company to search for (e.g., "Chevron", "ExxonMobil")
        year: Year to search (default: 2025)
    """
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Searching for M&A activity involving {company_name} in {year}...")
    print("=" * 60)

    system_prompt = """You are an M&A research analyst. Search for merger, acquisition,
divestiture, or spin-off activity involving the specified company.

Return results as a JSON array with this structure:
[
  {
    "acquiror": "Acquiring company name",
    "target": "Target company name",
    "deal_status": "Rumored/Announced/Closed",
    "description": "Brief description",
    "deal_value": "Deal value if known",
    "date": "Date (YYYY-MM-DD format)",
    "source": "Source publication",
    "source_link": "URL to article"
  }
]

CRITICAL: source_link must be a real URL from search results, never fabricated.
If no URL found, set source_link to null.
"""

    user_message = f"""Find any M&A deals (acquisitions, mergers, divestitures, spin-offs)
involving {company_name} in {year}.

Include deals where {company_name} is either:
- The acquiror (buying another company)
- The target (being acquired)
- Divesting assets or subsidiaries

Search period: {year}-01-01 to {year}-12-31

Return as JSON array. If no deals found, return empty array []."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5
            }],
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": user_message
            }]
        )

        deals = extract_json_from_response(response)

        if not deals:
            print(f"No deals found for {company_name} in {year}")
            return []

        print(f"\nFound {len(deals)} deal(s):\n")

        for i, deal in enumerate(deals, 1):
            print(f"Deal #{i}:")
            print(f"  Acquiror: {deal.get('acquiror', 'N/A')}")
            print(f"  Target: {deal.get('target', 'N/A')}")
            print(f"  Status: {deal.get('deal_status', 'N/A')}")
            print(f"  Value: {deal.get('deal_value', 'N/A')}")
            print(f"  Date: {deal.get('date', 'N/A')}")
            print(f"  Description: {deal.get('description', 'N/A')}")
            print(f"  Source: {deal.get('source', 'N/A')}")
            print(f"  Source Link: {deal.get('source_link', 'N/A')}")
            print()

        return deals

    except anthropic.RateLimitError as e:
        print(f"Rate limit error: {e}")
        print("\nYour API key has low rate limits. You need to add credits at:")
        print("https://console.anthropic.com/settings/billing")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


if __name__ == "__main__":
    # Test with a major company known to have M&A activity
    company = input("Enter company name to search (or press Enter for 'Chevron'): ").strip()
    if not company:
        company = "Chevron"

    year = input("Enter year to search (or press Enter for '2024'): ").strip()
    if not year:
        year = "2024"

    test_single_company(company, year)
