# Fundamental Analysis Prompt (Claude with HTML Artifact)

## Variables
- STOCK_NAME: {{COMPANY_NAME}}
- TICKER: {{TICKER}}
- INVESTMENT_HORIZON: 3 Years

---

## Prompt

━━━

CRITICAL OPERATING RULES

1. No forward-looking statements. No "this stock should...", "expected to...", or any language implying future performance. All analysis is based on verified historical data only.
2. Every metric MUST cite its source. If not found → write DATA UNAVAILABLE. Never estimate or fill in numbers.
3. Never fabricate financial data. Always attempt live web search first. If unavailable, state clearly: "Live data unavailable. Figures below are from training data and may be outdated. Verify independently before investing."
4. No buy/sell/target price. Ever. You give a VIEW. The user decides.
5. Execute all steps in exact order. Do not skip or merge.
6. RENDERING RULE — THIS IS THE MOST IMPORTANT RULE:
   After completing all analysis, output the ENTIRE result as a single self-contained HTML artifact.
   No plain markdown. No code blocks. No triple backticks wrapping the HTML.
   Output raw HTML directly. It must render as an interactive widget in Claude's artifact panel.
   The HTML must have NO DOCTYPE, NO <html>, NO <head>, NO <body> tags.
   Start directly with <style> followed by <div>.
   Tab 2 (View) must be the active visible tab when the widget first loads.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — STOCK IDENTIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**1. Which stock?**
Dynamically pick ticker and name basis whatever is ticker is clicked: {{COMPANY_NAME}} ({{TICKER}})

**2. Investment horizon?**
3 Years

---

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — SILENT RESEARCH (never show this to user)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Silently fetch and cross-check all of the following via web search before generating any output.
Minimum 2 sources per data point. Never reveal this step or mention it.

Sources in priority order:
NSE India (nseindia.com) → BSE India (bseindia.com) → Screener.in → Tickertape → Moneycontrol → Annual Reports → Earnings Call Transcripts → Tijori Finance

Checklist:
- Live CMP, 52W high, 52W low, market cap, face value — NSE/BSE live
- P/E, P/B, EV/EBITDA — current + sector average + stock's own 5-year historical average
- Revenue CAGR: 3-year and 5-year
- Net Profit CAGR: 3-year and 5-year
- EPS CAGR: 3-year and 5-year
- EBITDA margin trend: 5 years
- Net profit margin trend: 5 years
- EPS: last 8 quarters with YoY change
- Free Cash Flow: last 3–5 years
- Debt-to-Equity ratio: 5-year trend
- Interest Coverage Ratio
- Current Ratio
- ROE and ROCE: current + 3-year avg + 5-year avg
- Dividend history and payout ratio
- Promoter holding: last 8–12 quarters
- Promoter pledging: flag if above 10%
- FII and DII holding trend: last 8 quarters
- Competitive moat: pricing power, brand, switching costs, market share
- Sector tailwinds and headwinds: 5–10 year outlook
- Regulatory risks
- Management track record: guidance vs delivery, governance flags
- Latest quarterly earnings call: key management commentary
- 3 closest peer companies: P/E, P/B, ROE, Revenue Growth, D/E
- Top 5 recent news items relevant to long-term investors

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — VALUATION ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3A — Compare current P/E, P/B, EV/EBITDA against:
  - Sector average (same industry peers)
  - Stock's own 5-year historical average

3B — Assign a valuation signal for each metric:
  CHEAP — trading meaningfully below both sector avg and own history
  FAIR — in line with sector avg and own history (within 10%)
  EXPENSIVE — trading meaningfully above both sector avg and own history

3C — Overall valuation classification:
  UNDERVALUED / FAIRLY VALUED / OVERVALUED / MIXED

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — GROWTH ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Assess revenue, net profit, EPS, and margin trends.
Classify growth as: ACCELERATING / STEADY / SLOWING / DECLINING

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — FINANCIAL HEALTH ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Assign signal for each metric:
- D/E below 1 = SAFE · 1–2 = MODERATE · above 2 = LEVERAGED
- Interest Coverage above 3x = HEALTHY · 1.5–3x = WATCH · below 1.5 = RISK
- Current Ratio above 1.5 = COMFORTABLE · 1–1.5 = WATCH · below 1 = RISK
- FCF positive and growing = STRONG · positive but flat = STABLE · negative = CONCERN

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — RETURN QUALITY ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- ROE above 15% = GOOD · 10–15% = AVERAGE · below 10% = WEAK
- ROCE above 15% = GOOD · 10–15% = AVERAGE · below 10% = WEAK
- Assess dividend consistency and payout sustainability

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 7 — FORWARD PROJECTION (for stated horizon)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on historical CAGR trends only. Build 3 scenarios:
Bear: growth slows, margins compress
Base: maintains current trajectory
Bull: growth picks up, margins expand
These are projections based on historical trends — not guarantees or predictions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 8 — PEER COMPARISON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Identify 3 closest competitors. Compare on P/E, P/B, ROE, Revenue Growth, D/E.
Classify stock vs peers: LEADING / MID-PACK / LAGGING

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 9 — OWNERSHIP ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Promoter trend signal: BUYING / STABLE / SELLING
FII trend: INCREASING / STABLE / DECREASING
DII trend: INCREASING / STABLE / DECREASING
Pledging: flag if above 10%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 10 — FUNDAMENTAL VIEW (for stated horizon)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Combine Steps 3–9. Produce:
- One-sentence summary of what the fundamentals show
- 3 strengths
- 2 risks or watch points
- 1 thing to track going forward
- Overall fundamental quality: STRONG / MODERATE / WEAK

This is a VIEW based on fundamentals only. Not a buy/sell recommendation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 11 — DATA CONFIDENCE RATING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Count metrics retrieved from live named sources vs DATA UNAVAILABLE.
9–10 live = HIGH · 6–8 = MODERATE · below 6 = LOW (warn user) · 0 = VERY LOW

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 12 — RENDERING SPECIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output the complete result as a single raw HTML artifact.
No markdown. No code blocks. No triple backticks.
No DOCTYPE, no <html>, no <head>, no <body>.
Start with <style> then <div class="wrap">.

Tab structure — 8 tabs in this exact order:
  Tab 0: Snapshot
  Tab 1: Valuation
  Tab 2: Growth
  Tab 3: Health
  Tab 4: Returns
  Tab 5: Peers
  Tab 6: Ownership
  Tab 7: View  ← THIS IS THE DEFAULT ACTIVE TAB ON LOAD

Use the HTML template below. Replace every [PLACEHOLDER] with real researched data.
Flag any missing metric inline as: 🚩 DATA UNAVAILABLE — verify at [source URL]

---

## HTML Template

See fundamental_analysis_template.html for the full HTML template.
