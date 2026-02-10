"""
Notification module for Slack and Teams.

Sends summary notifications with link to Google Sheet.
No file attachments needed - the Sheet IS the report.
"""

import requests
import os
from typing import Optional


def notify_slack(new_deals: list[dict], sheet_url: str) -> bool:
    """
    Post a summary to Slack with a link to the Google Sheet.

    Uses a simple incoming webhook - no bot token required.

    Args:
        new_deals: List of new deal dicts
        sheet_url: URL to Google Sheet

    Returns:
        True if successful, False otherwise
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return False

    deal_count = len(new_deals)

    # Build summary lines for top deals
    deal_lines = []
    for deal in new_deals[:5]:
        acquiror = deal.get("acquiror", "?")
        target = deal.get("target", "?")
        value = deal.get("deal_value", "")
        status = deal.get("deal_status", "")
        value_str = f" ({value})" if value else ""
        deal_lines.append(f"• {acquiror} → {target}{value_str} [{status}]")

    if deal_count > 5:
        deal_lines.append(f"  ...and {deal_count - 5} more")

    deals_text = "\n".join(deal_lines) if deal_lines else "No new deals this cycle"

    message = (
        f"🔔 *PG M&A Scanner: {deal_count} new deal{'s' if deal_count != 1 else ''} found*\n\n"
        f"{deals_text}\n\n"
        f"📊 <{sheet_url}|View full report in Google Sheets>"
    )

    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        print(f"✓ Slack notification sent ({deal_count} deals)")
        return True
    except requests.RequestException as e:
        print(f"⚠️ Slack notification failed: {e}")
        return False


def notify_teams(new_deals: list[dict], sheet_url: str) -> bool:
    """
    Post a summary to Microsoft Teams via incoming webhook.

    Args:
        new_deals: List of new deal dicts
        sheet_url: URL to Google Sheet

    Returns:
        True if successful, False otherwise
    """
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        print("TEAMS_WEBHOOK_URL not set, skipping Teams notification")
        return False

    deal_count = len(new_deals)

    # Build summary lines for top deals
    deal_lines = []
    for deal in new_deals[:5]:
        acquiror = deal.get("acquiror", "?")
        target = deal.get("target", "?")
        value = deal.get("deal_value", "")
        status = deal.get("deal_status", "")
        value_str = f" ({value})" if value else ""
        deal_lines.append(f"- {acquiror} → {target}{value_str} [{status}]")

    if deal_count > 5:
        deal_lines.append(f"  ...and {deal_count - 5} more")

    deals_text = "\n".join(deal_lines) if deal_lines else "No new deals this cycle"

    # Teams Adaptive Card format
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.4",
                "body": [
                    {
                        "type": "TextBlock",
                        "size": "Medium",
                        "weight": "Bolder",
                        "text": f"🔔 PG M&A Scanner: {deal_count} new deal{'s' if deal_count != 1 else ''}"
                    },
                    {
                        "type": "TextBlock",
                        "text": deals_text,
                        "wrap": True
                    },
                ],
                "actions": [
                    {
                        "type": "Action.OpenUrl",
                        "title": "View Full Report",
                        "url": sheet_url
                    }
                ]
            }
        }]
    }

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        resp.raise_for_status()
        print(f"✓ Teams notification sent ({deal_count} deals)")
        return True
    except requests.RequestException as e:
        print(f"⚠️ Teams notification failed: {e}")
        return False


def notify_all(new_deals: list[dict], sheet_url: str) -> dict:
    """
    Send notifications to all configured channels.

    Args:
        new_deals: List of new deal dicts
        sheet_url: URL to Google Sheet

    Returns:
        Dict with keys: slack_success, teams_success
    """
    results = {
        "slack_success": notify_slack(new_deals, sheet_url),
        "teams_success": notify_teams(new_deals, sheet_url),
    }

    return results
