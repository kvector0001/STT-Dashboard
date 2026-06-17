# Fundamental Analysis Prompt (ChatGPT Version)

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
6. Format output as clean Markdown with tables. Use clear headers for each section.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOCK IDENTIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Stock:** {{COMPANY_NAME}} ({{TICKER}})
**Investment horizon:** 3 Years

---

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCH CHECKLIST (perform silently)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Search and cross-check from: NSE India, BSE India, Screener.in, Tickertape, Moneycontrol, Annual Reports, Earnings Call Transcripts, Tijori Finance

Data points to gather:
- Live CMP, 52W high/low, market cap, face value
- P/E, P/B, EV/EBITDA — current + sector avg + 5-year historical avg
- Revenue/Net Profit/EPS CAGR: 3-year and 5-year
- EBITDA margin and Net profit margin trends
- EPS: last 8 quarters with YoY change
- Free Cash Flow: last 3–5 years
- Debt-to-Equity, Interest Coverage, Current Ratio
- ROE and ROCE: current + 3-year avg + 5-year avg
- Dividend history and payout ratio
- Promoter/FII/DII holding trends
- Promoter pledging (flag if >10%)
- Competitive moat and sector outlook
- Management track record
- Latest earnings call highlights
- 3 peer companies comparison
- Top 5 recent news items

---

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 📊 SNAPSHOT
| Metric | Value | Source |
|--------|-------|--------|
| Company | ... | |
| Ticker | ... | |
| Sector/Industry | ... | |
| CMP | ₹... | NSE |
| 52W High/Low | ₹.../₹... | NSE |
| Market Cap | ₹... Cr | BSE |
| What it does | ... | |
| What makes it different | ... | |

---

## 💰 VALUATION

| Metric | Current | Sector Avg | Stock 5Y Avg | Signal |
|--------|---------|------------|--------------|--------|
| P/E | ...x | ...x | ...x | CHEAP/FAIR/EXPENSIVE |
| P/B | ...x | ...x | ...x | CHEAP/FAIR/EXPENSIVE |
| EV/EBITDA | ...x | ...x | ...x | CHEAP/FAIR/EXPENSIVE |

**Overall:** UNDERVALUED / FAIRLY VALUED / OVERVALUED / MIXED

---

## 📈 GROWTH

| Metric | 3Y CAGR | 5Y CAGR | Trend |
|--------|---------|---------|-------|
| Revenue | ...% | ...% | 📈/➡️/📉 |
| Net Profit | ...% | ...% | 📈/➡️/📉 |
| EPS | ...% | ...% | 📈/➡️/📉 |
| EBITDA Margin | ...% | ...% | 📈/➡️/📉 |
| Net Profit Margin | ...% | ...% | 📈/➡️/📉 |

**EPS Last 8 Quarters:**
| Q1FY25 | Q2FY25 | Q3FY25 | Q4FY25 | Q1FY26 | Q2FY26 | Q3FY26 | Q4FY26 |
|--------|--------|--------|--------|--------|--------|--------|--------|
| ₹... | ₹... | ₹... | ₹... | ₹... | ₹... | ₹... | ₹... |

**Growth Classification:** ACCELERATING / STEADY / SLOWING / DECLINING

---

## 🏦 FINANCIAL HEALTH

| Metric | Value | 5Y Trend | Signal |
|--------|-------|----------|--------|
| Debt/Equity | ... | ↓/→/↑ | SAFE/MODERATE/LEVERAGED |
| Interest Coverage | ...x | ↓/→/↑ | HEALTHY/WATCH/RISK |
| Current Ratio | ... | ↓/→/↑ | COMFORTABLE/WATCH/RISK |
| Free Cash Flow | ₹... Cr | ↓/→/↑ | STRONG/STABLE/CONCERN |

**Forward Projections (3 Year):**
| Scenario | Assumption | Est. Revenue | Est. Net Profit | Est. EPS |
|----------|------------|--------------|-----------------|----------|
| 🐢 Bear | Growth slows, margins compress | ₹... Cr | ₹... Cr | ₹... |
| 🚶 Base | Maintains current trajectory | ₹... Cr | ₹... Cr | ₹... |
| 🚀 Bull | Growth picks up, margins expand | ₹... Cr | ₹... Cr | ₹... |

---

## 📊 RETURNS

| Metric | Current | 3Y Avg | 5Y Avg | Signal |
|--------|---------|--------|--------|--------|
| ROE | ...% | ...% | ...% | GOOD/AVERAGE/WEAK |
| ROCE | ...% | ...% | ...% | GOOD/AVERAGE/WEAK |
| Dividend Yield | ...% | ...% | ...% | — |
| Dividend Payout | ...% | ...% | ...% | — |

---

## 👥 PEERS

| Company | P/E | P/B | ROE | Rev Growth | D/E | Edge |
|---------|-----|-----|-----|------------|-----|------|
| **[STOCK] ◀ you** | ... | ... | ...% | ...% | ... | ... |
| Peer 1 | ... | ... | ...% | ...% | ... | ... |
| Peer 2 | ... | ... | ...% | ...% | ... | ... |
| Peer 3 | ... | ... | ...% | ...% | ... | ... |

**Peer Standing:** LEADING / MID-PACK / LAGGING

---

## 🏢 OWNERSHIP

| Holder | Latest % | 8Q Trend | Signal |
|--------|----------|----------|--------|
| Promoter | ...% | ↑/→/↓ | BUYING/STABLE/SELLING |
| FII | ...% | ↑/→/↓ | INCREASING/STABLE/DECREASING |
| DII | ...% | ↑/→/↓ | INCREASING/STABLE/DECREASING |
| Promoter Pledging | ...% | — | OK/FLAG |

**Latest Earnings Call Highlights:**
- ...
- ...
- ...

**Management Tone:** CONFIDENT / CAUTIOUS / MIXED

---

## 🎯 VIEW

**Overall Fundamental Quality:** STRONG / MODERATE / WEAK

**Summary:** [One sentence on what the fundamentals show]

**✅ What Works:**
1. ...
2. ...
3. ...

**⚠️ What to Watch:**
1. ...
2. ...

**→ Track Going Forward:** ...

**Opportunities:**
- ...
- ...
- ...

**Risks:**
- ...
- ...
- ...

---

## 📊 DATA CONFIDENCE

- Live metrics retrieved: X of 12 key sections
- Sources used: ...
- Confidence: HIGH / MODERATE / LOW / VERY LOW

---

*This is a VIEW based on fundamentals only. Not a buy/sell recommendation. The decision is always yours. Verify all data at NSE/BSE/Screener.in before investing.*
