"""
Reinforcement learning knowledge base loader.

Reads data/reinforcement_learning.md and injects accumulated learnings
into scanner prompts. Graceful degradation: if the file is missing,
all functions return empty strings and the scanner works unchanged.
"""

import os
import re
from datetime import date

# Path to the knowledge base (relative to project root)
_RL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "reinforcement_learning.md"
)

# Tier -> sections mapping
_TIER_SECTIONS = {
    "tier1": [
        "KNOWN HALLUCINATION PATTERNS",
        "DEAL TYPE RULES",
        "SECTOR PATTERNS",
    ],
    "tier2": [
        "KNOWN HALLUCINATION PATTERNS",
        "DEAL TYPE RULES",
        "DEAL STATUS PATTERNS",
    ],
    "tier2_ab": [
        "KNOWN HALLUCINATION PATTERNS",
        "DEAL TYPE RULES",
        "DEAL STATUS PATTERNS",
    ],
    "tier3": [
        "KNOWN HALLUCINATION PATTERNS",
        "DEAL TYPE RULES",
        "DEAL STATUS PATTERNS",
    ],
    "tier4": [
        "OPPORTUNITY CLASSIFICATION LESSONS",
    ],
    "source_validation": [
        "SOURCE VALIDATION LESSONS",
    ],
}


def load_reinforcement_knowledge() -> str:
    """Load the full reinforcement learning file. Returns '' if missing."""
    try:
        with open(_RL_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def extract_section(content: str, header: str) -> str:
    """
    Extract content under a ## Header, up to the next ## or end of file.

    Args:
        content: Full markdown file content
        header: Section header name (without ##)

    Returns:
        Section content (without the header line itself), or ''
    """
    if not content:
        return ""

    # Match ## HEADER through next ## or end of string
    pattern = rf"^## {re.escape(header)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def get_prompt_injection(tier: str) -> str:
    """
    Build a formatted context block for a specific tier's system prompt.

    Args:
        tier: One of 'tier1', 'tier2', 'tier2_ab', 'tier3', 'tier4', 'source_validation'

    Returns:
        Formatted string to append to the system prompt, or ''
    """
    section_names = _TIER_SECTIONS.get(tier, [])
    if not section_names:
        return ""

    content = load_reinforcement_knowledge()
    if not content:
        return ""

    blocks = []
    for name in section_names:
        section = extract_section(content, name)
        if section:
            blocks.append(f"=== {name} ===\n{section}")

    if not blocks:
        return ""

    return (
        "--- REINFORCEMENT LEARNING CONTEXT (accumulated from prior scans) ---\n\n"
        + "\n\n".join(blocks)
        + "\n\n--- END REINFORCEMENT LEARNING CONTEXT ---"
    )


def append_scan_run_log(
    period: str,
    num_companies: int,
    tier1_count: int,
    tier2_ab_count: int,
    tier2_cd_count: int,
    tier3_verified: int,
    new_deals: int,
    excluded: int,
    unverified: int,
    notes: str = "",
) -> None:
    """
    Append a row to the SCAN RUN LOG table at the end of the RL file.

    Silently does nothing if the file doesn't exist.
    """
    try:
        content = load_reinforcement_knowledge()
        if not content:
            return

        today = date.today().isoformat()
        row = (
            f"| {today} | {period} | {num_companies} | {tier1_count} "
            f"| {tier2_ab_count} | {tier2_cd_count} | {tier3_verified} "
            f"| {new_deals} | {excluded} | {unverified} | {notes} |"
        )

        with open(_RL_PATH, "a", encoding="utf-8") as f:
            f.write(row + "\n")

    except Exception:
        pass  # Non-critical; never break the pipeline


def append_learning(section: str, bullet: str) -> None:
    """
    Append a bullet point to a specific section of the RL file.

    Args:
        section: Section header name (without ##), e.g. 'KNOWN HALLUCINATION PATTERNS'
        bullet: Text to append (will be prefixed with '- ')
    """
    try:
        content = load_reinforcement_knowledge()
        if not content:
            return

        marker = f"## {section}"
        idx = content.find(marker)
        if idx == -1:
            return

        # Find the end of this section (next ## or end of file)
        next_section = content.find("\n## ", idx + len(marker))
        if next_section == -1:
            insert_pos = len(content)
        else:
            # Insert before the blank line preceding the next section
            insert_pos = next_section

        # Ensure proper formatting
        new_bullet = f"- {bullet}\n"

        updated = content[:insert_pos].rstrip() + "\n" + new_bullet + "\n" + content[insert_pos:]

        with open(_RL_PATH, "w", encoding="utf-8") as f:
            f.write(updated)

    except Exception:
        pass  # Non-critical; never break the pipeline
