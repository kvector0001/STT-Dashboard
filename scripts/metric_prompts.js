// ══════════════════════════════════════════════════════════════════════════
// METRIC DEEP DIVE PROMPTS
// ══════════════════════════════════════════════════════════════════════════

function getMetricPrompt(metricType, ticker, companyName, stock) {
  const s = stock || (typeof allStocks !== 'undefined' ? allStocks.find(x => x.ticker === ticker) : {}) || {};
  const fmt = (v, d=1) => v != null ? v.toLocaleString('en-IN', {minimumFractionDigits: d, maximumFractionDigits: d}) : '—';
  
  const metricsSnapshot = `
Current Metrics for ${companyName} (${ticker}):
- Market Cap: ₹${fmt(s.mcap_cr,0)}Cr | P/E: ${fmt(s.pe,1)} | P/B: ${fmt(s.pb,2)} | EV/EBITDA: ${fmt(s.ev_ebitda,1)}
- ROE: ${fmt(s.roe,1)}% | ROCE: ${fmt(s.roce,1)}% | ROA: ${fmt(s.roa,1)}%
- Debt/Equity: ${fmt(s.debt_to_equity,2)} | EPS: ₹${fmt(s.eps,2)} | Book Value: ₹${fmt(s.book_value,2)}
- Gross Margin: ${fmt(s.gross_margin,1)}% | EBITDA Margin: ${fmt(s.ebitda_margin,1)}% | Operating Margin: ${fmt(s.operating_margin,1)}% | Net Margin: ${fmt(s.profit_margin,1)}%
- PAT CAGR: ${fmt(s.pat_cagr,1)}% | Revenue CAGR: ${fmt(s.rev_cagr,1)}% | Dividend Yield: ${fmt(s.div_yield,2)}%
- Promoter Holding: ${fmt(s.promoter_holding,1)}% | 1Y Return: ${fmt(s.ret_1y,1)}% | 3Y Return: ${fmt(s.ret_3y,1)}% | 5Y Return: ${fmt(s.ret_5y,1)}%
- OCF (3yr): ₹${fmt(s.opcf_3yr_avg ?? s.ocf_cr,0)}Cr | FCF (3yr): ₹${fmt(s.fcf_3yr_avg ?? s.fcf_cr,0)}Cr
- Moat: ${s.moat_class || '—'} | Sector: ${s.sector || '—'}`;

  const prompts = {
    // ═══════════════════════════════════════════════════════════════════════
    conviction: `# 🎯 CONVICTION SCORE DEEP DIVE — ${companyName} (${ticker})

## YOUR ROLE
Senior fundamental analyst with 20+ years in Indian equities. Think probabilistically. Be brutally honest.

## RULES
1. Cite sources (NSE, BSE, Screener.in). If unavailable → DATA UNAVAILABLE.
2. No buy/sell advice. Give CONVICTION SCORE with reasoning.
3. Be honest about weaknesses.

## CURRENT METRICS
${metricsSnapshot}

## ANALYSIS FRAMEWORK

### STEP 1 — BUSINESS QUALITY (Score /30)
- What does this company do? (2-line plain English)
- Good business to own for 5+ years?
- Competitive advantages (moat type, durability)
- Industry structure, pricing power

### STEP 2 — FINANCIAL STRENGTH (Score /25)
- Balance sheet (D/E, interest coverage)
- Cash flow generation (OCF trend, FCF yield)
- Capital allocation history
- Working capital efficiency

### STEP 3 — GROWTH TRAJECTORY (Score /20)
- Revenue CAGR (3Y, 5Y) — accelerating/slowing?
- PAT vs Revenue CAGR — operating leverage?
- Margin trends
- Growth runway

### STEP 4 — VALUATION REALITY (Score /15)
- P/E vs sector avg vs own history
- P/B vs ROE — justified?
- Pricing in perfection?

### STEP 5 — MANAGEMENT (Score /10)
- Promoter holding trend
- Pledging (>10% red flag)
- Capital allocation track record
- Guidance vs delivery

## OUTPUT

### CONVICTION SCORECARD
| Dimension | Score | Max |
|-----------|-------|-----|
| Business Quality | /30 | 30 |
| Financial Strength | /25 | 25 |
| Growth Trajectory | /20 | 20 |
| Valuation Reality | /15 | 15 |
| Management | /10 | 10 |
| **TOTAL** | **/100** | 100 |

**Conviction Score: [X]/100**
80-100=HIGH | 60-79=MODERATE | 40-59=LOW | <40=AVOID

**Top 3 Drivers:** 1. ... 2. ... 3. ...
**Top 3 Killers:** 1. ... 2. ... 3. ...`,

    // ═══════════════════════════════════════════════════════════════════════
    moat: `# 🛡️ ECONOMIC MOAT ANALYSIS — ${companyName} (${ticker})

## YOUR ROLE
Expert in competitive strategy. Morningstar methodology + Buffett principles.

## CURRENT METRICS
${metricsSnapshot}

## THE 7 MOAT TYPES

| Moat Type | What it is | Indian Examples | Durability |
|-----------|------------|-----------------|------------|
| **IP/Patents** | Patents, molecules, process know-how | NEULANDLAB, SUVEN, BIOCON | High if cliff far |
| **Brand** | Pricing power from trust | 3MINDIA, WHIRLPOOL, HONAUT | Very high |
| **Regulatory** | Licences, BIS/QCO barriers | AEROFLEX, defence PSUs | Very high while policy holds |
| **Switching Costs** | Painful to leave | SANSERA (OEM), RATEGAIN | High |
| **Network Effects** | Value grows with users | MAPMYINDIA, exchanges | Highest |
| **Cost Advantage** | Structural low-cost | GMDCLTD (captive), GESHIP | Medium-High |
| **Efficient Scale** | Niche supports 1-2 players | NESCO (Bombay expo) | High but caps growth |

## FOR ${companyName}:

### Evaluate EACH moat type:
1. Does company have it? (YES/NO/PARTIAL)
2. Evidence?
3. Durability (years)?
4. What could erode it?

### MOAT WIDTH
- **WIDE:** Multiple strong advantages, 20+ years
- **NARROW:** Some advantages, 5-10 years
- **NONE:** Easily replicable

### PEER COMPARISON
| Company | Primary Moat | Width | Differentiator |
|---------|--------------|-------|----------------|
| ${ticker} | | | |
| Peer 1 | | | |
| Peer 2 | | | |

### VERDICT
**Moat Width:** [WIDE/NARROW/NONE]
**Primary Moat:** [Which of 7]
**Durability:** [X years]
**Biggest Threat:**`,

    // ═══════════════════════════════════════════════════════════════════════
    pe: `# 📊 P/E RATIO DEEP DIVE — ${companyName} (${ticker})

## CURRENT
- P/E: ${fmt(s.pe,1)} | EPS: ₹${fmt(s.eps,2)} | Price: ₹${fmt(s.ltp,2)}

## ANALYSIS

### 1. P/E CONTEXT
| Timeframe | P/E | Source |
|-----------|-----|--------|
| Current | ${fmt(s.pe,1)} | |
| 1 Year Ago | | |
| 3 Year Avg | | |
| 5 Year Avg | | |
| Sector Median | | |
| Nifty 50 | | |

### 2. INTERPRETATION
- vs own history: CHEAP/FAIR/EXPENSIVE?
- vs sector: CHEAP/FAIR/EXPENSIVE?
- What P/E deserved?

### 3. EARNINGS QUALITY
- Sustainable or one-time?
- EPS trend (8 quarters)
- Earnings vs Cash Flow?

### 4. FORWARD P/E
- Consensus EPS next year:
- Forward P/E:
- Growth priced in?

### 5. VERDICT
**P/E Signal:** [UNDERVALUED/FAIR/OVERVALUED]`,

    // ═══════════════════════════════════════════════════════════════════════
    roe: `# 📈 ROE ANALYSIS — ${companyName} (${ticker})

## CURRENT
ROE: ${fmt(s.roe,1)}% | ROA: ${fmt(s.roa,1)}% | ROCE: ${fmt(s.roce,1)}% | D/E: ${fmt(s.debt_to_equity,2)}

## ANALYSIS

### 1. DUPONT BREAKDOWN
ROE = Margin × Turnover × Leverage
| Component | Value | Meaning |
|-----------|-------|---------|
| Net Margin | % | Pricing power |
| Asset Turnover | x | Efficiency |
| Equity Multiplier | x | Leverage |

### 2. QUALITY CHECK
- High ROE from profitability or leverage?
- ROE >> ROCE? (debt inflating)
- Sustainable?

### 3. TREND (5Y)
| Year | ROE % |
|------|-------|
| Current | ${fmt(s.roe,1)}% |
| FY-1 | |
| FY-2 | |
| FY-3 | |

### 4. PEER COMPARISON
| Company | ROE | ROCE | D/E |
|---------|-----|------|-----|
| ${ticker} | ${fmt(s.roe,1)}% | ${fmt(s.roce,1)}% | ${fmt(s.debt_to_equity,2)} |
| Peer 1 | | | |
| Peer 2 | | | |

### 5. SIGNAL
>20% low debt = EXCELLENT | 15-20% = GOOD | 10-15% = AVG | <10% = WEAK

**ROE Quality:** [EXCELLENT/GOOD/AVERAGE/WEAK]`,

    // ═══════════════════════════════════════════════════════════════════════
    de: `# 💳 DEBT ANALYSIS — ${companyName} (${ticker})

## CURRENT: D/E = ${fmt(s.debt_to_equity,2)}

## ANALYSIS

### 1. DEBT STRUCTURE
| Metric | Value |
|--------|-------|
| Total Debt | ₹ Cr |
| Long-term | ₹ Cr |
| Short-term | ₹ Cr |
| Cash | ₹ Cr |
| Net Debt | ₹ Cr |
| Net Debt/EBITDA | x |
| Interest Coverage | x |

### 2. TREND (5Y)
| Year | D/E | Int Coverage |
|------|-----|--------------|
| Current | ${fmt(s.debt_to_equity,2)} | |
| FY-1 | | |
| FY-2 | | |

Trend: INCREASING/STABLE/DECREASING?

### 3. QUALITY
- Used for? (Capex/Acquisition/Working cap)
- Cost of debt?
- Maturity profile?

### 4. SAFETY
| Metric | Current | Safe | Status |
|--------|---------|------|--------|
| D/E | ${fmt(s.debt_to_equity,2)} | <1.0 | |
| Interest Coverage | | >3x | |
| Net Debt/EBITDA | | <3x | |

**Financial Health:** [SAFE/MODERATE/LEVERAGED/STRESSED]`,

    // ═══════════════════════════════════════════════════════════════════════
    peers: `# 👥 PEER COMPARISON — ${companyName} (${ticker})

## CURRENT
${metricsSnapshot}

## ANALYSIS

### 1. IDENTIFY 5 PEERS
1. [Peer] — why comparable
2. ...
3. ...
4. ...
5. ...

### 2. COMPARISON TABLE
| Metric | ${ticker} | Peer 1 | Peer 2 | Peer 3 | Sector |
|--------|---------|--------|--------|--------|--------|
| Mcap | | | | | |
| P/E | ${fmt(s.pe,1)} | | | | |
| P/B | ${fmt(s.pb,2)} | | | | |
| EV/EBITDA | ${fmt(s.ev_ebitda,1)} | | | | |
| ROE | ${fmt(s.roe,1)}% | | | | |
| EBITDA Margin | ${fmt(s.ebitda_margin,1)}% | | | | |
| D/E | ${fmt(s.debt_to_equity,2)} | | | | |

### 3. RELATIVE VALUE
Premium/Discount vs peers? Justified?

### 4. RANK
| Dimension | Rank /5 |
|-----------|---------|
| Market Share | |
| Growth | |
| Profitability | |
| Balance Sheet | |

**Peer Rank:** #X of Y
**Relative Value:** [UNDERVALUED/FAIR/OVERVALUED]`,

    // ═══════════════════════════════════════════════════════════════════════
    management: `# 👔 MANAGEMENT TRUST — ${companyName} (${ticker})

## ANALYSIS

### 1. PROMOTER PROFILE
- Who? Background? Tenure?

### 2. OWNERSHIP
| Metric | Value | Signal |
|--------|-------|--------|
| Promoter % | ${fmt(s.promoter_holding,1)}% | |
| Trend 3Y | | ↑/→/↓ |
| Pledging | | <10%=OK |
| Insider buying | | |

### 3. CAPITAL ALLOCATION (5Y)
- Dividends consistent?
- Buybacks at fair prices?
- Acquisitions value-creating?
- Capex disciplined?

### 4. GOVERNANCE
| Item | Status | Red Flag? |
|------|--------|-----------|
| Related party | | |
| Board independence | | |
| Auditor changes | | |
| SEBI penalties | | |

### 5. GUIDANCE vs DELIVERY
- Promised 3Y ago:
- Delivered:
- Track: BEATS/MEETS/MISSES?

### 6. TRUST SCORE
| Dimension | /10 |
|-----------|-----|
| Competence | |
| Integrity | |
| Alignment | |
| Transparency | |
| **TOTAL** | /40 |

**Trust Level:** [HIGH/MODERATE/LOW/AVOID]`,

    // ═══════════════════════════════════════════════════════════════════════
    redflags: `# 🚩 RED FLAGS SCAN — ${companyName} (${ticker})

## CURRENT
${metricsSnapshot}

## CHECKLIST

### 1. ACCOUNTING
| Check | Status |
|-------|--------|
| Revenue ↑ but OCF ↓ | |
| Receivables > Revenue growth | |
| Inventory buildup | |
| Policy changes | |
| High other income | |
| Auditor changes | |

### 2. GOVERNANCE
| Check | Status |
|-------|--------|
| Pledging >10% | |
| Promoter selling | |
| Related party issues | |
| Management exits | |
| SEBI penalties | |

### 3. FINANCIAL
| Check | Status |
|-------|--------|
| Debt > EBITDA growth | |
| Interest coverage <1.5x | |
| Negative FCF 3+ years | |
| Working capital stress | |

### 4. BUSINESS
| Check | Status |
|-------|--------|
| Customer concentration >30% | |
| Patent expiry | |
| Tech disruption | |
| Key person dependency | |

**Critical Flags:**
**Amber Flags:**
**Risk Level:** [LOW/MODERATE/HIGH/VERY HIGH]
**Skip?** [YES/NO]`,

    // ═══════════════════════════════════════════════════════════════════════
    margins: `# 📊 MARGIN ANALYSIS — ${companyName} (${ticker})

## CURRENT
Gross: ${fmt(s.gross_margin,1)}% | EBITDA: ${fmt(s.ebitda_margin,1)}% | Op: ${fmt(s.operating_margin,1)}% | Net: ${fmt(s.profit_margin,1)}%

## ANALYSIS

### 1. TREND (5Y)
| Year | Gross | EBITDA | Op | Net |
|------|-------|--------|-----|-----|
| Current | ${fmt(s.gross_margin,1)}% | ${fmt(s.ebitda_margin,1)}% | ${fmt(s.operating_margin,1)}% | ${fmt(s.profit_margin,1)}% |
| FY-1 | | | | |
| FY-2 | | | | |
| Sector | | | | |

### 2. DRIVERS
- Gross margin driver?
- Operating margin driver?
- What's compressing?

### 3. PEER COMPARISON
| Company | Gross | EBITDA | Net |
|---------|-------|--------|-----|
| ${ticker} | ${fmt(s.gross_margin,1)}% | ${fmt(s.ebitda_margin,1)}% | ${fmt(s.profit_margin,1)}% |
| Peer 1 | | | |
| Peer 2 | | | |

**Margin Quality:** [EXCELLENT/GOOD/AVERAGE/WEAK]
**Trend:** [EXPANDING/STABLE/COMPRESSING]`,

    // ═══════════════════════════════════════════════════════════════════════
    returns: `# 📈 RETURNS ANALYSIS — ${companyName} (${ticker})

## CURRENT
1Y: ${fmt(s.ret_1y,1)}% | 3Y: ${fmt(s.ret_3y,1)}% | 5Y: ${fmt(s.ret_5y,1)}%

## ANALYSIS

### 1. vs BENCHMARKS
| Period | ${ticker} | Nifty 50 | Sector | Alpha |
|--------|---------|----------|--------|-------|
| 1Y | ${fmt(s.ret_1y,1)}% | | | |
| 3Y | ${fmt(s.ret_3y,1)}% | | | |
| 5Y | ${fmt(s.ret_5y,1)}% | | | |

### 2. ATTRIBUTION
- Earnings growth: %
- P/E expansion: %
- Dividends: %

### 3. DRAWDOWNS
| Event | Max DD | Recovery |
|-------|--------|----------|
| COVID 2020 | | |
| Biggest | | |

### 4. FUTURE (3Y)
- Bear:
- Base:
- Bull:

**Alpha:** [STRONG/MODERATE/WEAK]`,

    // ═══════════════════════════════════════════════════════════════════════
    cashflow: `# 💰 CASH FLOW — ${companyName} (${ticker})

## CURRENT
OCF (3yr): ₹${fmt(s.opcf_3yr_avg ?? s.ocf_cr,0)}Cr | FCF (3yr): ₹${fmt(s.fcf_3yr_avg ?? s.fcf_cr,0)}Cr | Mcap: ₹${fmt(s.mcap_cr,0)}Cr

## ANALYSIS

### 1. TREND (5Y)
| Year | OCF | FCF | Capex | FCF Yield |
|------|-----|-----|-------|-----------|
| Current | | | | |
| FY-1 | | | | |
| FY-2 | | | | |

### 2. QUALITY
- OCF vs Net Profit (≥1x?)
- Consistent conversion?
- Working capital trends?

### 3. FCF USAGE
- Dividends
- Debt repaid
- Capex
- Acquisitions

### 4. FCF YIELD
>5% = ATTRACTIVE | 3-5% = FAIR | <3% = EXPENSIVE

**Cash Generation:** [STRONG/MODERATE/WEAK]`,

    // ═══════════════════════════════════════════════════════════════════════
    mcap: `# 📊 MARKET CAP ANALYSIS — ${companyName} (${ticker})

## CURRENT
Market Cap: ₹${fmt(s.mcap_cr,0)}Cr | LTP: ₹${fmt(s.ltp,2)}

## ANALYSIS

### 1. SIZE CLASSIFICATION
- Large Cap (>₹50,000 Cr)
- Mid Cap (₹15,000-50,000 Cr)
- Small Cap (<₹15,000 Cr)

Current: [LARGE/MID/SMALL CAP]

### 2. MCAP vs FUNDAMENTALS
| Metric | Value |
|--------|-------|
| Mcap/Sales | x |
| Mcap/PAT (P/E) | ${fmt(s.pe,1)}x |
| Mcap/Book (P/B) | ${fmt(s.pb,2)}x |
| Mcap/FCF | x |

### 3. MCAP TREND
| Period | Mcap | Change |
|--------|------|--------|
| Current | ₹${fmt(s.mcap_cr,0)}Cr | |
| 1Y Ago | | |
| 3Y Ago | | |
| 5Y Ago | | |

### 4. PEER COMPARISON
| Company | Mcap | P/E | Growth |
|---------|------|-----|--------|
| ${ticker} | ₹${fmt(s.mcap_cr,0)}Cr | ${fmt(s.pe,1)} | |
| Peer 1 | | | |
| Peer 2 | | | |

**Size Signal:** Room to grow or already large?`,

    // ═══════════════════════════════════════════════════════════════════════
    promoter: `# 👥 PROMOTER ANALYSIS — ${companyName} (${ticker})

## CURRENT
Promoter Holding: ${fmt(s.promoter_holding,1)}%

## ANALYSIS

### 1. HOLDING TREND (8 Quarters)
| Quarter | Promoter % | Change | Signal |
|---------|------------|--------|--------|
| Current | ${fmt(s.promoter_holding,1)}% | | |
| Q-1 | | | |
| Q-2 | | | |
| Q-3 | | | |
| Q-4 | | | |
| Q-5 | | | |
| Q-6 | | | |
| Q-7 | | | |

Trend: BUYING / STABLE / SELLING?

### 2. PLEDGING
| Metric | Value | Signal |
|--------|-------|--------|
| Pledged % | | <10% OK, >20% Red Flag |
| Trend | | |

### 3. WHO ARE PROMOTERS?
- Names and backgrounds
- Succession plan?
- Other interests?

### 4. FII/DII TREND
| Holder | Current | 1Y Ago | Trend |
|--------|---------|--------|-------|
| FII | | | |
| DII | | | |

**Promoter Signal:** [ALIGNED/NEUTRAL/CONCERNING]`
  };

  return prompts[metricType] || prompts.conviction;
}

// ── Open metric analysis with AI picker ────────────────────────────────────
function openMetricAnalysis(metricType, ticker, companyName, anchorEl) {
  const stock = (typeof allStocks !== 'undefined') ? allStocks.find(s => s.ticker === ticker) : null;
  const prompt = getMetricPrompt(metricType, ticker, companyName, stock);
  showAiPicker(anchorEl, prompt);
}
