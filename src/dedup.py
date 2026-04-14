"""
Deal deduplication module.

Prevents duplicate alerts by tracking deal history in Google Sheets.
Max 3 alerts per deal: rumor → announced → closed.

Also provides fuzzy_dedupe_deals() for bulk dedup of existing deal lists,
catching both exact-ID matches and fuzzy duplicates (different target names,
parent vs subsidiary, asset vs company framing).
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher
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


# ---------------------------------------------------------------------------
# Fuzzy deduplication helpers
# ---------------------------------------------------------------------------

# Field mapping: (pipeline_key, sheets_key)
_FIELD_MAP = {
    "acquiror":           ("acquiror",           "Acquiror"),
    "target":             ("target",             "Target"),
    "deal_status":        ("deal_status",        "Deal Status"),
    "description":        ("description",        "Description"),
    "deal_value":         ("deal_value",         "Deal Value ($)"),
    "date_rumor":         ("date_rumor",          "Date of Rumor"),
    "date_announced":     ("date_announced",      "Date of Announcement"),
    "date_closed":        ("date_closed",          "Date Closed"),
    "source":             ("source",              "Source"),
    "source_link":        ("source_link",          "Source Link"),
    "pg_account_name":    ("pg_account_name",      "PG Account Name"),
    "clean_name":         ("clean_name",           "Clean Name"),
    "opportunity":        ("opportunity",          "Potential Opportunity for PG"),
    "source_validation":  ("source_validation",    "Source Validation"),
    "sector":             ("sector",              "Sector"),
    "deal_type":          ("deal_type",            "Deal Type"),
}

# Words to ignore when tokenizing names — includes common industry terms
# that appear in many unrelated company names and would cause false matches
_STOP_WORDS = frozenset({
    # Common English
    "the", "of", "in", "and", "for", "a", "an", "to", "its", "by",
    "from", "with", "on", "at", "as", "or", "s", "is", "are", "was",
    "not", "new", "all", "pro", "via", "per", "has", "been", "will",
    # Deal terminology
    "stake", "stakes", "share", "shares", "interest", "interests",
    "acquisition", "merger", "deal", "transaction", "purchase", "sale",
    "assets", "asset", "business", "operations", "operation", "division",
    "unit", "percent", "remaining", "equity", "joint", "venture",
    "owned", "subsidiary", "minority", "majority", "controlling",
    # Corporate suffixes
    "inc", "corp", "corporation", "ltd", "limited", "llc", "plc",
    "sa", "se", "holdings", "group", "company", "co", "pty", "ag",
    "gmbh", "bv", "nv",
    # Industry-common company name words (cause false matches)
    "energy", "power", "resources", "capital", "global", "international",
    "partners", "petroleum", "oil", "gas", "mining", "metals", "metal",
    "natural", "gold", "mine", "mines", "copper", "coal", "steel",
    "solutions", "services", "technologies", "technology", "systems",
    "products", "materials", "chemicals", "industrial", "industries",
    "enterprises", "infrastructure", "management", "investment",
    "development", "financial", "fund", "ventures",
    "semiconductor", "electronics", "silicon", "silicone",
    "north", "south", "east", "west", "american", "pacific", "americas",
    "canada", "canadian", "australia", "australian", "brasil", "brazil",
    "europe", "european", "africa", "african", "asian",
    "norge", "norway", "colombia", "colombia",
    "clean", "renewable", "renewables", "green",
    "exploration", "production", "refining",
    "midstream", "upstream", "downstream", "pipeline",
    "generation", "electric", "electricity", "nuclear", "solar", "wind",
    "thermal", "hydro", "geothermal",
})

# Status ranking for merge (higher = more advanced)
_STATUS_RANK = {"rumored": 0, "rumor": 0, "announced": 1, "closed": 2, "completed": 2}


def _get_field(deal: dict, field_name: str) -> str:
    """Get a field value from a deal dict, trying both pipeline and Sheets keys."""
    pipeline_key, sheets_key = _FIELD_MAP.get(field_name, (field_name, field_name))
    val = deal.get(pipeline_key, "") or deal.get(sheets_key, "")
    return str(val).strip() if val else ""


def _normalize_name(name: str) -> str:
    """Normalize a company name for fuzzy comparison (lowercase, strip suffixes)."""
    if not name:
        return ""
    name = str(name).strip().lower()
    # Remove parenthetical content
    name = re.sub(r'\([^)]*\)', '', name).strip()
    # Remove possessives
    name = re.sub(r"['']s?\b", "", name)
    # Strip common suffixes
    for suffix in (" corporation", " corp.", " corp", " incorporated",
                   " inc.", " inc", " limited", " ltd.", " ltd",
                   " llc", " plc", " sa", " s.a.", " se", " s.e.",
                   " holdings", " group", " company", " co."):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _name_tokens(name: str) -> set[str]:
    """Extract significant tokens (≥3 chars, not stop words) from a name.

    Unlike _normalize_name, this preserves parenthetical content so we can
    match 'Teck Resources (Elk Valley)' against 'Elk Valley Resources'.
    """
    if not name:
        return set()
    name = str(name).strip().lower()
    # Remove possessives but keep parenthetical content
    name = re.sub(r"['']s?\b", "", name)
    return {t for t in re.split(r'[^a-z0-9]+', name)
            if len(t) >= 3 and t not in _STOP_WORDS}


def _desc_tokens(desc: str) -> set[str]:
    """Extract significant tokens from a description."""
    if not desc:
        return set()
    desc = str(desc).lower()
    return {t for t in re.split(r'[^a-z0-9]+', desc)
            if len(t) >= 3 and t not in _STOP_WORDS}


# Words stripped from names before SequenceMatcher comparison to prevent
# industry-common words ("energy", "midstream", "resources") from inflating
# similarity between unrelated companies.
_COMPARISON_STRIP_RE = re.compile(
    r'\b(?:energy|energi|energía|resources|resource|mining|metals|metal|'
    r'power|capital|midstream|upstream|downstream|pipeline|petroleum|'
    r'oil|gas|solar|wind|nuclear|chemicals?|materials?|'
    r'partners|ventures|investments?|management|services|solutions|'
    r'industries|industrial|infrastructure|technologies|technology|'
    r'global|international|american|americas|pacific|'
    r'north|south|east|west|norge|norway|canada|australia|'
    r'asa|as|ag|gmbh|bv|nv|pty)\b',
    re.IGNORECASE
)


def _clean_for_comparison(name: str) -> str:
    """Normalize + strip industry words for SequenceMatcher comparison."""
    name = _normalize_name(name)
    name = _COMPARISON_STRIP_RE.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _seq_ratio(a: str, b: str) -> float:
    """SequenceMatcher ratio on two cleaned names."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _token_overlap(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Jaccard-like token overlap ratio."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _is_duplicate_pair(deal_a: dict, deal_b: dict) -> bool:
    """
    Check whether two deals are duplicates using multi-signal matching.

    Rules (any one triggers a match):
    1. Both sides similar: acquiror sim ≥ 0.7 AND target sim ≥ 0.7
    2. Cross-match: A's acquiror ≈ B's target AND vice versa
    3. Same acquiror + ≥2 shared distinctive target tokens
    4. Same acquiror + ≥2 distinctive target tokens in other's description
    """
    acq_a = _clean_for_comparison(_get_field(deal_a, "acquiror"))
    acq_b = _clean_for_comparison(_get_field(deal_b, "acquiror"))
    tgt_a = _clean_for_comparison(_get_field(deal_a, "target"))
    tgt_b = _clean_for_comparison(_get_field(deal_b, "target"))

    acq_sim = _seq_ratio(acq_a, acq_b)
    tgt_sim = _seq_ratio(tgt_a, tgt_b)

    # Rule 1: Both sides similar
    if acq_sim >= 0.7 and tgt_sim >= 0.7:
        return True

    # Rule 2: Cross-match (swapped parties)
    cross_1 = _seq_ratio(acq_a, tgt_b)
    cross_2 = _seq_ratio(tgt_a, acq_b)
    if cross_1 >= 0.75 and cross_2 >= 0.75:
        return True

    # For rules 3-4, acquiror must be a strong match (on cleaned names)
    high_acq = acq_sim >= 0.80

    if not high_acq:
        return False

    tgt_tokens_a = _name_tokens(_get_field(deal_a, "target"))
    tgt_tokens_b = _name_tokens(_get_field(deal_b, "target"))

    # Rule 3: Same acquiror + ≥2 shared distinctive target tokens
    shared_tgt = tgt_tokens_a & tgt_tokens_b
    if len(shared_tgt) >= 2:
        return True

    # Rule 4: Same acquiror + ≥2 distinctive target tokens in other's description
    desc_tok_a = _desc_tokens(_get_field(deal_a, "description"))
    desc_tok_b = _desc_tokens(_get_field(deal_b, "description"))

    if len(tgt_tokens_a & desc_tok_b) >= 2:
        return True
    if len(tgt_tokens_b & desc_tok_a) >= 2:
        return True

    return False


def _merge_deal_group(deals: list[dict]) -> dict:
    """
    Merge a group of duplicate deals into one, keeping the best information.

    Strategy:
    - Acquiror/Target: most frequent, tie-break on shortest (cleaner names)
    - Deal Status: most advanced (Closed > Announced > Rumored)
    - Description/Opportunity: longest non-empty
    - Deal Value: prefer specific over "Undisclosed"
    - Dates: prefer non-empty
    - Source: prefer verified source
    - PG Account: keep any non-empty
    - Source Validation: prefer "✓ Verified"
    """
    if len(deals) == 1:
        return deals[0]

    merged = dict(deals[0])  # Start with first deal as base

    def _best_name(field_name: str) -> str:
        """Pick the most frequent name, tie-break on shortest."""
        counts = defaultdict(int)
        for d in deals:
            val = _get_field(d, field_name)
            if val:
                counts[val] += 1
        if not counts:
            return ""
        max_count = max(counts.values())
        candidates = [v for v, c in counts.items() if c == max_count]
        return min(candidates, key=len)

    def _longest(field_name: str) -> str:
        """Pick the longest non-empty value."""
        best = ""
        for d in deals:
            val = _get_field(d, field_name)
            if val and len(val) > len(best):
                best = val
        return best

    def _any_nonempty(field_name: str) -> str:
        """Pick the first non-empty value."""
        for d in deals:
            val = _get_field(d, field_name)
            if val:
                return val
        return ""

    def _best_status() -> str:
        """Pick the most advanced deal status."""
        best_rank = -1
        best_status = ""
        for d in deals:
            status = _get_field(d, "deal_status")
            rank = _STATUS_RANK.get(status.lower(), -1)
            if rank > best_rank:
                best_rank = rank
                best_status = status
        return best_status or _any_nonempty("deal_status")

    def _best_value() -> str:
        """Prefer specific deal value over 'Undisclosed'."""
        specific = ""
        any_val = ""
        for d in deals:
            val = _get_field(d, "deal_value")
            if not val:
                continue
            if not any_val:
                any_val = val
            if val.lower() not in ("undisclosed", "n/a", "not disclosed", ""):
                if not specific or len(val) > len(specific):
                    specific = val
        return specific or any_val

    def _best_validation() -> str:
        """Prefer '✓ Verified' over other values."""
        for d in deals:
            val = _get_field(d, "source_validation")
            if "verified" in val.lower() or "✓" in val:
                return val
        return _any_nonempty("source_validation")

    # Determine which key format the deals use (Sheets or pipeline)
    is_sheets = "Acquiror" in deals[0]

    def _set(field_name: str, value: str):
        """Set a field in the merged dict using the correct key format."""
        pipeline_key, sheets_key = _FIELD_MAP[field_name]
        key = sheets_key if is_sheets else pipeline_key
        merged[key] = value

    _set("acquiror", _best_name("acquiror"))
    _set("target", _best_name("target"))
    _set("deal_status", _best_status())
    _set("description", _longest("description"))
    _set("opportunity", _longest("opportunity"))
    _set("deal_value", _best_value())
    _set("source_validation", _best_validation())
    _set("sector", _any_nonempty("sector"))
    _set("source", _any_nonempty("source"))
    _set("source_link", _any_nonempty("source_link"))
    _set("pg_account_name", _any_nonempty("pg_account_name"))
    _set("clean_name", _any_nonempty("clean_name"))
    _set("deal_type", _any_nonempty("deal_type"))

    # Dates: prefer non-empty for each date field
    for date_field in ("date_rumor", "date_announced", "date_closed"):
        _set(date_field, _any_nonempty(date_field))

    return merged


# ---------------------------------------------------------------------------
# Union-Find for transitive grouping
# ---------------------------------------------------------------------------

class _UnionFind:
    """Simple Union-Find (disjoint set) data structure."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ---------------------------------------------------------------------------
# Main fuzzy dedup function
# ---------------------------------------------------------------------------

def fuzzy_dedupe_deals(deals: list[dict], verbose: bool = False) -> list[dict]:
    """
    Deduplicate a list of deals using exact-ID + fuzzy matching, then merge
    the best information from each duplicate group.

    Args:
        deals: List of deal dicts (Sheets or pipeline format)
        verbose: Print detailed merge report

    Returns:
        Deduplicated list of deal dicts
    """
    if len(deals) <= 1:
        return deals

    n = len(deals)
    uf = _UnionFind(n)

    # ---------------------------------------------------------------
    # Pass 1: Exact deal_id match
    # ---------------------------------------------------------------
    id_to_indices = defaultdict(list)
    for i, deal in enumerate(deals):
        acq = _get_field(deal, "acquiror")
        tgt = _get_field(deal, "target")
        did = generate_deal_id(acq, tgt)
        id_to_indices[did].append(i)

    exact_merges = 0
    for did, indices in id_to_indices.items():
        if len(indices) > 1:
            exact_merges += len(indices) - 1
            for idx in indices[1:]:
                uf.union(indices[0], idx)

    if verbose:
        print(f"  Pass 1 (exact ID): {exact_merges} duplicates in "
              f"{sum(1 for v in id_to_indices.values() if len(v) > 1)} groups")

    # ---------------------------------------------------------------
    # Pass 2: Token-blocking + fuzzy match
    # ---------------------------------------------------------------
    # Build token → deal index map for blocking
    token_to_indices = defaultdict(set)
    for i, deal in enumerate(deals):
        tokens = (_name_tokens(_get_field(deal, "acquiror")) |
                  _name_tokens(_get_field(deal, "target")))
        for tok in tokens:
            token_to_indices[tok].add(i)

    # Only compare pairs sharing at least one significant token
    checked_pairs = set()
    fuzzy_merges = 0

    for tok, indices in token_to_indices.items():
        idx_list = sorted(indices)
        for ii in range(len(idx_list)):
            for jj in range(ii + 1, len(idx_list)):
                i, j = idx_list[ii], idx_list[jj]
                # Skip if already in same group
                if uf.find(i) == uf.find(j):
                    continue
                pair = (i, j)
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                if _is_duplicate_pair(deals[i], deals[j]):
                    uf.union(i, j)
                    fuzzy_merges += 1

    if verbose:
        print(f"  Pass 2 (fuzzy):    {fuzzy_merges} additional duplicates found "
              f"({len(checked_pairs)} pairs checked)")

    # ---------------------------------------------------------------
    # Build groups and merge
    # ---------------------------------------------------------------
    groups = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    result = []
    merge_report = []

    for root, member_indices in sorted(groups.items()):
        group_deals = [deals[i] for i in member_indices]
        merged = _merge_deal_group(group_deals)
        result.append(merged)

        if verbose and len(member_indices) > 1:
            names = []
            for d in group_deals:
                acq = _get_field(d, "acquiror")
                tgt = _get_field(d, "target")
                names.append(f"{acq} + {tgt}")
            merge_report.append((len(member_indices), names,
                                 _get_field(merged, "acquiror"),
                                 _get_field(merged, "target")))

    if verbose:
        dup_groups = sum(1 for v in groups.values() if len(v) > 1)
        total_dupes = sum(len(v) - 1 for v in groups.values() if len(v) > 1)
        print(f"\n  DEDUP SUMMARY: {n} deals → {len(result)} unique "
              f"({total_dupes} duplicates in {dup_groups} groups)")

        if merge_report:
            # Sort by group size descending
            merge_report.sort(key=lambda x: x[0], reverse=True)
            print(f"\n  Top merged groups:")
            for count, names, merged_acq, merged_tgt in merge_report[:20]:
                print(f"    [{count}x] → {merged_acq} + {merged_tgt}")
                for name in names:
                    print(f"           - {name}")

    return result
