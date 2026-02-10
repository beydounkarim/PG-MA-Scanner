"""
Unit tests for notifier.py
"""

import pytest
from unittest.mock import patch, Mock
from src.notifier import notify_slack, notify_teams, notify_all


class TestNotifySlack:
    """Test Slack notification."""

    @patch('src.notifier.requests.post')
    @patch.dict('os.environ', {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'})
    def test_notify_slack_success(self, mock_post):
        """Test successful Slack notification."""
        mock_post.return_value = Mock(status_code=200)

        deals = [
            {"acquiror": "Chevron", "target": "Hess", "deal_value": "$53B", "deal_status": "Closed"}
        ]
        result = notify_slack(deals, "https://docs.google.com/spreadsheets/d/123")

        assert result is True
        assert mock_post.called
        call_args = mock_post.call_args
        assert "Chevron" in call_args.kwargs['json']['text']
        assert "Hess" in call_args.kwargs['json']['text']

    @patch.dict('os.environ', {}, clear=True)
    def test_notify_slack_no_webhook(self):
        """Test Slack notification without webhook URL."""
        deals = []
        result = notify_slack(deals, "https://example.com")

        assert result is False

    @patch('src.notifier.requests.post')
    @patch.dict('os.environ', {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'})
    def test_notify_slack_request_error(self, mock_post):
        """Test Slack notification with request error."""
        mock_post.side_effect = Exception("Network error")

        deals = [{"acquiror": "Company A", "target": "Company B"}]
        result = notify_slack(deals, "https://example.com")

        assert result is False

    @patch('src.notifier.requests.post')
    @patch.dict('os.environ', {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'})
    def test_notify_slack_truncates_long_list(self, mock_post):
        """Test that long deal lists are truncated to top 5."""
        mock_post.return_value = Mock(status_code=200)

        deals = [
            {"acquiror": f"Company {i}", "target": f"Target {i}", "deal_value": "$1B", "deal_status": "Announced"}
            for i in range(10)
        ]
        result = notify_slack(deals, "https://example.com")

        assert result is True
        message = mock_post.call_args.kwargs['json']['text']
        assert "...and 5 more" in message


class TestNotifyTeams:
    """Test Teams notification."""

    @patch('src.notifier.requests.post')
    @patch.dict('os.environ', {'TEAMS_WEBHOOK_URL': 'https://outlook.office.com/webhook/test'})
    def test_notify_teams_success(self, mock_post):
        """Test successful Teams notification."""
        mock_post.return_value = Mock(status_code=200)

        deals = [
            {"acquiror": "Chevron", "target": "Hess", "deal_value": "$53B", "deal_status": "Closed"}
        ]
        result = notify_teams(deals, "https://docs.google.com/spreadsheets/d/123")

        assert result is True
        assert mock_post.called

        # Verify Adaptive Card structure
        card = mock_post.call_args.kwargs['json']
        assert card['type'] == 'message'
        assert 'attachments' in card

    @patch.dict('os.environ', {}, clear=True)
    def test_notify_teams_no_webhook(self):
        """Test Teams notification without webhook URL."""
        deals = []
        result = notify_teams(deals, "https://example.com")

        assert result is False

    @patch('src.notifier.requests.post')
    @patch.dict('os.environ', {'TEAMS_WEBHOOK_URL': 'https://outlook.office.com/webhook/test'})
    def test_notify_teams_has_action_button(self, mock_post):
        """Test that Teams card has View Full Report button."""
        mock_post.return_value = Mock(status_code=200)

        deals = [{"acquiror": "Company A", "target": "Company B"}]
        sheet_url = "https://docs.google.com/spreadsheets/d/123"
        notify_teams(deals, sheet_url)

        card = mock_post.call_args.kwargs['json']
        actions = card['attachments'][0]['content']['actions']
        assert len(actions) == 1
        assert actions[0]['type'] == 'Action.OpenUrl'
        assert actions[0]['url'] == sheet_url


class TestNotifyAll:
    """Test combined notification function."""

    @patch('src.notifier.notify_slack')
    @patch('src.notifier.notify_teams')
    def test_notify_all_calls_both(self, mock_teams, mock_slack):
        """Test that notify_all calls both Slack and Teams."""
        mock_slack.return_value = True
        mock_teams.return_value = True

        deals = [{"acquiror": "Company A", "target": "Company B"}]
        results = notify_all(deals, "https://example.com")

        assert mock_slack.called
        assert mock_teams.called
        assert results['slack_success'] is True
        assert results['teams_success'] is True

    @patch('src.notifier.notify_slack')
    @patch('src.notifier.notify_teams')
    def test_notify_all_handles_partial_failure(self, mock_teams, mock_slack):
        """Test that notify_all continues even if one fails."""
        mock_slack.return_value = True
        mock_teams.return_value = False

        deals = []
        results = notify_all(deals, "https://example.com")

        assert results['slack_success'] is True
        assert results['teams_success'] is False
