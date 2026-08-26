# STT Portfolio Dashboard: Copilot Handoff

## Project Purpose

This is a personal Indian-market portfolio monitoring dashboard for managing allocation across long-term holdings. It detects catalysts, re-ratings, breakouts, and temporary pullbacks that may create better 6-12 month allocation opportunities.

It is a self-hosted, mobile-friendly PWA deployed at `https://kvector0001.github.io/STT-Dashboard/`. It combines portfolio holdings, live and historical prices, fundamentals, qualitative moat analysis, management and governance scoring, peer comparisons, momentum signals, account summaries, and AI research prompts.

The momentum framework is a portfolio monitor, not a screener. Do not introduce eligibility filters such as market-cap, liquidity, promoter-pledge, or listing-age gates.

## Architecture

- `index.html`: Main single-page UI, including cards, analysis table, filtering, summaries, privacy lock, exports, AI prompts, and momentum calculations.
- `app.py`: Optional local Flask server on port 8000 with local refresh, streamed refresh, and save/push APIs.
- `scripts/fetch_prices.py`: Primary data pipeline. Downloads the Google Sheet, aggregates holdings, fetches Yahoo Finance data, calculates returns/momentum/trends, and writes `prices.json` and `stocks.json` data.
- `scripts/momentum_classifier.py`: Canonical momentum and allocation rules mirrored by the frontend.
- `scripts/fetch_extended_data.py`: Secondary fundamentals and returns refresh used by GitHub Actions.
- `scripts/score_companies.py`: Management Trust and Red Flags datasets and reports.
- `scripts/build_quality_score.py`, `scripts/build_peer_rank.py`, and `scripts/build_peer_verdict.py`: Qualitative quality and peer datasets.
- `.github/workflows/refresh-prices.yml`: Scheduled and manual GitHub Actions refresh.
- `manifest.json` and `sw.js`: Installable PWA with network-first caching.

## Running Locally

```powershell
cd "C:\Users\shashirekha\OneDrive - Microsoft\Shashi\Dashboard\Dashboard"
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8000`. Alternatively, run `bat/start_dashboard.bat`.

To refresh portfolio data manually:

```powershell
python scripts/fetch_prices.py
```

`bat/morning_refresh.bat` performs a refresh followed by commit and push. Ask before committing or pushing personal portfolio data.

## Important Behavior

- Holdings are aggregated across accounts while retaining per-account quantity, cost, and invested value.
- Cash is extracted from Google Sheet rows whose type is `Cash` and remains separate from invested value and equity returns.
- Missing or suspect returns are excluded from aggregate calculations, not treated as zero.
- Quality scoring excludes live valuation; valuation is handled separately.
- Red Flags uses a "higher is cleaner" scale.
- PARKHOSPS is Park Medi World Limited and has a Yahoo symbol override.
- SKFINDUS maps explicitly to `SKFINDUS.NS`.
- Wrong-security protection compares Yahoo LTP with sheet-derived LTP. It uses the sheet price and blanks contaminated returns/technicals when divergence exceeds tolerance.

## Momentum Rules

- Daily: breakout/breakdown at volume >= 3x and move >= +/-3%.
- Weekly: breakout/breakdown at volume >= 1.5x and move >= +/-8%; trending at volume >= 1.3x and move >= +/-5%.
- Monthly: breakout/breakdown at volume >= 1.3x and move >= +/-12%; trending at volume >= 1.2x and move >= +/-8%.
- A weekly/monthly dip with a rising 200DMA and Trend Score >= 70 is a pullback/hold, not automatically a reduce signal.

## Recent Work

The recovered conversation most recently covered:

1. Portfolio Extract, lock-state errors, mobile search/filter ergonomics, sticky-symbol opacity, and toolbar placement.
2. Richer mover tooltips and AI prompts for Claude, ChatGPT, DeepSeek, and Gemini.
3. Table ordering around company, daily/weekly/monthly movers, allocation, trend, and returns.
4. Revised momentum rules and tag validation.
5. Per-column mover filters, bulk prompts, clear-filter behavior, and an allocation prompt combining all timeframes.
6. Trend Score and allocation calibration for 6-12 month catalysts without misclassifying healthy pullbacks.
7. Cash, win-rate display, account summaries, and multi-account aggregation.
8. SKFINDUS pricing and generic wrong-ticker safeguards.
9. Management Trust, Red Flags, and quality scores for eight newly analyzed holdings.

## Known Issues

- At recovery time, `prices.json` was dated 2026-07-14 and stale relative to 2026-08-26.
- `data/portfolio.xlsx` was locally modified and uncommitted. Preserve it; do not overwrite, discard, or commit it without checking the source difference.
- The monthly mover tooltip says +/-15%, while frontend logic and the canonical classifier use +/-12%.
- `README.md` has stale setup details, including an obsolete absolute path and inconsistent portfolio-file casing/location.
- `scripts/fetch_extended_data.py` has a "Final Save" comment but no final write, so a partial final batch can be lost.
- The extended-data script does not reuse centralized Yahoo symbol overrides from the primary fetcher.
- Pending Management Trust/Red Flags worklists include non-equity instruments and `Cash`; these should be excluded or explicitly classified.
- The client-side privacy lock cannot secure personal data already published in public JSON.
- Several generator scripts depend on `Downloads\batch_*.json`, fixed local assumptions, or hardcoded update dates.

## Recommended Continuation

First inspect git status and preserve the modified `data/portfolio.xlsx`. Verify generated-data timestamps before refreshing anything. Then:

1. Fix the monthly tooltip from +/-15% to +/-12%.
2. Add the missing final write to `scripts/fetch_extended_data.py`.
3. Share Yahoo symbol overrides with the primary fetcher.
4. Exclude Cash and non-equity instruments from pending company-score worklists.
5. Update README run and data instructions.
6. Add focused tests for monthly momentum thresholds, SKFINDUS/wrong-ticker fallback, cash extraction, and null-return summary behavior.

Run focused tests and syntax checks, show data changes before applying a refresh, and ask before committing or pushing refreshed personal portfolio data.

The complete text-only recovered conversation remains one level above this workspace at `..\COPILOT_CHAT_RECOVERY.md`. It contains 376 user prompts and 371 Copilot responses with inaccessible attachment metadata removed.