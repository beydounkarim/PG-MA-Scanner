"""
Source validation module - THE critical quality gate.

4-stage validation pipeline prevents fabricated URLs from polluting the dataset:
- Stage 0: Cross-deal QA (duplicate URLs, generic patterns, fabricated slugs)
- Stage 1: HTTP reachability check
- Stage 2: Content relevance matching
- Stage 3: Auto re-sourcing via Claude API

LLMs routinely fabricate plausible-looking URLs that 404. This module is mandatory.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import time
from typing import Tuple, Optional, Union


# Browser-like User-Agent (corporate sites block python-requests)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def run_pre_validation_qa(deals: list[dict]) -> dict:
    """
    Stage 0: Pre-validation cross-deal QA.

    Analyzes the full batch of deals for cross-deal quality issues that are
    only visible when analyzing multiple deals together.

    Three detection mechanisms:
    1. Duplicate URL Detection - same URL used for multiple deals
    2. Known Generic URL Patterns - /press-releases, /news, /newsroom
    3. Fabricated Slug Detection - URLs that look constructed, not real

    Args:
        deals: List of deal dicts with source_link field

    Returns:
        Dict with keys:
        - duplicate_urls: {url: [deal_indices...]}
        - generic_urls: {url: [deal_indices...]}
        - suspicious_slugs: {url: [deal_indices...]}
        - flagged_deals: set(deal_indices)
        - summary: str (human-readable summary)
    """
    url_to_deals = {}
    generic_urls = {}
    suspicious_slugs = {}
    flagged_indices = set()

    # Detection 1: Duplicate URLs
    for i, deal in enumerate(deals):
        url = deal.get("source_link")
        if not url:
            continue

        normalized = _normalize_url(url)
        if normalized not in url_to_deals:
            url_to_deals[normalized] = []
        url_to_deals[normalized].append(
            (i, deal.get("acquiror", "?"), deal.get("target", "?"))
        )

    duplicate_urls = {
        url: entries for url, entries in url_to_deals.items()
        if len(entries) >= 2
    }
    for url, entries in duplicate_urls.items():
        for idx_tuple in entries:
            flagged_indices.add(idx_tuple[0])

    # Detection 2: Known Generic URL Patterns
    GENERIC_PATH_PATTERNS = [
        "/press-releases", "/press-release", "/pressreleases",
        "/news", "/newsroom", "/news-room",
        "/media", "/media-center", "/mediacenter",
        "/media/press-releases", "/media/news",
        "/investors", "/investor-relations",
        "/about/news", "/about/media",
    ]

    for i, deal in enumerate(deals):
        url = deal.get("source_link")
        if not url:
            continue

        parsed = urlparse(url)
        path = parsed.path.rstrip("/").lower()

        if path in GENERIC_PATH_PATTERNS or path == "":
            if url not in generic_urls:
                generic_urls[url] = []
            generic_urls[url].append(
                (i, deal.get("acquiror", "?"), deal.get("target", "?"))
            )
            flagged_indices.add(i)

    # Detection 3: Fabricated Slug Detection
    for i, deal in enumerate(deals):
        url = deal.get("source_link")
        if not url:
            continue

        parsed = urlparse(url)
        path = parsed.path.lower()
        acquiror = deal.get("acquiror", "").lower()
        target = deal.get("target", "").lower()

        # Extract first words for matching
        acquiror_short = acquiror.split()[0] if acquiror else ""
        target_short = target.split()[0] if target else ""

        # Check 1: Both company names in slug
        has_both_names = (
            acquiror_short and target_short and
            len(acquiror_short) > 2 and len(target_short) > 2 and
            acquiror_short in path and target_short in path
        )

        # Check 2: Deal verbs in slug
        deal_verbs_in_slug = any(
            verb in path for verb in
            ["-acquires-", "-merger-with-", "-acquisition-of-",
             "-to-acquire-", "-buys-", "-purchase-of-"]
        )

        # Check 3: Long descriptive path
        is_long_descriptive = len(path) > 60 and deal_verbs_in_slug

        # Check 4: Suspicious corporate patterns
        is_corporate = any(
            parsed.netloc.startswith(prefix) for prefix in
            ["www.", "corporate.", "ir.", "investors."]
        )
        has_date_path = bool(re.search(r'/20\d{2}/', path))
        is_suspicious_corporate = (
            is_corporate and not has_date_path and
            len(path.split("/")) <= 3 and deal_verbs_in_slug
        )

        if has_both_names or is_long_descriptive or is_suspicious_corporate:
            if url not in suspicious_slugs:
                suspicious_slugs[url] = []
            suspicious_slugs[url].append(
                (i, deal.get("acquiror", "?"), deal.get("target", "?"))
            )
            flagged_indices.add(i)

    # Build summary
    summary_parts = []
    if duplicate_urls:
        summary_parts.append(
            f"  DUPLICATE URLS: {len(duplicate_urls)} URLs shared across "
            f"{sum(len(v) for v in duplicate_urls.values())} deals"
        )
        for url, entries in list(duplicate_urls.items())[:3]:  # Show first 3
            names = [f"{e[1]} / {e[2]}" for e in entries]
            summary_parts.append(f"    {url}")
            for name in names:
                summary_parts.append(f"      -> {name}")

    if generic_urls:
        summary_parts.append(
            f"  GENERIC URLS: {len(generic_urls)} generic index page URLs"
        )

    if suspicious_slugs:
        summary_parts.append(
            f"  SUSPICIOUS SLUGS: {len(suspicious_slugs)} likely fabricated URLs"
        )

    summary = (
        f"STAGE 0 PRE-VALIDATION QA\n"
        f"{'='*50}\n"
        f"  Total deals analyzed: {len(deals)}\n"
        f"  Deals flagged for forced re-sourcing: {len(flagged_indices)}\n"
    )
    if summary_parts:
        summary += "\n" + "\n".join(summary_parts)
    else:
        summary += "  No cross-deal issues detected."
    summary += f"\n{'='*50}"

    return {
        "duplicate_urls": duplicate_urls,
        "generic_urls": generic_urls,
        "suspicious_slugs": suspicious_slugs,
        "flagged_deals": flagged_indices,
        "summary": summary
    }


def _normalize_url(url: str) -> str:
    """Normalize URL for dedup comparison."""
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def apply_pre_validation_flags(deals: list[dict], qa_results: dict) -> list[dict]:
    """
    For flagged deals, null out the source_link to force re-sourcing in Stage 3.
    Preserves the original URL in _stage0_original_url.

    Args:
        deals: List of deal dicts
        qa_results: Results from run_pre_validation_qa()

    Returns:
        Modified deals list (in place)
    """
    for idx in qa_results["flagged_deals"]:
        deal = deals[idx]
        deal["_stage0_original_url"] = deal.get("source_link")
        deal["_stage0_flag_reason"] = _get_flag_reason(
            deal.get("source_link", ""), qa_results
        )
        deal["source_link"] = None  # Force re-sourcing
    return deals


def _get_flag_reason(url: str, qa_results: dict) -> str:
    """Get human-readable reason why a URL was flagged."""
    reasons = []
    normalized = _normalize_url(url) if url else ""

    if normalized in qa_results.get("duplicate_urls", {}):
        count = len(qa_results["duplicate_urls"][normalized])
        reasons.append(f"Duplicate URL (used for {count} deals)")

    if url in qa_results.get("generic_urls", {}):
        reasons.append("Generic index page URL pattern")

    if url in qa_results.get("suspicious_slugs", {}):
        reasons.append("Likely fabricated slug")

    return "; ".join(reasons) if reasons else "Unknown"


def check_url_reachable(url: str, timeout: int = 15) -> dict:
    """
    Stage 1: HTTP reachability check.

    Check if URL returns HTTP 200.

    Args:
        url: URL to check
        timeout: Request timeout in seconds (default: 15)

    Returns:
        Dict with keys:
        - reachable: bool
        - status_code: int | None
        - final_url: str (after redirects)
        - is_redirect: bool
        - content: str | None (HTML content if reachable)
        - error: str | None
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
            "final_url": resp.url,
            "is_redirect": resp.url != url,
            "content": resp.text if resp.status_code == 200 else None,
            "error": None
        }
    except requests.Timeout:
        return {
            "reachable": False,
            "status_code": None,
            "final_url": url,
            "is_redirect": False,
            "content": None,
            "error": "Timeout"
        }
    except requests.RequestException as e:
        return {
            "reachable": False,
            "status_code": None,
            "final_url": url,
            "is_redirect": False,
            "content": None,
            "error": str(e)
        }


def check_content_relevance(html_content: str, acquiror: str, target: str) -> dict:
    """
    Stage 2: Content relevance matching.

    Parse the page and verify it actually discusses the deal.

    Args:
        html_content: HTML content of the page
        acquiror: Acquiror company name
        target: Target company name

    Returns:
        Dict with keys:
        - relevant: bool (true if HIGH or MEDIUM confidence and not generic)
        - acquiror_found: bool
        - target_found: bool
        - deal_keywords_found: list[str]
        - is_generic_page: bool
        - page_title: str
        - confidence: "high" | "medium" | "low" | "none"

    Confidence scoring:
    - HIGH: Both parties + keywords
    - MEDIUM: One party + keywords
    - LOW: Only keywords found (generic M&A article)
    - NONE: Neither party found - wrong page
    """
    soup = BeautifulSoup(html_content, 'lxml')

    # Remove navigation, footer, header, aside, script, style
    for tag in soup(['nav', 'footer', 'header', 'aside', 'script',
                     'style', 'noscript']):
        tag.decompose()

    text = soup.get_text(separator=' ', strip=True).lower()
    title = soup.title.string.lower() if soup.title and soup.title.string else ""

    # Generate name variations
    acquiror_terms = _name_variations(acquiror)
    target_terms = _name_variations(target)

    # Deal keywords
    deal_keywords = [
        "acqui", "merger", "merg", "divest", "spin-off",
        "spinoff", "transaction", "purchase", "takeover",
        "deal close", "deal value", "all-stock", "cash and stock"
    ]

    # Check presence
    acquiror_found = any(term in text for term in acquiror_terms)
    target_found = any(term in text for term in target_terms)
    keywords_found = [kw for kw in deal_keywords if kw in text]

    # Generic page indicators
    generic_indicators = [
        "press releases", "newsroom", "media center",
        "latest news", "news archive", "all articles"
    ]
    is_generic = any(g in title for g in generic_indicators) and \
                 not (acquiror_found and target_found)

    # Confidence scoring
    if acquiror_found and target_found and keywords_found:
        confidence = "high"
    elif (acquiror_found or target_found) and keywords_found:
        confidence = "medium"
    elif keywords_found:
        confidence = "low"
    else:
        confidence = "none"

    relevant = confidence in ("high", "medium") and not is_generic

    return {
        "relevant": relevant,
        "acquiror_found": acquiror_found,
        "target_found": target_found,
        "deal_keywords_found": keywords_found,
        "is_generic_page": is_generic,
        "page_title": title[:200],
        "confidence": confidence
    }


def _name_variations(company_name: str) -> list[str]:
    """
    Generate search variations for a company name.

    Examples:
        "Hess Corporation" → ["hess corporation", "hess corp", "hess"]
    """
    name = company_name.lower().strip()
    variations = [name]

    # Strip suffixes
    suffixes = [
        " corporation", " corp.", " corp", " inc.", " inc",
        " ltd.", " ltd", " llc", " plc", " sa", " se",
        " group", " limited", " holdings"
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            variations.append(name[:-len(suffix)].strip())

    # Handle CamelCase splitting
    if " " not in name and len(name) > 5:
        split = re.sub(r'([a-z])([A-Z])', r'\1 \2', company_name).lower()
        if split != name:
            variations.append(split)

    return list(set(variations))


def find_replacement_source(
    acquiror: str,
    target: str,
    client,
    deal_description: str = ""
) -> dict:
    """
    Stage 3: Auto re-sourcing via Claude API.

    When the original URL fails validation, use Claude + web search
    to find a real, working source.

    Args:
        acquiror: Acquiror company name
        target: Target company name
        client: Anthropic client
        deal_description: Optional deal description for context

    Returns:
        Dict with keys:
        - found: bool
        - source: str | None (publication name)
        - source_link: str | None (URL)
        - confidence: str (high/medium/low/none)
    """
    system_prompt = """You are finding a credible news source for a specific M&A deal.
Search for the deal and return ONLY URLs that appeared in your search results.

CRITICAL: Return the EXACT URLs from your search results. Do NOT construct or guess URLs.

Return a JSON object with:
- "sources": array of {"url": "...", "title": "...", "publication": "..."}
- Include up to 3 candidate sources, ranked by credibility
  (press releases > Reuters/Bloomberg > trade publications > other)"""

    user_message = (
        f"Find a credible source URL for this deal: "
        f"{acquiror} acquiring/merging with {target}."
    )
    if deal_description:
        user_message += f"\nContext: {deal_description}"

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3
            }],
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        # Extract JSON from response
        from scanner import extract_json_from_response
        candidates = extract_json_from_response(response)

        if isinstance(candidates, dict):
            candidates = candidates.get("sources", [])

        # Validate each candidate URL
        for candidate in candidates[:3]:
            url = candidate.get("url")
            if not url:
                continue

            # Stage 1: HTTP check
            http_check = check_url_reachable(url)
            if not http_check["reachable"]:
                continue

            # Stage 2: Content match
            content_check = check_content_relevance(
                http_check["content"], acquiror, target
            )
            if content_check["relevant"]:
                return {
                    "found": True,
                    "source": candidate.get("publication", "Unknown"),
                    "source_link": http_check["final_url"],
                    "confidence": content_check["confidence"]
                }

    except Exception as e:
        print(f"  Auto re-sourcing error: {e}")

    return {
        "found": False,
        "source": None,
        "source_link": None,
        "confidence": "none"
    }


def validate_deal_source(deal: dict, client) -> dict:
    """
    Run the full 3-stage validation pipeline on a single deal.

    Stages 1-3 (Stage 0 is done at batch level before this).

    Args:
        deal: Deal dict with source_link
        client: Anthropic client (for Stage 3)

    Returns:
        Modified deal dict with validation_details and source_validation fields
    """
    url = deal.get("source_link")
    acquiror = deal.get("acquiror", "")
    target = deal.get("target", "")

    deal["validation_details"] = {}

    # Stage 1: HTTP check
    if url:
        http_result = check_url_reachable(url)
        deal["validation_details"]["http_check"] = {
            "status": http_result["status_code"],
            "reachable": http_result["reachable"]
        }

        if http_result["reachable"]:
            # Stage 2: Content match
            content_result = check_content_relevance(
                http_result["content"], acquiror, target
            )
            deal["validation_details"]["content_check"] = {
                "confidence": content_result["confidence"],
                "acquiror_found": content_result["acquiror_found"],
                "target_found": content_result["target_found"],
                "is_generic": content_result["is_generic_page"]
            }

            if content_result["relevant"]:
                deal["source_validation"] = "✓ Verified"
                return deal

    # Stage 3: Auto re-source
    print(f"  ⚠️  Source failed for {acquiror} → {target}. Searching for replacement...")

    resource_result = find_replacement_source(
        acquiror, target, client, deal.get("description", "")
    )
    deal["validation_details"]["resource"] = resource_result

    if resource_result["found"]:
        deal["original_source_link"] = deal.get("source_link")
        deal["source_link"] = resource_result["source_link"]
        deal["source"] = resource_result["source"]
        deal["source_validation"] = "🔄 Re-sourced"
        print(f"  ✓ Replacement found: {resource_result['source_link']}")
    else:
        deal["source_validation"] = "⚠️ Unverified"
        deal["validation_failure_reason"] = "No valid source found after re-sourcing"
        print(f"  ❌ No valid source found → routing to Unverified tab")

    return deal


def validate_all_deals(
    deals: list[dict],
    client,
    delay: float = 1.0
) -> Tuple[list, list]:
    """
    Validate all deals and split into verified vs unverified.

    Args:
        deals: List of deal dicts
        client: Anthropic client
        delay: Delay between validations in seconds (rate limiting)

    Returns:
        Tuple of (verified_deals, unverified_deals)
    """
    verified = []
    unverified = []

    for i, deal in enumerate(deals):
        print(f"Validating source [{i+1}/{len(deals)}]: "
              f"{deal.get('acquiror')} → {deal.get('target')}")

        validated = validate_deal_source(deal, client)

        if validated["source_validation"] in ("✓ Verified", "🔄 Re-sourced"):
            verified.append(validated)
        else:
            unverified.append(validated)

        time.sleep(delay)

    # Print summary
    v_count = sum(1 for d in verified if d["source_validation"] == "✓ Verified")
    r_count = sum(1 for d in verified if d["source_validation"] == "🔄 Re-sourced")
    u_count = len(unverified)

    print(f"\n{'='*50}")
    print(f"SOURCE VALIDATION SUMMARY")
    print(f"  ✓ Verified (original URL good):  {v_count}")
    print(f"  🔄 Re-sourced (replacement found): {r_count}")
    print(f"  ⚠️  Unverified (no valid source):   {u_count}")
    print(f"{'='*50}\n")

    return verified, unverified
