"""
Deal deduplication module.

Prevents duplicate alerts by tracking deal history in Google Sheets.
Max 3 alerts per deal: rumor → announced → closed.
"""

import re
from typing import Optional


def generate_deal_id(acquiror: str, target: str) -> str:
    """
    Normalize acquiror + target into a stable key.

    Normalizes to lowercase, strips common suffixes (Corp, Inc, Ltd, LLC),
    replaces spaces with underscores, sorts alphabetically for mergers.

    Args:
        acquiror: Acquiror company name
        target: Target company name

    Returns:
        Normalized deal ID (e.g., "chevron_hess")

    Examples:
        >>> generate_deal_id("Chevron Corporation", "Hess Corp")
        "chevron_hess"

        >>> generate_deal_id("Company B", "Company A")  # Merger
        "company_a_company_b"  # Sorted alphabetically
    """
    def normalize(name: str) -> str:
        if not name:
            return ""

        name = str(name).strip().lower()

        # Remove "the" prefix
        if name.startswith("the "):
            name = name[4:]

        # Remove possessive forms ('s or 's)
        name = re.sub(r"'s?\s", " ", name)

        # Remove parenthetical content (preserves core company name)
        name = re.sub(r'\([^)]*\)', '', name).strip()

        # Remove descriptive phrases that come after company names
        # e.g., "stakes in...", "assets of...", "coal division", etc.
        descriptive_patterns = [
            r'\s+stakes?\s+in\s+.*$',
            r'\s+assets?\s+(of|at|in)\s+.*$',
            r'\s+\w+\s+division\s*$',  # "coal division", "mining division", etc.
            r'\s+division\s+(of|in)\s+.*$',
            r'\s+business\s+unit\s+.*$',
            r'\s+operations?\s+in\s+.*$',
            r'\s+facilities?\s+in\s+.*$',
            r'\s+\w+\s+business\s*$',  # "coal business", "mining business", etc.
            r'\s+specific\s+.*$',
            r'\s+from\s+.*$'
        ]
        for pattern in descriptive_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        name = name.strip()

        # Strip subsidiary/division/product line names and geographic regions
        # e.g., "INEOS Olefins & Polymers Europe" → "INEOS"
        # This must come BEFORE suffix removal
        subsidiary_patterns = [
            # Geographic regions
            r'\s+(europe|americas|asia|africa|oceania|international)$',
            r'\s+(north|south|east|west)\s+(america|europe|asia|africa)$',
            r'\s+(asia\s+pacific|apac|emea|latam)$',
            # Product lines / divisions (after "&" symbol)
            r'\s+&\s+.*$',  # "Company & Product Line" → "Company"
            # Common division descriptors
            r'\s+(chemicals?|materials?|energy|power|mining)$',
            r'\s+(oil|gas|petroleum|refining)$',
            r'\s+(olefins?|polymers?|plastics?|petrochemicals?)$',
            r'\s+(upstream|downstream|midstream)$',
        ]
        for pattern in subsidiary_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        name = name.strip()

        # Remove common suffixes (loop until no more suffixes match)
        suffixes = [
            " corporation", " corp.", " corp",
            " incorporated", " inc.", " inc",
            " limited", " ltd.", " ltd",
            " llc", " l.l.c.",
            " plc", " p.l.c.",
            " sa", " s.a.",
            " se", " s.e.",
            " holdings",
            " group",
            " company"
        ]

        # Keep stripping suffixes until none match
        suffix_found = True
        while suffix_found:
            suffix_found = False
            for suffix in suffixes:
                if name.endswith(suffix):
                    name = name[:-len(suffix)].strip()
                    suffix_found = True
                    break  # Restart from beginning of suffix list

        # Replace spaces and special chars with underscores
        name = re.sub(r'[^\w]+', '_', name)

        # Remove trailing underscores
        name = name.strip('_')

        return name

    acq_norm = normalize(acquiror)
    tgt_norm = normalize(target)

    # For mergers of equals, sort alphabetically for consistency
    # This ensures "A + B" and "B + A" map to same deal_id
    if acq_norm and tgt_norm:
        parts = sorted([acq_norm, tgt_norm])
        return "_".join(parts)
    elif acq_norm:
        return acq_norm
    elif tgt_norm:
        return tgt_norm
    else:
        return "unknown_deal"


def is_new_alert(deal: dict, state: dict) -> bool:
    """
    Returns True if this deal+stage combo hasn't been reported yet.

    A deal can generate up to 3 alerts: rumor, announced, closed.

    Args:
        deal: Deal dict with keys: deal_id, deal_status (or just acquiror+target)
        state: Dedup state dict built from Google Sheets via build_dedup_state()

    Returns:
        True if this is a new alert, False if already reported

    Examples:
        >>> state = {
        ...     "chevron_hess": {
        ...         "stages_reported": ["rumored", "announced"],
        ...         ...
        ...     }
        ... }
        >>> is_new_alert({"deal_id": "chevron_hess", "deal_status": "Closed"}, state)
        True  # "closed" not in stages_reported
        >>> is_new_alert({"deal_id": "chevron_hess", "deal_status": "Announced"}, state)
        False  # "announced" already reported
    """
    deal_id = deal.get("deal_id")

    # Generate deal_id if not present
    if not deal_id:
        deal_id = generate_deal_id(
            deal.get("acquiror", ""),
            deal.get("target", "")
        )

    # Normalize deal status to lowercase
    deal_status = deal.get("deal_status", "").lower()
    if not deal_status:
        # Try alternative field names
        deal_status = deal.get("Deal Status", "").lower()

    # If deal_id not in state, this is a new deal
    if deal_id not in state:
        return True

    # Check if this stage has been reported
    stages_reported = state[deal_id].get("stages_reported", [])

    # Normalize stages to lowercase for comparison
    stages_reported = [s.lower() for s in stages_reported]

    # Max 3 alerts: rumor, announced, closed
    if len(stages_reported) >= 3:
        return False

    # New alert if current status not in stages_reported
    return deal_status not in stages_reported


def categorize_candidate(candidate: dict, state: dict) -> tuple[str, Optional[dict]]:
    """
    Categorize a candidate deal against existing state.

    Returns:
        Tuple of (category, existing_deal):
        - ("exact_match", existing_deal): Same deal, same status - skip Tier 3-4
        - ("status_update", existing_deal): Same deal, status changed - update status only
        - ("new_deal", None): Completely new deal - run full Tier 3-4

    Args:
        candidate: Candidate deal dict from Tier 2
        state: Dedup state dict from Google Sheets

    Examples:
        >>> state = {"chevron_hess": {"deal_status": "announced", ...}}
        >>> categorize_candidate({"acquiror": "Chevron", "target": "Hess", "deal_status": "Announced"}, state)
        ("exact_match", {...})
        >>> categorize_candidate({"acquiror": "Chevron", "target": "Hess", "deal_status": "Closed"}, state)
        ("status_update", {...})
        >>> categorize_candidate({"acquiror": "Shell", "target": "NewCo", "deal_status": "Rumored"}, state)
        ("new_deal", None)
    """
    # Generate deal_id for candidate
    deal_id = generate_deal_id(
        candidate.get("acquiror", ""),
        candidate.get("target", "")
    )

    # Normalize candidate status
    candidate_status = candidate.get("deal_status", "").lower()

    # Check if deal exists in state
    if deal_id not in state:
        return ("new_deal", None)

    existing = state[deal_id]
    existing_status = existing.get("current_status", "").lower()

    # Check if status is the same
    if candidate_status == existing_status:
        return ("exact_match", existing)
    else:
        # Status changed (e.g., Announced → Closed)
        return ("status_update", existing)


def update_state_in_memory(deal: dict, state: dict) -> dict:
    """
    Add this deal/stage to the in-memory state dict.

    The actual persistence happens when we write to Google Sheets.
    This is just for tracking within a single scan run.

    Args:
        deal: Deal dict
        state: Dedup state dict (modified in place)

    Returns:
        Updated state dict
    """
    deal_id = deal.get("deal_id")

    if not deal_id:
        deal_id = generate_deal_id(
            deal.get("acquiror", ""),
            deal.get("target", "")
        )

    deal_status = deal.get("deal_status", "").lower()
    if not deal_status:
        deal_status = deal.get("Deal Status", "").lower()

    if deal_id not in state:
        state[deal_id] = {
            "acquiror": deal.get("acquiror", ""),
            "target": deal.get("target", ""),
            "deal_id": deal_id,
            "stages_reported": [],
            "first_seen": deal.get("first_seen", ""),
            "last_updated": deal.get("last_updated", ""),
            "current_status": deal_status
        }

    # Add current status to stages_reported if not already there
    if deal_status and deal_status not in state[deal_id]["stages_reported"]:
        state[deal_id]["stages_reported"].append(deal_status)

    # Update last_updated
    if deal.get("last_updated"):
        state[deal_id]["last_updated"] = deal["last_updated"]

    return state
