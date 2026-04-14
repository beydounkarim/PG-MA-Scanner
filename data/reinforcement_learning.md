# PG M&A Scanner - Reinforcement Learning Knowledge Base

> This file is read by the scanner at runtime and injected into LLM prompts.
> It captures accumulated learnings from cross-referencing scanner output against Pitchbook data,
> manual QA, and scan-over-scan pattern analysis.
>
> **Format rules**: Each `## Section` is a self-contained block. The scanner extracts sections
> by header name. Bullets under each section are the actual rules/learnings.

---

## KNOWN HALLUCINATION PATTERNS

These patterns have been observed in scanner output and should be actively guarded against:

- **Malformed deal types**: The scanner occasionally produces slug-format deal types like "joint-venture" or "asset-transfer" instead of proper labels. ~71 instances observed in a 1,475-deal corpus. Always use the canonical deal types listed in DEAL TYPE RULES.
- **Fabricated URLs**: LLMs routinely construct plausible-looking URLs that 404. Never construct a URL from a domain + assumed path. Only return URLs that appeared in web search results.
- **Temporal hallucinations**: 43.7% of "new" scanner deals were dated before 2024 in a scan targeting recent activity. Always enforce the date range strictly. If a deal's only activity is outside the scan window, exclude it.
- **Company name anomalies**: SI Group appeared in 40 deals (4x the next highest company) in one scan run, suggesting the LLM over-indexed on a single company. If you find yourself returning more than 5 deals for a single company in one query, double-check each one independently.
- **Pre-2010 deals**: 5 deals dated before 2010 appeared in a recent-period scan. These are almost certainly hallucinated or irrelevant. Exclude any deal with activity solely before 2015 unless the scan period explicitly covers that range.
- **Ghost JVs**: The scanner sometimes invents joint ventures that don't exist, particularly for companies with complex partnership histories. Verify JV entity names against search results.

---

## DEAL TYPE RULES

**Canonical deal types** (use EXACTLY these labels, case-sensitive):
- Acquisition
- Merger
- Divestiture
- Spin-off
- Joint Venture
- Asset Transfer
- Investment/Stake

**Classification guidance:**
- If a company buys another company or its business unit outright -> Acquisition
- If two companies combine as relative equals -> Merger
- If a company sells off a division, subsidiary, or business unit -> Divestiture
- If a company separates a division into an independent entity -> Spin-off
- If two or more companies form a new entity together -> Joint Venture
- If companies swap or transfer specific physical assets (plants, pipelines, etc.) -> Asset Transfer
- If a company takes a minority stake, makes a strategic investment, or increases ownership without full acquisition -> Investment/Stake

**Common mistakes to avoid:**
- Do NOT use hyphenated forms: "joint-venture", "asset-transfer", "spin-off" with lowercase
- Do NOT use "Takeover" (use Acquisition)
- Do NOT use "Purchase" (use Acquisition)
- Do NOT use "Partnership" (use Joint Venture if a new entity is formed, otherwise Investment/Stake)
- Do NOT use "Consolidation" (use Merger)
- Do NOT use "Buyout" (use Acquisition)

---

## SECTOR PATTERNS

**Pitchbook industry groups — scanner miss rate** (950 missed / 791 matched, from 1,741 Pitchbook deals):

Well-covered (miss rate <50%):
- Exploration, Production & Refining: 111 missed / 127 matched (47%)
- Chemicals & Gases: 65 missed / 58 matched (53%) — borderline
- Metals, Minerals & Mining: 68 missed / 63 matched (52%) — borderline
- Utilities: 24 missed / 25 matched (49%)
- Construction (Non-Wood): 22 missed / 23 matched (49%)
- Containers & Packaging: 13 missed / 26 matched (33%) — strong

Major blind spots (miss rate >55%):
- Commercial Services: 133 missed / 88 matched (60%) — environmental services, construction & engineering, logistics
- Commercial Products: 129 missed / 111 matched (54%) — industrial equipment, steel distribution
- Consumer Non-Durables: 62 missed / 45 matched (58%) — food/beverage/agri adjacent
- Software/IT Services: 45+22 missed / 19+5 matched (74%) — but many should be excluded per PG focus
- Energy Equipment: 18 missed / 10 matched (64%)
- Agriculture: 14 missed / 6 matched (70%)
- Transportation/Logistics: 25 missed / 12 matched (68%)

**Pitchbook sub-sectors the scanner consistently misses:**
- Environmental Services (waste, water treatment, remediation)
- Construction & Engineering services (EPC contractors, civil works)
- Logistics & commercial transportation (fleet, warehousing)
- Energy equipment manufacturers (turbines, transformers, compressors)
- Food & beverage processing (adjacent to agribusiness)

**Action**: Expand Tier 1 queries to include environmental services, construction & engineering, logistics, energy equipment, and food processing. These are PG-relevant industrial sectors that the current query set under-covers.

---

## SOURCE VALIDATION LESSONS

Learnings from the 4-stage source validation pipeline:

- **72.1% of new scanner deals required re-sourcing** in the initial cross-reference analysis. This is a known weakness - the scanner's first-pass URLs are unreliable.
- **Known bad URL patterns**: Generic newsroom pages (/press-releases, /news, /newsroom), URLs with both company names in the slug (likely fabricated), URLs without date paths on corporate sites.
- **Re-sourcing success patterns**: Reuters, Bloomberg, and trade publications (Chemical Week, Mining Weekly, Oil & Gas Journal) have the highest re-sourcing success rate. Prioritize these in Stage 3.
- **Press releases vs. news articles**: Company press releases are more authoritative but harder to find via web search. News articles from Reuters/Bloomberg are easier to find and sufficiently authoritative.
- **Paywall handling**: Some valid sources (FT, WSJ) may appear unreachable due to paywalls. If a URL returns 200 but content relevance is low, it may be behind a soft paywall - flag as medium confidence rather than failing.

---

## DEDUP AND MATCHING LESSONS

Learnings for fuzzy matching and deduplication:

- **Parent/subsidiary framing**: The same deal can appear as "Parent Corp acquires Target" or "Subsidiary LLC acquires Target". Normalize to the ultimate parent company when possible.
- **JV naming**: Joint ventures often appear with different party orderings. Always sort parties alphabetically to create consistent deal IDs.
- **Stop words for matching**: Ignore "Corporation", "Corp.", "Inc.", "Ltd.", "LLC", "PLC", "SA", "SE", "Group", "Limited", "Holdings", "International", "Enterprises" when comparing company names.
- **Abbreviation handling**: Common abbreviations should match full names: "BASF" = "BASF SE", "BHP" = "BHP Group", "Rio" = "Rio Tinto".
- **Deal ID stability**: The deal ID is generated from normalized acquiror + target names. Changing the normalization logic will invalidate existing dedup state.

---

## OPPORTUNITY CLASSIFICATION LESSONS

**Distribution from cross-referencing** (715 overlapping deals):
- OFFENSIVE (Upsell): ~35% of classified deals
- DEFENSIVE (Risk): ~25% of classified deals
- MONITOR: ~40% of classified deals

**Common misclassification rules:**
- Investment/Stake deals should almost always be MONITOR, not OFFENSIVE (no full acquisition = no license extension opportunity)
- Joint Ventures default to MONITOR unless clear facility-level implications exist
- Divestitures where PG customer is the SELLER should be DEFENSIVE (risk of losing the divested assets), not OFFENSIVE
- If acquiror is PG customer AND target has industrial facilities -> OFFENSIVE
- If acquiror is NOT PG customer AND target IS PG customer -> DEFENSIVE
- If neither party is a PG customer -> MONITOR (competitive intelligence only)

---

## DEAL STATUS PATTERNS

**Status distribution from cross-referencing:**
- Closed: ~55% of deals
- Announced: ~30% of deals
- Rumored: ~15% of deals

**Status assignment rules:**
- A deal is "Closed" only if there is explicit confirmation of deal completion/closing
- A deal is "Announced" if there is a formal announcement or definitive agreement but no closing confirmation
- A deal is "Rumored" if sources cite unnamed sources, "reportedly", "in talks", "exploring", or "considering"
- If a deal has multiple statuses (e.g., announced then closed), use the LATEST status
- Never guess the status - if unclear from sources, default to "Announced"

---

## PITCHBOOK COVERAGE GAP ANALYSIS

Cross-reference of 1,741 Pitchbook customer deals vs scanner output. 791 matched, 950 missed (55%).

**Scanner strengths** (760 deals found by scanner but NOT in Pitchbook):
- Scanner excels at finding: recent announcements, smaller asset transfers, JVs in niche sectors, deals covered only by trade publications
- Scanner catches deals faster than Pitchbook's manual entry process
- Stronger on Americas-based deals (51.6% of matched vs 42.8% of missed)

**Gap 1: Joint Ventures are the #1 blind spot**
- 326 JVs missed vs only 120 found — 73% miss rate on JVs vs 48% on M&A
- Worst JV gaps by sector: Exploration/Refining (64 missed), Commercial Services (53), Energy Services (42), Mining (32)
- Worst JV gaps by region: Americas (113 missed), Europe (94), Asia (58), Middle East (31)
- Many missed JVs are multi-party (3+ partners) which the scanner's 2-party model doesn't capture well

**Gap 2: Older deals decay sharply**
- 2021 deals: 70% miss rate (236/338)
- 2022 deals: 55% miss rate (218/397)
- 2023 deals: 56% miss rate (194/346)
- 2024 deals: 44% miss rate (141/322) — best year
- 2025 deals: 48% miss rate (136/286)
- Web search results naturally deprioritize older news. For historical scans, add year-specific queries.

**Gap 3: Geographic blind spots**
- Europe: 321 missed (33.8% of misses) vs 215 matched (27.2% of matches) — scanner under-indexes Europe by ~7pp
- Top missed European countries: France (49), Germany (47), UK (45), Spain (31), Netherlands (29), Italy (19), Poland (14)
- South America: 83 missed — Brazil (48), Argentina (12) are major gaps
- Middle East: 44 missed — Saudi Arabia (20), UAE (12). Many are JVs with national oil companies.
- Asia: 102 missed — China (22), India (17), Japan (15), South Korea (14)
- Non-English language sources are a systemic weakness. Deals only covered in local-language press are invisible.

**Gap 4: Industry groups the scanner under-covers**
- Commercial Services (133 missed): environmental services, construction & engineering, logistics — all PG-relevant
- Consumer Non-Durables (62 missed): food/beverage/agri processing companies with heavy industrial assets
- Energy Equipment (18 missed): turbine, transformer, and compressor manufacturers
- Agriculture (14 missed): fertilizer, crop science, farm equipment

**Gap 5: Deal status bias**
- 97% of missed deals are "Completed" (922/950) — the scanner over-indexes on announced/rumored deals
- Only 25 missed deals were "Announced/In Progress"
- The scanner is good at catching deals in the news cycle but misses deals that closed quietly

**Actionable improvements for the scanner:**
1. Add JV-specific Tier 1 queries by region (e.g., "oil gas joint venture Europe 2025", "mining joint venture South America")
2. Add queries for under-covered sectors: environmental services, construction engineering, logistics, energy equipment, food processing
3. Add region-specific queries: France, Germany, Brazil, Saudi Arabia, India, Japan, South Korea
4. For historical scans, add year-anchored queries (e.g., "industrial acquisition completed 2022")
5. Search for completed/closed deals explicitly (e.g., "deal closed" "acquisition completed" "transaction completed")
6. Consider non-English search queries for major markets (Brazil, France, Germany, Japan)

---

## QUALITY METRICS

**Baseline metrics from first comprehensive cross-reference (1,475 scanner deals vs 1,741 Pitchbook deals):**
- Scanner deal quality: 96.6% high quality (well-formed, verifiable deals)
- Malformed deal type rate: 4.8% (71/1,475) - all slug-format bugs
- Source validation pass rate (first attempt): 27.9%
- Source validation pass rate (after re-sourcing): ~85%
- Pitchbook overlap: 791 of 1,741 Pitchbook deals matched by scanner (45%)
- Pitchbook missed: 950 of 1,741 Pitchbook deals NOT found by scanner (55%)
- Scanner unique finds: 760 of 1,475 scanner deals NOT in Pitchbook (52%)
- JV miss rate: 73% (326/446 Pitchbook JVs missed) — worst deal type
- M&A miss rate: 48% (624/1,291 Pitchbook M&A deals missed) — baseline
- Oldest-year miss rate: 70% (2021) vs best year: 44% (2024)

---

## SCAN RUN LOG

| Date | Period | Companies | Tier1 | Tier2 AB | Tier2 CD | Tier3 Verified | New Deals | Excluded | Unverified | Notes |
|------|--------|-----------|-------|----------|----------|----------------|-----------|----------|------------|-------|
