# Portfolio Dashboard

A self-hosted Indian stock portfolio fundamental analysis dashboard deployed on GitHub Pages.

## Features
- 📊 Real-time price refresh via GitHub Actions + yfinance (free, zero cost)
- 🏛️ Moat analysis, tailwinds, risks, and tracking KPIs per stock
- 📱 Mobile-first PWA — works as a bookmarked app on your phone
- 🔍 Filter by moat type, conviction, profit/loss; search by ticker or name
- 🌙 Dark mode dashboard

## Setup

### 1. Install dependencies
```bash
pip install yfinance pandas openpyxl
```

### 2. Add your portfolio file
Place your Zerodha portfolio Excel export as `data/portfolio.xlsx` in this repo.

On your local machine the script also reads from:
```
C:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard\Portfolio.xlsx
```

### 3. Fetch prices locally
```bash
cd portfolio-dashboard
python scripts/fetch_prices.py
```

### 4. View locally
```bash
python -m http.server 8000
# Open http://localhost:8000
```

### 5. Deploy to GitHub Pages
- Push this repo to GitHub
- Go to **Settings → Pages → Deploy from branch main / root**
- Your dashboard will be live at `https://YOUR_USERNAME.github.io/portfolio-dashboard/`

## Auto Price Refresh
GitHub Actions refreshes prices daily at **4:00 PM IST (10:30 UTC), Mon–Fri**.

You can also trigger it manually from the **Actions** tab on GitHub.

## Data Files
| File | Description |
|------|-------------|
| `stocks.json` | Fundamental analysis per stock (moat, tailwinds, risks, KPIs) |
| `prices.json` | Live prices — auto-generated, do not edit manually |
| `management_trust.json` | 👔 Management Trust score per stock (5-pillar, keyed by ticker) |
| `red_flags.json` | 🚩 Red-Flag forensic score per stock (4-category, keyed by ticker) |
| `prompt_outputs/management_trust_findings.md` | Downloadable Management Trust report (auto-generated) |
| `prompt_outputs/red_flags_findings.md` | Downloadable Red-Flag report (auto-generated) |
| `scripts/score_companies.py` | Maintains the two score files (`pending` / `merge` / `report`) |
| `data/portfolio.xlsx` | Portfolio file used by GitHub Actions for daily refresh |

> **Keep `data/portfolio.xlsx` updated** — this is what GitHub Actions uses for daily price refresh.

## Updating the Data

There are **three** independent datasets. Prices refresh automatically; the three below are refreshed by you when you add stocks or do a periodic review.

### 1. Fundamental analysis — `stocks.json`
The moat, tailwinds, risks, conviction, KPIs and other qualitative fields.

1. In the dashboard header use **🔬 Refresh ALL** (re-do everything) or **🟡 Refresh Pending** (only stocks missing analysis / new fields) to copy a batched prompt.
2. Paste the prompt into Claude / ChatGPT / DeepSeek; let it return the JSON.
3. Click **📋 Paste Claude Response** in the header and paste the result (use **⏭ Next Batch** for the next set).
4. Click **⬇ Export ALL** to download the merged `stocks.json`, replace the file in the repo, then:
   ```bash
   git add stocks.json && git commit -m "update: fundamentals" && git push
   ```

### 2. Management Trust — `management_trust.json`
A 5-pillar score (Promoter Profile 20%, Ownership Behaviour 25%, Capital Allocation 20%, Governance 20%, Execution 15%). New stocks show `—` until scored. **No API key needed.**

**Path A — VS Code agent mode (recommended):** open this folder in VS Code and, in Copilot Chat (Agent mode), run:
```
/score-pending
```
The agent finds every stock missing a Management Trust **and/or** Red Flags score, scores it from `stocks.json` + the methodology in `prompts/management_trust.md`, writes the JSON and rebuilds the report.

**Path B — Claude web (no agent):**
1. Double-click **`score_pending.bat`** — it lists what's missing and opens `prompt_outputs/_pending_scores_worklist.md` (each company's snapshot + the ready prompt).
2. Paste the blocks into Claude, collect the answers into `prompt_outputs/_scores_to_merge.json` (shape: `prompt_outputs/_scores_to_merge.template.json`).
3. Double-click **`merge_scores.bat`** — it merges and rebuilds the report.
4. Commit:
   ```bash
   git add management_trust.json prompt_outputs/management_trust_findings.md && git commit -m "update: mgmt trust" && git push
   ```

> The **overall score + verdict are recomputed on merge** from the pillar sub-scores, so you only supply the 5 pillar scores + reasons + summary + confidence. Keep it evidence-based — mark **Low** confidence for new IPOs / thin data. ETFs: set `"etf": true`.

### 3. Red Flags — `red_flags.json`
A 4-category forensic score (Accounting 30%, Governance 30%, Financial 20%, Business 20%) where **10 = clean, 0–3 = serious red flags** — higher is cleaner. Methodology: `prompts/red_flags.md`.

Red Flags is maintained by the **same tooling as Management Trust** — `/score-pending` (Path A) or `score_pending.bat` → `merge_scores.bat` (Path B) fills both at once. After merging:
```bash
git add red_flags.json prompt_outputs/red_flags_findings.md && git commit -m "update: red flags" && git push
```

**Helper commands** (run from the repo root):
| Command | What it does |
|---------|--------------|
| `python scripts/score_companies.py pending` | List stocks missing a score; write the worklist + merge template |
| `python scripts/score_companies.py merge <file.json>` | Merge filled scores into both JSON files + rebuild reports |
| `python scripts/score_companies.py report` | Rebuild both `*_findings.md` reports from the JSON |

On the page, the scores appear on each card's **👔 Management Trust** / **🚩 Red Flags** tiles (click = AI search, hover = full breakdown), in the analysis table columns, the **👔 Trust 7+** / **🚩 Red Flags (<5)** filters, and the two **⬇ Report** download buttons.

## iPhone Home Screen (PWA)
1. Open the GitHub Pages URL in Safari
2. Tap Share → "Add to Home Screen"
3. It opens full-screen like a native app

---
*Built with yfinance, GitHub Actions, and GitHub Pages. Zero cost, zero servers.*
