# PG M&A Deal Scanner

Automated Python agent monitoring ~651 Prometheus Group customer accounts for M&A activity (acquisitions, mergers, divestitures, spin-offs). Produces a cumulative Google Sheets report with actionable sales intelligence.

## What This Does

**Why:** Customer acquires a company → upsell opportunity. Customer divests → revenue at risk. Sales needs to know within days.

**How:**
- Scans ~651 PG customer accounts using Claude API + web search
- 4-tier scanning approach for comprehensive coverage
- 4-stage source validation pipeline to prevent fabricated URLs
- Outputs to Google Sheets (4 tabs: Executive Summary, Deals, Excluded, Unverified)
- Sends Slack/Teams notifications with link to live Google Sheet
- Runs weekly via GitHub Actions

## Architecture

```
src/main.py             → CLI entry point (--period REQUIRED, --test, --dry-run)
src/scanner.py          → Claude API + web search, 4-tier scanning
src/matcher.py          → Fuzzy matching against PG_Acct_List.xlsx
src/dedup.py            → Deal deduplication against Google Sheets state
src/source_validator.py → 4-stage URL validation (THE critical QA/QC gate)
src/sheets_output.py    → Google Sheets read/write (single source of truth)
src/notifier.py         → Slack & Teams webhook delivery
data/PG_Acct_List.xlsx  → Master company list (~651 companies)
.github/workflows/scan.yml → Weekly cron + manual trigger
```

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd PG-M&A-Scanner

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 2. Configuration

You'll need:
- **Anthropic API key** - Get from https://console.anthropic.com
- **Google Service Account JSON** - See Google Cloud Setup below
- **Google Sheet ID** - Create a sheet and copy ID from URL
- **Slack Webhook URL** (optional) - For notifications
- **Teams Webhook URL** (optional) - For notifications

### 3. Google Cloud Setup

1. Create a Google Cloud project
2. Enable Google Sheets API and Google Drive API
3. Create a service account and download JSON credentials
4. Share your Google Sheet with the service account email (Editor access)
5. Set `GOOGLE_SERVICE_ACCOUNT_JSON` in .env to the full JSON content

### 4. Add Company List

Place your `PG_Acct_List.xlsx` file in the `data/` directory with two sheets:
- `A&B Customers` - High priority accounts
- `C&D Customers` - Standard accounts

Each sheet should have columns: `Account Name`, `Clean Name`

## Usage

### Command Line

```bash
# Weekly scan (last Monday-Sunday)
python src/main.py --period last_week

# Test mode (first 20 companies only)
python src/main.py --period last_week --test

# Dry run (scan but don't write to Sheets)
python src/main.py --period last_month --dry-run

# Full year scan
python src/main.py --period 2025

# Custom date range
python src/main.py --period custom:2024-06-01:2024-12-31
```

### Period Options

- `last_week` - Previous Monday-Sunday
- `last_month` - Previous calendar month
- `last_quarter` - Previous Q1/Q2/Q3/Q4
- `last_6_months` - Last 182 days
- `YYYY` - Full year (e.g., `2025`)
- `YYYY-QN` - Specific quarter (e.g., `2024-Q4`)
- `YYYY-MM` - Specific month (e.g., `2025-01`)
- `custom:START:END` - Custom range (e.g., `custom:2024-06-01:2024-12-31`)

### GitHub Actions (Automated)

**Automated weekly run:** Every Monday at 9 AM ET via cron schedule

**Manual run:**
1. Go to GitHub repo → Actions tab
2. Click "PG M&A Scanner" workflow
3. Click "Run workflow"
4. Select period and options
5. Click "Run workflow" button

## Output

### Google Sheet Structure (4 Tabs)

**Tab 1: Executive Summary**
- Total deals, new this cycle, by status, by sector
- Top 5 largest deals
- Source validation summary
- Last scan date and period

**Tab 2: Deals** (15 fields + metadata)
- New rows inserted at top, highlighted yellow
- ✓ Verified or 🔄 Re-sourced sources only
- Hidden metadata: deal_id, stages_reported, first_seen, last_updated, scan_period

**Tab 3: Excluded (Non-Strategic)**
- PE/financial/IPO deals with exclusion reason
- Cumulative record

**Tab 4: Unverified**
- Deals where no valid source URL could be found
- For manual review and re-sourcing

### 15 Output Fields Per Deal

1. PG Account Name
2. Clean Name
3. Acquiror
4. Target
5. Deal Status (Rumored / Announced / Closed)
6. Sector
7. Description (1-2 sentence summary)
8. Date of Rumor
9. Date of Announcement
10. Date Closed
11. Deal Value ($)
12. Source (publication name)
13. Source Link (validated URL)
14. Potential Opportunity for PG
15. Source Validation (✓ Verified / 🔄 Re-sourced / ⚠️ Unverified)

## Key Features

### 4-Stage Source Validation Pipeline

**THE critical quality gate** - LLMs routinely fabricate plausible URLs that 404.

- **Stage 0:** Cross-deal QA (duplicate URLs, generic patterns, suspicious slugs)
- **Stage 1:** HTTP reachability check (200 OK vs 404)
- **Stage 2:** Content relevance matching (page mentions acquiror + target)
- **Stage 3:** Auto re-sourcing via Claude if Stages 1-2 fail

Results: ✓ Verified (original URL good) | 🔄 Re-sourced (replacement found) | ⚠️ Unverified (manual review needed)

### Deduplication

- Max 3 alerts per deal lifecycle: rumor → announced → closed
- Keyed by normalized acquiror+target pair
- State read from Google Sheets at scan start

### Business Rules

**Include:**
- Acquisitions, mergers, divestitures, spin-offs
- Operating companies in: oil & gas, mining, utilities, manufacturing, chemicals, cement, steel/metals, midstream/pipeline, paper/pulp, water/waste, packaging, industrial gases, agribusiness
- All stages (rumor/announced/closed)
- Global scope, no minimum deal size

**Exclude:**
- PE/financial buyers (Carlyle, KKR, Apollo, Blackstone, etc.)
- Joint ventures
- IPOs
- Internal restructurings

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_matcher.py

# Run with coverage
pytest --cov=src tests/
```

## Cost Estimates

**API Costs per Weekly Run:**
- Tier 1: ~$0.75
- Tier 2: ~$1.32
- Tier 3: ~$0.75
- Tier 4: ~$0.80
- Source validation (re-sourcing): ~$0.40
- **Total: ~$4-5 per week, ~$20/month**

**GitHub Actions:**
- Free tier: 2,000 minutes/month
- Weekly run: ~30-45 minutes
- Monthly usage: ~180 minutes (well within limits)

## Troubleshooting

### Common Issues

**"Fabricated URLs" / 404 errors:**
- This is the #1 quality issue - LLMs make up URLs
- The 4-stage validation pipeline catches these
- Check the Unverified tab for deals needing manual review

**Google Sheets authentication fails:**
- Verify `GOOGLE_SERVICE_ACCOUNT_JSON` contains full JSON (not file path)
- Verify Sheet is shared with service account email
- Check service account has Editor access

**gspread rate limits (429 errors):**
- Built-in exponential backoff handles this
- If persistent, reduce batch size or add delays

**No deals found:**
- Verify period is correct (check resolved dates in output)
- Try `--test` mode first to validate setup
- Check Claude API key is valid

## Project Status

**Current Implementation:** Phase 1 - Foundation & Configuration

**Remaining Phases:**
- Phase 2: Company Matcher & Period Resolution
- Phase 3: Google Sheets Integration
- Phase 4: Source Validation Pipeline
- Phase 5: Scanner & Claude API Integration
- Phase 6: Deduplication & Main Orchestration
- Phase 7: Notifications & GitHub Actions

## License

Proprietary - Prometheus Group Internal Use Only

## Support

For issues or questions, contact [your team/email]
