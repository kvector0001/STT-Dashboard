---
mode: agent
description: Score any holdings missing Management Trust / Red Flags scores, then merge and rebuild reports.
---

# Score pending holdings (Management Trust + Red Flags)

Fill in the missing **Management Trust** and **Red Flags** scores for every holding
that does not yet have one. No API key is involved — you (the agent) do the scoring.

## Steps

1. Run `python scripts/score_companies.py pending` in the terminal to list which
   tickers are missing a Management Trust (MT) and/or Red Flags (RF) score. If it
   reports nothing pending, stop and say so.

2. For **each** pending ticker, read its row in `stocks.json` (fields: `name`,
   `sector`, `mcap_cr`, `roe`, `debt_to_equity`, `div_yield`, `pat_cagr`,
   `rev_cagr`, `ocf_cr`, `leadership`, `risks`). Use that data **plus your own
   verifiable public knowledge** of the company.

3. Score it following the two methodologies in `prompts/management_trust.md` and
   `prompts/red_flags.md`:
   - **Management Trust** — 5 pillars: `promoter_profile`, `ownership_behaviour`,
     `capital_allocation`, `governance`, `execution`. Each 1–10.
   - **Red Flags** — 4 categories: `accounting`, `governance`, `financial`,
     `business`. Each 0–10 where **10 = clean, 0–3 = serious red flags**.
   - Add `critical_flags` / `amber_flags` lists for Red Flags where warranted.

## Rules (important)

- **Do NOT fabricate.** Ground every sub-score in the stock's data or verifiable
  public information. If evidence is thin (new IPO, micro-cap, conflicting data),
  set `confidence` to `"Low"` and say so in the reasons/summary.
- For **ETFs**, set `"etf": true` in the block (the verdict becomes `N/A (ETF)`).
- You provide only the **sub-scores + one-line reasons + a `summary` + `confidence`**.
  Do **not** compute the overall score or verdict — the merge step does that from
  the weights, so everything stays internally consistent.
- Keep reasons concise (one line each).

## Output + merge

4. Write all results to `prompt_outputs/_scores_to_merge.json`, keyed by ticker,
   using this exact shape (omit a block if that score already exists):

```json
{
  "TICKER": {
    "mgmt_trust": {
      "confidence": "Moderate", "summary": "...", "etf": false,
      "pillars": {
        "promoter_profile":   {"score": 7, "reason": "..."},
        "ownership_behaviour":{"score": 7, "reason": "..."},
        "capital_allocation": {"score": 7, "reason": "..."},
        "governance":         {"score": 7, "reason": "..."},
        "execution":          {"score": 7, "reason": "..."}
      }
    },
    "red_flags": {
      "confidence": "Moderate", "summary": "...", "etf": false,
      "critical_flags": [], "amber_flags": [],
      "categories": {
        "accounting": {"score": 7, "reason": "..."},
        "governance": {"score": 7, "reason": "..."},
        "financial":  {"score": 7, "reason": "..."},
        "business":   {"score": 7, "reason": "..."}
      }
    }
  }
}
```

5. Run `python scripts/score_companies.py merge prompt_outputs/_scores_to_merge.json`.
   This recomputes overall scores + verdicts, writes `management_trust.json` and
   `red_flags.json`, and rebuilds the two `prompt_outputs/*_findings.md` reports.

6. Confirm which tickers were scored and report the new scores. The dashboard will
   show them on reload (tiles, table column, hover breakdown, download reports).
