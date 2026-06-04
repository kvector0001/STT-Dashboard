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
| `data/portfolio.xlsx` | Portfolio file used by GitHub Actions for daily refresh |

> **Keep `data/portfolio.xlsx` updated** — this is what GitHub Actions uses for daily price refresh.

## Monthly Update Workflow
1. Go to Claude.ai
2. Upload your updated Excel portfolio
3. Ask: *"Refresh the fundamental analysis for my stocks"*
4. Copy the updated `stocks.json` into this repo
5. `git add stocks.json && git commit -m "update: monthly fundamentals" && git push`

## iPhone Home Screen (PWA)
1. Open the GitHub Pages URL in Safari
2. Tap Share → "Add to Home Screen"
3. It opens full-screen like a native app

---
*Built with yfinance, GitHub Actions, and GitHub Pages. Zero cost, zero servers.*
