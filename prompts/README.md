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

---

## How to Use

1. **In Dashboard:** Click company name in Deep Analysis tab → choose Claude or ChatGPT
2. **Manually:** Copy any `.md` file contents, replace `{{TICKER}}` and `{{COMPANY_NAME}}` with actual values

## Variables
- `{{TICKER}}` - NSE stock ticker (e.g., RELIANCE)
- `{{COMPANY_NAME}}` - Full company name (e.g., Reliance Industries Ltd)
- `{{KPI_LIST}}` - Bullet list of KPIs to track (for kpi_tracking.md)
