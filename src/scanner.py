"""
Scanner module - Core intelligence layer.

4-tier scanning approach with Claude API + web search:
- Tier 1: Industry sector scans (20-25 API calls)
- Tier 2: Company batch verification (30-35 API calls)
- Tier 3: Deep dive verification (5-20 API calls)
- Tier 4: Facility & opportunity research (5-15 API calls)

Model: claude-sonnet-4-20250514
Time period binding: MANDATORY for all queries
"""

import anthropic
import json
import re
import time
from typing import Tuple, Optional, Union

try:
    from reinforcement import get_prompt_injection
except ImportError:
    def get_prompt_injection(tier): return ""


# PE/financial buyer blocklist (hardcoded safety net)
PE_FIRMS = {
    "carlyle", "kkr", "apollo", "blackstone", "tpg", "bain capital",
    "eqt", "advent", "cvc", "warburg pincus", "gemspring", "cerberus",
    "brookfield", "silver lake", "thoma bravo", "vista equity",
    "hellman & friedman", "genstar", "platinum equity", "leonard green",
    "berkshire hathaway", "sovereign wealth fund",
}


def is_fatal_api_error(error: Exception) -> bool:
    """Check if an API error is fatal (billing, auth) vs transient (rate limit)."""
    msg = str(error).lower()
    return any(s in msg for s in [
        "credit balance is too low",
        "billing",
        "authentication",
        "invalid api key",
        "account has been disabled",
    ])


def build_tier1_queries(start_date: str, end_date: str) -> list[str]:
    """
    Build date-bounded Tier 1 queries.

    For periods < 3 months: use "after:YYYY-MM-DD before:YYYY-MM-DD"
    For full years: use the year number
    For multi-year: use "YYYY-YYYY" range

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of query strings with date bounds
    """
    from datetime import date

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    delta_days = (end - start).days

    # Determine date suffix format
    if delta_days <= 90:
        date_suffix = f"after:{start_date} before:{end_date}"
    elif start.year == end.year:
        date_suffix = str(start.year)
    else:
        date_suffix = f"{start.year}-{end.year}"

    # Industry sectors
    SECTORS = [
        "oil gas company acquisition",
        "oil gas company merger",
        "oil gas company divestiture",
        "mining company acquisition",
        "mining company merger",
        "chemical manufacturer acquisition",
        "chemical company merger divestiture",
        "utility company acquisition",
        "power utility merger",
        "manufacturing company acquisition",
        "industrial manufacturer merger",
        "cement company acquisition",
        "building materials merger",
        "steel company acquisition merger",
        "pipeline midstream acquisition",
        "water waste management acquisition",
        "paper pulp company merger",
        "industrial gases acquisition",
        "packaging company acquisition merger",
        "agribusiness acquisition merger",
        "major industrial acquisition announced",
        "largest industrial mergers",
        "industrial spin-off divestiture",
        # JV / investment / asset transfer queries
        "oil gas joint venture formed",
        "mining joint venture partnership",
        "chemical joint venture new entity",
        "industrial joint venture facilities",
        "energy company asset transfer",
        "oil gas asset swap deal",
        "infrastructure investment partnership",
        "industrial consortium formed",
        "midstream joint venture pipeline",
        "utility partnership investment",
    ]

    return [f"{sector} {date_suffix}" for sector in SECTORS]


def run_tier1_scans(start_date: str, end_date: str, max_uses: int = 5) -> list[dict]:
    """
    Tier 1: Industry sector scans.

    Cast a wide net across PG's verticals to find major deals.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_uses: Max web search uses per query (default 5, exhaustive 10)

    Returns:
        List of deal dicts
    """
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    system_prompt = f"""You are an M&A research analyst specializing in industrial sectors.
Search for mergers, acquisitions, divestitures, spin-offs, joint ventures, asset transfers,
significant investments/stakes, and consortium formations in the specified industry sector.

TIME PERIOD: Only include deals with activity between {start_date} and {end_date}.
"Activity" means: rumor first reported, deal announced, or deal closed within this window.
Do NOT include deals whose only activity was outside this date range.

For each deal you find, extract:
- acquiror: Company making the acquisition (for JVs: Party A alphabetically first)
- target: Company being acquired / divested (for JVs: Party B alphabetically second)
- deal_type: Acquisition, Merger, Divestiture, Spin-off, Joint Venture, Asset Transfer, or Investment/Stake
- deal_status: Rumored / Announced / Closed
- description: 1-2 sentence factual summary. For joint ventures: include the JV entity name and ownership split.
- deal_value: Approximate deal value if known (e.g., "$53B" or "Undisclosed")
- date: When was it rumored/announced/closed? (YYYY-MM-DD)
- source: Publication name
- source_link: Direct URL to article

IMPORTANT FILTERS - EXCLUDE these:
- Deals where the buyer is a PE firm, hedge fund, or financial investor
  (Carlyle, KKR, Apollo, Blackstone, Berkshire Hathaway, TPG, etc.)
- Technology/software companies (Google, Microsoft, Apple, Meta, Amazon, etc.)
- IPOs or public listings
- Internal restructurings where ownership doesn't truly change

Only include deals where at least one side is an OPERATING company in:
oil & gas, mining, utilities, manufacturing, chemicals, cement,
steel/metals, midstream/pipeline, paper, water/waste, packaging,
industrial gases, or agribusiness.

DO NOT include technology or software sector deals.

Return results as a JSON array. If no relevant deals found, return []."""

    rl_context = get_prompt_injection("tier1")
    if rl_context:
        system_prompt += f"\n\n{rl_context}"

    queries = build_tier1_queries(start_date, end_date)
    all_deals = []

    print(f"\nTIER 1: Industry Sector Scans ({len(queries)} queries)")
    print("=" * 60)

    for i, query in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {query}")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses
                }],
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Find all M&A and investment deals matching: {query}. Return as JSON array."
                }]
            )

            deals = extract_json_from_response(response)
            if deals:
                # Filter out PE deals (safety net)
                deals = [d for d in deals if not is_pe_buyer(d.get("acquiror", ""))]
                all_deals.extend(deals)
                print(f"    Found {len(deals)} deals")

            time.sleep(10)  # Rate limiting - increased for low rate limits

        except Exception as e:
            print(f"    Error: {e}")
            if is_fatal_api_error(e):
                print(f"\n    FATAL: {e}")
                print(f"    Stopping Tier 1 early. {len(all_deals)} deals collected so far.")
                break

    print(f"\nTier 1 complete: {len(all_deals)} total deals")
    return all_deals


def run_tier2_scans(companies: list[dict], start_date: str, end_date: str,
                    batch_size: int = 3, max_uses: int = 5,
                    label: str = "C&D") -> list[dict]:
    """
    Tier 2: Company batch verification.

    Check specific PG accounts for M&A activity.
    Split companies into batches.

    Args:
        companies: List of company dicts from matcher.load_company_list()
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        batch_size: Number of companies per batch (default 3, exhaustive 2)
        max_uses: Max web search uses per batch (default 5, exhaustive 10)
        label: Label for console output (default "C&D")

    Returns:
        List of deal dicts
    """
    client = anthropic.Anthropic()

    system_prompt = f"""You are an M&A research analyst. I will give you a list of companies.
For each company, search for mergers, acquisitions, divestitures, spin-offs,
joint ventures, asset transfers/swaps, significant investments or stakes,
and consortium formations they have been involved in between {start_date} and {end_date}.

CRITICAL: Include ALL deals where ANY of these dates fall within the range:
- Date rumored
- Date announced
- Date closed (MOST IMPORTANT - capture deals announced earlier but closed in this period)

Example: A deal announced in Oct 2023 but closed in May 2024 MUST be included.

Apply the same filters:
- EXCLUDE PE/financial buyers
- EXCLUDE technology/software companies (Google, Microsoft, Apple, Meta, Amazon, etc.)
- EXCLUDE IPOs, internal restructurings
- Only INCLUDE strategic/competitive activity in industrial sectors

For JVs: set role to 'Partner', list counterparty as the other partner, include JV entity name and ownership % in description.

For each deal found, return:
- company_from_list: Company from the list that matched
- role: Acquiror, Target, or Partner
- counterparty: The other company in the deal
- deal_type: Acquisition, Merger, Divestiture, Spin-off, Joint Venture, Asset Transfer, or Investment/Stake
- deal_status: Rumored / Announced / Closed
- description: 1-2 sentence summary
- deal_value: If known
- date: YYYY-MM-DD
- source: Publication name
- source_link: Direct URL

Return as JSON array. If no deals found for any company, return []."""

    rl_context = get_prompt_injection("tier2")
    if rl_context:
        system_prompt += f"\n\n{rl_context}"

    batches = [companies[i:i + batch_size] for i in range(0, len(companies), batch_size)]

    all_deals = []

    print(f"\nTIER 2 ({label}): Company Batch Verification ({len(batches)} batches, {max_uses} searches each)")
    print("=" * 60)

    for i, batch in enumerate(batches, 1):
        company_names = [c["clean_name"] for c in batch]
        numbered_list = "\n".join(f"{j+1}. {name}" for j, name in enumerate(company_names))

        print(f"  [{i}/{len(batches)}] Batch of {len(batch)} companies")

        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses
                }],
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Check these companies for M&A and investment activity between {start_date} and {end_date}:\n{numbered_list}"
                }]
            )

            deals = extract_json_from_response(response)
            if deals:
                # Normalize Tier 2 format to standard format
                normalized = []
                for deal in deals:
                    if deal.get("role") == "Acquiror":
                        normalized.append({
                            "acquiror": deal.get("company_from_list", ""),
                            "target": deal.get("counterparty", ""),
                            "deal_type": deal.get("deal_type", ""),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })
                    elif deal.get("role") == "Target":
                        normalized.append({
                            "acquiror": deal.get("counterparty", ""),
                            "target": deal.get("company_from_list", ""),
                            "deal_type": deal.get("deal_type", ""),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })
                    elif deal.get("role") == "Partner":
                        # JV/partnership: assign alphabetically for consistency
                        company = deal.get("company_from_list", "")
                        counterparty = deal.get("counterparty", "")
                        parties = sorted([company, counterparty], key=str.lower)
                        normalized.append({
                            "acquiror": parties[0],
                            "target": parties[1],
                            "deal_type": deal.get("deal_type", "Joint Venture"),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })

                # Filter out PE deals
                normalized = [d for d in normalized if not is_pe_buyer(d.get("acquiror", ""))]
                all_deals.extend(normalized)
                print(f"    Found {len(normalized)} deals")

            time.sleep(10)  # Rate limiting - increased for low rate limits

        except Exception as e:
            print(f"    Error: {e}")
            if is_fatal_api_error(e):
                print(f"\n    FATAL: {e}")
                print(f"    Stopping Tier 2 ({label}) early. {len(all_deals)} deals collected so far.")
                break

    print(f"\nTier 2 ({label}) complete: {len(all_deals)} total deals")
    return all_deals


def run_tier2_ab_scans(companies: list[dict], start_date: str, end_date: str,
                       max_uses: int = 20) -> list[dict]:
    """
    Tier 2 (A&B): Exhaustive individual company scans.

    Each A&B account gets its own dedicated API call with more web searches
    to catch smaller deals (JVs, asset swaps, minority stakes) that get
    crowded out in batched scans.

    Args:
        companies: List of A&B company dicts from matcher
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_uses: Max web search uses per company (default 20)

    Returns:
        List of deal dicts in standard format
    """
    client = anthropic.Anthropic()

    system_prompt = f"""You are an M&A research analyst conducting an EXHAUSTIVE search for a single company.
Find EVERY deal this company has been involved in between {start_date} and {end_date}.

Do NOT just report the biggest headline deals. You must also find:
- Joint ventures (JVs) — even small ones involving a handful of facilities
- Asset swaps and asset transfers
- Minority stakes and strategic investments
- Facility-level transactions (e.g., acquiring or divesting individual plants/refineries)
- Consortium formations and partnerships
- Spin-offs and carve-outs

CRITICAL: Include ALL deals where ANY of these dates fall within the range:
- Date rumored
- Date announced
- Date closed (MOST IMPORTANT - capture deals announced earlier but closed in this period)

Example: A deal announced in Oct 2023 but closed in May 2024 MUST be included.

Apply the same filters:
- EXCLUDE PE/financial buyers
- EXCLUDE technology/software companies (Google, Microsoft, Apple, Meta, Amazon, etc.)
- EXCLUDE IPOs, internal restructurings
- Only INCLUDE strategic/competitive activity in industrial sectors

For JVs: set role to 'Partner', list counterparty as the other partner, include JV entity name and ownership % in description.

For each deal found, return:
- company_from_list: Company from the list that matched
- role: Acquiror, Target, or Partner
- counterparty: The other company in the deal
- deal_type: Acquisition, Merger, Divestiture, Spin-off, Joint Venture, Asset Transfer, or Investment/Stake
- deal_status: Rumored / Announced / Closed
- description: 1-2 sentence summary
- deal_value: If known
- date: YYYY-MM-DD
- source: Publication name
- source_link: Direct URL

Return as JSON array. If no deals found, return []."""

    rl_context = get_prompt_injection("tier2_ab")
    if rl_context:
        system_prompt += f"\n\n{rl_context}"

    all_deals = []

    print(f"\nTIER 2 (A&B): Exhaustive Individual Scans ({len(companies)} companies, {max_uses} searches each)")
    print("=" * 60)

    for i, company in enumerate(companies, 1):
        name = company["clean_name"]
        print(f"  [{i}/{len(companies)}] {name}")

        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses
                }],
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search exhaustively for ALL M&A activity, joint ventures, asset deals, "
                        f"and investments involving {name} between {start_date} and {end_date}. "
                        f"Leave no stone unturned — include even small facility-level transactions."
                    )
                }]
            )

            deals = extract_json_from_response(response)
            if deals:
                # Normalize Tier 2 format to standard format (same logic as run_tier2_scans)
                normalized = []
                for deal in deals:
                    if deal.get("role") == "Acquiror":
                        normalized.append({
                            "acquiror": deal.get("company_from_list", ""),
                            "target": deal.get("counterparty", ""),
                            "deal_type": deal.get("deal_type", ""),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })
                    elif deal.get("role") == "Target":
                        normalized.append({
                            "acquiror": deal.get("counterparty", ""),
                            "target": deal.get("company_from_list", ""),
                            "deal_type": deal.get("deal_type", ""),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })
                    elif deal.get("role") == "Partner":
                        company_name = deal.get("company_from_list", "")
                        counterparty = deal.get("counterparty", "")
                        parties = sorted([company_name, counterparty], key=str.lower)
                        normalized.append({
                            "acquiror": parties[0],
                            "target": parties[1],
                            "deal_type": deal.get("deal_type", "Joint Venture"),
                            "deal_status": deal.get("deal_status", ""),
                            "description": deal.get("description", ""),
                            "deal_value": deal.get("deal_value", ""),
                            "date": deal.get("date", ""),
                            "source": deal.get("source", ""),
                            "source_link": deal.get("source_link", "")
                        })

                # Filter out PE deals
                normalized = [d for d in normalized if not is_pe_buyer(d.get("acquiror", ""))]
                all_deals.extend(normalized)
                print(f"    Found {len(normalized)} deals")

            time.sleep(10)  # Rate limiting

        except Exception as e:
            print(f"    Error: {e}")
            if is_fatal_api_error(e):
                print(f"\n    FATAL: {e}")
                print(f"    Stopping Tier 2 (A&B) early. {len(all_deals)} deals collected so far.")
                break

    print(f"\nTier 2 (A&B) complete: {len(all_deals)} total deals")
    return all_deals


def run_tier3_verification(candidate: dict) -> dict:
    """
    Tier 3: Deep dive verification.

    For a candidate deal from Tiers 1+2, do targeted search to extract
    all output fields and verify with credible source.

    Args:
        candidate: Candidate deal dict with acquiror, target

    Returns:
        Verified deal dict with all 15 fields, or {"verified": False}
    """
    client = anthropic.Anthropic()

    acquiror = candidate.get("acquiror", "")
    target = candidate.get("target", "")

    deal_type = candidate.get("deal_type", "")
    deal_context = f"Deal to verify: {acquiror} acquiring/merging with {target}"
    if deal_type == "Joint Venture":
        deal_context = f"Deal to verify: {acquiror} and {target} forming a joint venture"

    system_prompt = f"""You are verifying a specific M&A or investment transaction. Search for detailed,
authoritative information about this deal.

{deal_context}

Extract ALL of the following fields:
1. acquiror (full legal name; for JVs: partner alphabetically first)
2. target (full legal name; for JVs: partner alphabetically second)
3. deal_type (Acquisition, Merger, Divestiture, Spin-off, Joint Venture, Asset Transfer, or Investment/Stake)
4. deal_status (Rumored / Announced / Closed)
5. description (2-3 sentence factual summary)
6. date_rumor (YYYY-MM-DD or null)
7. date_announced (YYYY-MM-DD or null)
8. date_closed (YYYY-MM-DD or null)
9. deal_value (e.g., "$53B" or "Undisclosed")
10. source (publication name)
11. source_link - SEE CRITICAL RULES BELOW
12. sector (Oil & Gas, Mining, Utilities, Manufacturing, Chemicals, etc.)

For joint ventures, also extract:
- jv_entity_name: Name of the JV entity (e.g., "Adura") or null
- ownership_split: Ownership percentages (e.g., "50/50") or null
- facilities_contributed: Number/description of facilities being contributed or operated

=== CRITICAL RULES FOR SOURCE LINK ===
- The source_link MUST be a URL you found in your web search results.
- NEVER construct or guess a URL. NEVER build a URL from a domain name and an assumed path.
- If your search returned a relevant article, use THAT EXACT URL.
- If you cannot find a direct URL to an article about this specific deal,
  set source_link to null and set needs_manual_source to true.
- A generic company newsroom page (e.g., "/press-releases" or "/news") is NOT acceptable
  - it must link to the SPECIFIC article or announcement.

Common WRONG patterns (never do these):
  ✗ "https://www.reuters.com/business/energy/chevron-hess-deal"
  ✗ "https://www.company.com/news/company-acquires-target"
  ✗ "https://corporate.arcelormittal.com/media/press-releases"

Correct approach:
  ✓ Copy the exact URL from your search results
  ✓ If no direct URL found, return null + needs_manual_source: true
=== END CRITICAL RULES ===

If you cannot verify this deal with a credible source, return
{{"verified": false, "reason": "..."}}.

Apply all exclusion filters (PE buyers, technology/software companies, IPOs, restructurings).

Return as a single JSON object."""

    rl_context = get_prompt_injection("tier3")
    if rl_context:
        system_prompt += f"\n\n{rl_context}"

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
                "content": f"Verify this deal and extract all fields: {deal_context}"
            }]
        )

        deal = extract_json_from_response(response)

        if isinstance(deal, list) and len(deal) > 0:
            deal = deal[0]

        if not isinstance(deal, dict):
            return {"verified": False, "reason": "Invalid response format"}

        if deal.get("verified") is False:
            return deal

        # Filter out PE deals
        if is_pe_buyer(deal.get("acquiror", "")):
            return {
                "verified": False,
                "reason": "PE/financial buyer",
                "excluded": True,
                "exclusion_reason": "Financial buyer (PE firm)"
            }

        # Preserve matching info from candidate
        if "pg_account_name" in candidate:
            deal["pg_account_name"] = candidate["pg_account_name"]
        if "clean_name" in candidate:
            deal["clean_name"] = candidate["clean_name"]
        if "pg_match_side" in candidate:
            deal["pg_match_side"] = candidate["pg_match_side"]

        # Preserve deal_type from candidate as fallback if Tier 3 didn't return it
        if not deal.get("deal_type") and candidate.get("deal_type"):
            deal["deal_type"] = candidate["deal_type"]

        return deal

    except Exception as e:
        return {"verified": False, "reason": str(e)}


def format_facility_details(facility_data) -> str:
    """Convert facility data (list/dict/string) to readable text."""
    if isinstance(facility_data, str):
        return facility_data
    elif isinstance(facility_data, list):
        # List of facilities - format as bullet points
        if not facility_data:
            return "No specific facilities identified"
        formatted = []
        for item in facility_data:
            if isinstance(item, dict):
                # Extract name and location if available
                name = item.get('name', item.get('facility', ''))
                location = item.get('location', '')
                if name:
                    formatted.append(f"• {name}" + (f" ({location})" if location else ""))
            elif isinstance(item, str):
                formatted.append(f"• {item}")
        return "\n".join(formatted) if formatted else "No specific facilities identified"
    elif isinstance(facility_data, dict):
        # Dict of facilities - format as bullet points
        formatted = []
        for key, value in facility_data.items():
            formatted.append(f"• {key}: {value}")
        return "\n".join(formatted) if formatted else "No specific facilities identified"
    else:
        return str(facility_data)


def run_tier4_research(deal: dict) -> str:
    """
    Tier 4: Facility & opportunity research.

    For a verified deal, research the target company's physical facilities
    and classify the opportunity for PG.

    Args:
        deal: Verified deal dict

    Returns:
        Opportunity text for the "Potential Opportunity for PG" field
    """
    client = anthropic.Anthropic()

    acquiror = deal.get("acquiror", "")
    target = deal.get("target", "")
    sector = deal.get("sector", "")
    deal_type = deal.get("deal_type", "Acquisition")
    is_jv = deal_type == "Joint Venture"

    # Check which side is the PG customer
    pg_match_side = deal.get("pg_match_side", "")  # "acquiror" or "target"
    pg_account_name = deal.get("pg_account_name", "")

    acquiror_is_pg_customer = (pg_match_side == "acquiror")
    target_is_pg_customer = (pg_match_side == "target")

    pg_context = ""
    if acquiror_is_pg_customer:
        pg_context = f"\n\nIMPORTANT: {acquiror} is a Prometheus Group customer (account: {pg_account_name})."
    elif target_is_pg_customer:
        pg_context = f"\n\nIMPORTANT: {target} is a Prometheus Group customer (account: {pg_account_name}). {acquiror} is NOT a PG customer."
    else:
        pg_context = f"\n\nIMPORTANT: Neither {acquiror} nor {target} are confirmed Prometheus Group customers."

    # Build deal description based on deal type
    if is_jv:
        jv_entity = deal.get("jv_entity_name", "")
        jv_label = f" (JV entity: {jv_entity})" if jv_entity else ""
        deal_desc = f"{acquiror} and {target} forming a joint venture{jv_label}"
        research_target = f"the JV entity{jv_label} and both partners' contributed facilities"
    else:
        deal_desc = f"{acquiror} acquiring {target}"
        research_target = f"the TARGET company ({target})"

    jv_classification_rules = """
   For JOINT VENTURES specifically:
   - OFFENSIVE: If a PG customer is a partner AND the JV creates new facilities
     or brings together assets that would need maintenance software.
   - DEFENSIVE: If a PG customer's assets are being contributed to a JV with
     a non-PG partner who may bring different software/processes.
   - MONITOR: Default for JVs where the relationship impact is unclear.""" if is_jv else ""

    system_prompt = """You are a sales intelligence analyst for Prometheus Group, which sells
planning & scheduling software for maintenance of heavy industrial assets.

For the following deal, research {research_target}'s physical
operations and classify the opportunity:

Deal: {deal_desc}
Deal Type: {deal_type}
Sector: {sector}{pg_context}

Research and provide:
1. FACILITY DETAILS: List known facilities - plants,
   refineries, mines, processing facilities, manufacturing sites,
   power plants, pipelines, etc. Be specific with names and locations.

2. OPPORTUNITY CLASSIFICATION (CRITICAL - Follow these rules exactly):
   - OFFENSIVE (Upsell): Use ONLY when the acquiror IS a PG customer AND
     they are FULLY ACQUIRING the target business or sites (not just making
     an investment or taking a minority stake). This represents an opportunity
     to extend PG licenses to the newly acquired facilities.

   - DEFENSIVE (Risk): Use ONLY when the acquiror is NOT a PG customer but
     is acquiring a company or assets that may have PG relationships. This
     represents a risk of losing revenue under new ownership.

   - MONITOR: For investments, minority stakes, joint ventures, or deals
     where neither classification clearly applies.
{jv_classification_rules}
3. RECOMMENDED ACTION: 1-2 sentences for the sales team.

Return as JSON with fields: facility_details, classification, recommended_action."""

    formatted_prompt = system_prompt.format(
        acquiror=acquiror, target=target, sector=sector,
        pg_context=pg_context, deal_desc=deal_desc, deal_type=deal_type,
        research_target=research_target, jv_classification_rules=jv_classification_rules
    )

    rl_context = get_prompt_injection("tier4")
    if rl_context:
        formatted_prompt += f"\n\n{rl_context}"

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,  # Larger for facility details
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5
            }],
            system=formatted_prompt,
            messages=[{
                "role": "user",
                "content": f"Research facilities and classify opportunity for: {deal_desc}"
            }]
        )

        research = extract_json_from_response(response)

        if isinstance(research, dict):
            facility_data = research.get("facility_details", "")
            facility_details = format_facility_details(facility_data)
            classification = research.get("classification", "MONITOR")
            recommended_action = research.get("recommended_action", "")

            return f"{classification}: {recommended_action}\n\nFacilities: {facility_details}"
        else:
            return "MONITOR: Further research needed"

    except Exception as e:
        return f"MONITOR: Research error - {str(e)}"


def clean_citation_tags(text: str) -> str:
    """Remove citation tags like <cite index="1-2,7-8"> from text."""
    # Remove citation tags
    text = re.sub(r'<cite[^>]*>', '', text)
    text = re.sub(r'</cite>', '', text)
    return text


def extract_text_from_response(response) -> str:
    """Extract all text content from a Claude API response."""
    texts = []
    for block in response.content:
        if block.type == "text":
            texts.append(block.text)
    text = "\n".join(texts)
    return clean_citation_tags(text)


def clean_json_citations(data):
    """Recursively clean citation tags from JSON string values."""
    if isinstance(data, dict):
        return {k: clean_json_citations(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_json_citations(item) for item in data]
    elif isinstance(data, str):
        return clean_citation_tags(data)
    else:
        return data


def extract_json_from_response(response) -> Union[list, dict]:
    """
    Extract JSON from Claude's text response.

    Handles:
    - ```json blocks
    - Raw JSON
    - Embedded JSON in text
    """
    text = extract_text_from_response(response)

    # Try extracting from ```json block
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return clean_json_citations(data)
        except json.JSONDecodeError:
            pass

    # Try parsing entire text as JSON
    try:
        data = json.loads(text)
        return clean_json_citations(data)
    except json.JSONDecodeError:
        pass

    # Try finding JSON array or object in text
    for pattern in [r'\[.*\]', r'\{.*\}']:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return clean_json_citations(data)
            except json.JSONDecodeError:
                continue

    return []  # Fallback: no JSON found


def call_claude_with_retry(client, max_retries=3, **kwargs):
    """
    Call Claude API with retry logic.

    Handles:
    - RateLimitError: exponential backoff (10s, 20s, 40s)
    - APIError: retry 3 times

    Args:
        client: Anthropic client
        max_retries: Maximum retry attempts
        **kwargs: Arguments for client.messages.create()

    Returns:
        API response

    Raises:
        Exception: If all retries exhausted
    """
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            wait = 2 ** attempt * 10  # 10s, 20s, 40s
            print(f"    Rate limited. Waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt == max_retries - 1:
                raise
            print(f"    API error: {e}. Retrying...")
            time.sleep(5)

    raise Exception("Max retries exhausted")


def is_pe_buyer(acquiror: str) -> bool:
    """
    Check if acquiror is a PE/financial buyer (safety net).

    Args:
        acquiror: Acquiror company name

    Returns:
        True if PE firm, False otherwise
    """
    if not acquiror:
        return False

    acquiror_lower = acquiror.lower()
    return any(pe in acquiror_lower for pe in PE_FIRMS)
