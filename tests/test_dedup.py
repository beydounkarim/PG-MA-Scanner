"""
Unit tests for dedup.py
"""

import pytest
from src.dedup import generate_deal_id, is_new_alert, update_state_in_memory


class TestGenerateDealId:
    """Test deal ID generation and normalization."""

    def test_basic_deal_id(self):
        deal_id = generate_deal_id("Chevron", "Hess")
        assert deal_id == "chevron_hess"

    def test_with_suffixes(self):
        deal_id = generate_deal_id("Chevron Corporation", "Hess Corp")
        assert deal_id == "chevron_hess"

    def test_case_insensitive(self):
        deal_id1 = generate_deal_id("CHEVRON", "HESS")
        deal_id2 = generate_deal_id("Chevron", "Hess")
        assert deal_id1 == deal_id2

    def test_merger_alphabetical_sorting(self):
        # For mergers, should sort alphabetically
        deal_id1 = generate_deal_id("Company A", "Company B")
        deal_id2 = generate_deal_id("Company B", "Company A")
        assert deal_id1 == deal_id2
        assert deal_id1 == "company_a_company_b"

    def test_special_characters_replaced(self):
        deal_id = generate_deal_id("Company & Co.", "Target-Corp")
        assert "_" in deal_id
        assert "&" not in deal_id
        assert "-" not in deal_id

    def test_strip_various_suffixes(self):
        suffixes = [
            ("Hess Corporation", "hess"),
            ("Hess Corp.", "hess"),
            ("Hess Inc.", "hess"),
            ("Hess Limited", "hess"),
            ("Hess LLC", "hess"),
            ("Hess Holdings", "hess"),
            ("Hess Group", "hess"),
        ]
        for input_name, expected in suffixes:
            deal_id = generate_deal_id(input_name, "Target")
            assert expected in deal_id

    def test_empty_inputs(self):
        deal_id = generate_deal_id("", "")
        assert deal_id == "unknown_deal"

        deal_id = generate_deal_id("Chevron", "")
        assert deal_id == "chevron"

        deal_id = generate_deal_id("", "Hess")
        assert deal_id == "hess"


class TestIsNewAlert:
    """Test new alert detection logic."""

    def test_completely_new_deal(self):
        """Deal not in state should trigger alert."""
        state = {}
        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "Rumored"
        }
        assert is_new_alert(deal, state) is True

    def test_new_stage_on_existing_deal(self):
        """New stage on existing deal should trigger alert."""
        state = {
            "chevron_hess": {
                "stages_reported": ["rumored"],
                "acquiror": "Chevron",
                "target": "Hess"
            }
        }
        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "Announced"
        }
        assert is_new_alert(deal, state) is True

    def test_duplicate_stage(self):
        """Same stage should not trigger alert."""
        state = {
            "chevron_hess": {
                "stages_reported": ["rumored", "announced"],
                "acquiror": "Chevron",
                "target": "Hess"
            }
        }
        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "Announced"
        }
        assert is_new_alert(deal, state) is False

    def test_max_three_alerts(self):
        """After 3 alerts, no more alerts should be triggered."""
        state = {
            "chevron_hess": {
                "stages_reported": ["rumored", "announced", "closed"],
                "acquiror": "Chevron",
                "target": "Hess"
            }
        }
        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "Completed"  # 4th stage
        }
        assert is_new_alert(deal, state) is False

    def test_case_insensitive_status_matching(self):
        """Status matching should be case-insensitive."""
        state = {
            "chevron_hess": {
                "stages_reported": ["Rumored"],  # Title case
                "acquiror": "Chevron",
                "target": "Hess"
            }
        }
        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "rumored"  # Lowercase
        }
        assert is_new_alert(deal, state) is False

    def test_generate_deal_id_if_missing(self):
        """Should generate deal_id from acquiror+target if missing."""
        state = {}
        deal = {
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Rumored"
        }
        assert is_new_alert(deal, state) is True

    def test_alternative_field_name(self):
        """Should handle 'Deal Status' field name."""
        state = {}
        deal = {
            "deal_id": "chevron_hess",
            "Deal Status": "Rumored"  # Alternative field name
        }
        assert is_new_alert(deal, state) is True


class TestUpdateStateInMemory:
    """Test in-memory state updates."""

    def test_add_new_deal_to_empty_state(self):
        """Adding new deal should create state entry."""
        state = {}
        deal = {
            "deal_id": "chevron_hess",
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Rumored",
            "first_seen": "2024-01-15",
            "last_updated": "2024-01-15"
        }

        updated_state = update_state_in_memory(deal, state)

        assert "chevron_hess" in updated_state
        assert updated_state["chevron_hess"]["acquiror"] == "Chevron"
        assert updated_state["chevron_hess"]["target"] == "Hess"
        assert "rumored" in updated_state["chevron_hess"]["stages_reported"]

    def test_add_new_stage_to_existing_deal(self):
        """Adding new stage should append to stages_reported."""
        state = {
            "chevron_hess": {
                "acquiror": "Chevron",
                "target": "Hess",
                "deal_id": "chevron_hess",
                "stages_reported": ["rumored"],
                "first_seen": "2024-01-15",
                "last_updated": "2024-01-15",
                "current_status": "rumored"
            }
        }

        deal = {
            "deal_id": "chevron_hess",
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Announced",
            "last_updated": "2024-05-01"
        }

        updated_state = update_state_in_memory(deal, state)

        assert len(updated_state["chevron_hess"]["stages_reported"]) == 2
        assert "rumored" in updated_state["chevron_hess"]["stages_reported"]
        assert "announced" in updated_state["chevron_hess"]["stages_reported"]
        assert updated_state["chevron_hess"]["last_updated"] == "2024-05-01"

    def test_duplicate_stage_not_added_twice(self):
        """Adding same stage twice should not duplicate in stages_reported."""
        state = {
            "chevron_hess": {
                "acquiror": "Chevron",
                "target": "Hess",
                "deal_id": "chevron_hess",
                "stages_reported": ["rumored", "announced"],
                "first_seen": "2024-01-15",
                "last_updated": "2024-05-01",
                "current_status": "announced"
            }
        }

        deal = {
            "deal_id": "chevron_hess",
            "deal_status": "Announced"  # Duplicate
        }

        updated_state = update_state_in_memory(deal, state)

        # Should still only have 2 stages
        assert len(updated_state["chevron_hess"]["stages_reported"]) == 2

    def test_generate_deal_id_if_missing(self):
        """Should generate deal_id if not provided."""
        state = {}
        deal = {
            "acquiror": "Chevron Corporation",
            "target": "Hess Corp",
            "deal_status": "Rumored"
        }

        updated_state = update_state_in_memory(deal, state)

        assert "chevron_hess" in updated_state


class TestIntegrationScenario:
    """Test realistic deduplication scenarios."""

    def test_full_lifecycle(self):
        """Test deal progression through all stages."""
        state = {}

        # Stage 1: Rumor
        deal_rumor = {
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Rumored",
            "first_seen": "2024-01-15"
        }
        assert is_new_alert(deal_rumor, state) is True
        state = update_state_in_memory(deal_rumor, state)

        # Stage 2: Announced
        deal_announced = {
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Announced",
            "last_updated": "2024-05-01"
        }
        assert is_new_alert(deal_announced, state) is True
        state = update_state_in_memory(deal_announced, state)

        # Stage 3: Closed
        deal_closed = {
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Closed",
            "last_updated": "2024-10-01"
        }
        assert is_new_alert(deal_closed, state) is True
        state = update_state_in_memory(deal_closed, state)

        # Verify state
        assert len(state["chevron_hess"]["stages_reported"]) == 3
        assert "rumored" in state["chevron_hess"]["stages_reported"]
        assert "announced" in state["chevron_hess"]["stages_reported"]
        assert "closed" in state["chevron_hess"]["stages_reported"]

        # Stage 4: Any additional stage should be rejected (max 3)
        deal_completed = {
            "acquiror": "Chevron",
            "target": "Hess",
            "deal_status": "Completed"
        }
        assert is_new_alert(deal_completed, state) is False
