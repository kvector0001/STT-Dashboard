# 📋 Prompt Library

This folder contains all the AI analysis prompts used in the Portfolio Dashboard.

## Files

### 1. `catalyst_analysis_v2.md`
**Purpose:** Comprehensive catalyst analysis for identifying re-rating triggers  
**Best for:** Understanding what events could move the stock price  
**Horizon:** 6-24 months  
**Output:** Detailed catalyst table with probabilities and impact scores

### 2. `kpi_tracking.md`
**Purpose:** Track specific KPIs quarter-over-quarter  
**Best for:** Monitoring operational metrics you care about  
**Output:** Tables showing 6 quarters of data with trend analysis

### 3. `fundamental_analysis_claude.md`
**Purpose:** Deep fundamental analysis with HTML artifact  
**Best for:** Claude AI - generates interactive tabbed widget  
**Features:**
- 8 tabs: Snapshot, Valuation, Growth, Health, Returns, Peers, Ownership, View
- Dark mode support
- Data confidence rating
- No buy/sell recommendations (VIEW only)

### 4. `fundamental_analysis_chatgpt.md`
**Purpose:** Same analysis as above but in Markdown format  
**Best for:** ChatGPT (no artifact rendering)  
**Output:** Clean Markdown tables with all the same data

### 5. `fundamental_analysis_template.html`
**Purpose:** HTML template for Claude's artifact rendering  
**Usage:** Reference template for the interactive widget  
**Note:** This is the raw HTML structure used in the Claude prompt

### 6. `red_flags.md`
**Purpose:** Forensic red-flags scan (accounting, governance, financial, business)  
**Triggered by:** 🚩 Red Flags button on each ticker card  
**Output:** Scored summary table (/10), critical/amber/watchlist flags, evidence table

### 7. `peer_comparison.md`
**Purpose:** Compare the company vs its 5 closest listed peers and judge valuation  
**Triggered by:** 👥 Peer Comparison button on each ticker card  
**Output:** Scored summary table, peer metrics table, PEER RANK #X of 6, UNDER/FAIR/OVERVALUED verdict

### 8. `management_trust.md`
**Purpose:** Forensic management-credibility / trust assessment over a 5–10 year horizon  
**Triggered by:** 👔 Management Trust button on each ticker card  
**Output:** Scored summary table (/10), TRUST VERDICT (HIGH/MODERATE/LOW/AVOID)

### 9. `technical_trends.md`
**Purpose:** Medium-term (3–12 month) technical setup — covers BOTH bullish breakouts AND bearish breakdowns / loss of support  
**Triggered by:** 📈 Technical Trends button on each ticker card  
**Output:** Scored summary table (/10), key levels (breakout & breakdown triggers), trend signal and action

---

## How to Use

1. **In Dashboard:** Click company name in Deep Analysis tab → choose Claude or ChatGPT
2. **Manually:** Copy any `.md` file contents, replace `{{TICKER}}` and `{{COMPANY_NAME}}` with actual values

## Variables
- `{{TICKER}}` - NSE stock ticker (e.g., RELIANCE)
- `{{COMPANY_NAME}}` - Full company name (e.g., Reliance Industries Ltd)
- `{{SNAPSHOT}}` - Live data block (Mcap, P/E, ROE, margins, price/technical) injected by the dashboard for the deep-analysis prompts
- `{{KPI_LIST}}` - Bullet list of KPIs to track (for kpi_tracking.md)

> **Note:** The dashboard injects these variables dynamically from the card you click (ticker, company name, and live metrics from `stocks.json` + `prices.json`). The inline versions live in `getMetricPrompt()` in `index.html`; these `.md` files are the readable source of truth.
