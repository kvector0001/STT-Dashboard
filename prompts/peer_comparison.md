# 👥 PEER VERDICT — {COMPANY}

## CRITICAL RULES (do not violate)
- Output ONLY two sections: "💎 Premium/Discount Verdict" and "🎯 Final Verdict".
- DO NOT output: snapshot, rank tables, qual pillar tables, scoring breakdowns,
  methodology notes, or any preamble.
- DO NOT explain what you are doing. No intros. No "Let me compile…".
  Start directly with the 💎 header.
- Premium/Discount section = NUMBERED LIST (#1 to #6), NOT bullets, NOT a table.
- Each numbered line = ONE sentence with: company @ P/E — evidence-based reason —
  % over/undervaluation — VERDICT IN CAPS — 1 source link.
- Final Verdict = exactly 5 numbered points in the order shown in the example.
- Total output ≤ 22 lines.

## DEEP QUALITATIVE ANALYSIS (INTERNAL — EXECUTE BEFORE VERDICT)

### PHASE 1: TARGET COMPANY DEEP DIVE (mandatory before peer selection)

Before making ANY valuation judgment, conduct exhaustive qualitative research on the target company:

#### A. PRODUCT PROFILE DEPTH
- Product complexity and differentiation (commodity vs specialty vs mission-critical)
- Certifications held (ISO, industry-specific, customer audits)
- Use cases and criticality to customer operations
- Switching costs for customers (technical, operational, financial)
- Product lifecycle and obsolescence risk

#### B. MANAGEMENT QUALITY & TRACK RECORD
- Promoter shareholding trend (stable / increasing / diluting)
- Capital allocation history (capex discipline, M&A record, dividend consistency)
- Execution track record (promised vs delivered capacity expansions, guidance accuracy)
- Conference call tone and transparency (specific vs vague, accountability)
- Related-party transactions and governance red flags

#### C. CUSTOMER & MARKET PROFILE
- Export share and geographic diversification
- Customer concentration risk (top 5/10 customers as % of revenue)
- Industries served and their cyclicality
- Contract duration and revenue visibility
- Customer creditworthiness

#### D. ENTRY BARRIERS & MOAT STRENGTH
- Technical complexity and manufacturing know-how
- Certification requirements (time and cost to replicate)
- Customer qualification timelines (switching inertia)
- Scale advantages (fixed cost leverage, procurement power)
- Brand equity in B2B context

#### E. EARNINGS QUALITY & SUSTAINABILITY
- Revenue growth consistency (lumpiness vs steady)
- Margin stability across cycles
- Cash conversion (CFO/EBITDA ratio)
- Working capital intensity
- Dependence on external factors (commodity prices, government orders, forex)

### PHASE 2: PEER SELECTION (quality over similarity)

DO NOT select peers mechanically by sector/industry tags.

- Prioritize business model similarity (not just "steel tubes")
- Validate peer quality:
  - Check recent governance issues, regulatory actions
  - Check cyclicality and order book visibility
  - Check margin volatility and execution consistency
  - Check balance sheet stress (debt/equity, interest coverage)
- If serious issues exist in a commonly cited "peer", DO NOT include them
- Prefer 5 high-quality peers over 6 weak comparables

### PHASE 3: VALUATION JUDGMENT (only after Phases 1 & 2)

For EACH company (target + all peers):

- Estimate fair P/E range based on:
  - Growth (3Y CAGR, forward guidance credibility)
  - ROCE/ROE (capital efficiency)
  - Margins (level + stability)
  - Business quality score (from qualitative analysis above)
  - Cyclicality and earnings visibility

- Calculate % overvaluation / undervaluation:
  % = (Current P/E - Fair P/E Midpoint) / Current P/E × 100

- DO NOT assume low P/E = undervalued
- Penalize heavily for:
  - Weak governance or accounting concerns
  - High cyclicality without offsetting moat
  - Poor earnings quality (lumpy revenue, weak cash conversion)
  - Customer/geographic concentration
  - Deteriorating trends (margin compression, order book decline)

## METHOD (internal — never show this in output)

- Score each peer on Quant (60%) + Qual (40%) where Qual = Moat + Customer
  stickiness + Brand + Pricing power + Earnings quality.
- Rank #1 to #6 by blended score (best → worst).
- Each verdict line MUST cite specific evidence: certifications, customer
  concentration %, export %, contract value, conf call quote, AR disclosure, or news source.
  NO generic adjectives.
- Verdict word per line: JUSTIFIED / PARTIALLY JUSTIFIED / NOT JUSTIFIED.
- Numbers from Screener, BSE/NSE, AR, conf calls. Mark "NV" if unverified.
  No fabrication.

## TWO LOCKED FORMAT RULES (FIX v6)

### FIX 1 — Best peer to BUY (actionable, not descriptive)
Format: **Best peer to BUY NOW**: {Name} @ ₹{CMP} — entry trigger: {price/event}
— allocation: {how to deploy proceeds}.

### FIX 2 — Action NOW vs REVERSE trigger (unambiguous)
Format:
**ACTION NOW**: [HOLD / ACCUMULATE / SWITCH OUT NOW → {Peer}]
**REVERSE ACTION (switch back to {COMPANY}) when**:
  (a) [measurable trigger 1] AND/OR
  (b) [measurable trigger 2] AND/OR
  (c) [measurable trigger 3]

Triggers must be numbers, events, or filing disclosures — not adjectives.
Use AND / OR explicitly.

## OUTPUT FORMAT (copy exactly)

💎 Premium/Discount Verdict

**#1 ★ {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued vs fair P/E]. **VERDICT**. [source]  
**#2 {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued]. **VERDICT**. [source]  
**#3 {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued]. **VERDICT**. [source]  
**#4 {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued]. **VERDICT**. [source]  
**#5 {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued]. **VERDICT**. [source]  
**#6 {Company} @ Xx P/E** — [specific evidence] — [~XX% over/undervalued]. **VERDICT**. [source]  

🎯 Final Verdict

1. **Quant Rank**: #X | **Qual Rank**: #Y | **Blended Rank**: **#Z of 6**  
2. **Why ranks differ**: [one sentence on quant-vs-qual divergence]  
3. **Best peer to BUY NOW**: {Name} @ ₹{CMP} — entry trigger: {price/event} —  
   allocation: {how to deploy proceeds}  
4. **Peer to completely Avoid**: {Name} @ Xx  
5. **Action for {COMPANY}**: **ACTION NOW** = [HOLD/ACCUMULATE/SWITCH OUT NOW → {Peer}]  
   | **REVERSE ACTION when**: (a) trigger AND/OR (b) trigger AND/OR (c) trigger  

## END OF PROMPT
Now run for: {COMPANY} ({TICKER}). Output ONLY the two sections.