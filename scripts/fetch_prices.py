"""
fetch_prices.py — Portfolio price fetcher
Reads Portfolio.xlsx, fetches live prices from yfinance, writes prices.json.
Also auto-updates stocks.json with placeholder entries for any new tickers.
"""

import json
import os
import glob
import shutil
import warnings
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Path resolution (Google Sheets vs local vs GitHub Actions) ──────────────
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TSn6HIdcsux4p8cdpU0fx78zKibyxFKnwUUZTHFKfNI/export?format=xlsx"
REPO_PATH = "data/portfolio.xlsx"

def download_portfolio():
    import requests
    print(f"🌐 Downloading portfolio from Google Sheets...")
    try:
        response = requests.get(GSHEET_URL, timeout=30)
        response.raise_for_status()
        os.makedirs("data", exist_ok=True)
        with open(REPO_PATH, "wb") as f:
            f.write(response.content)
        print(f"✅ Downloaded to {REPO_PATH}")
        return REPO_PATH
    except Exception as e:
        print(f"❌ Failed to download from Google Sheets: {e}")
        return None

# Decide which source to use
portfolio_file = None
if os.environ.get("GITHUB_ACTIONS"):
    # Always try to download in CI
    portfolio_file = download_portfolio() 
    if not portfolio_file and os.path.exists(REPO_PATH):
        portfolio_file = REPO_PATH
else:
    # Locally, try download first, fall back to existing files
    portfolio_file = download_portfolio()
    if not portfolio_file:
        LOCAL_PATH = r"C:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard\Portfolio.xlsx"
        LOCAL_DATA_PATH = r"C:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard\Data\Portfolio.xlsx"
        if os.path.exists(LOCAL_PATH):
            portfolio_file = LOCAL_PATH
        elif os.path.exists(LOCAL_DATA_PATH):
            portfolio_file = LOCAL_DATA_PATH
        elif os.path.exists(REPO_PATH):
            portfolio_file = REPO_PATH

if not portfolio_file:
    raise FileNotFoundError("Portfolio file not found and Google Sheets download failed.")

print(f"📂 Reading portfolio from: {portfolio_file}")
# ── Copy to data/portfolio.xlsx for git tracking ─────────────────────────────
os.makedirs("data", exist_ok=True)
if os.path.abspath(portfolio_file) != os.path.abspath(REPO_PATH):
    shutil.copy2(portfolio_file, REPO_PATH)
    print(f"📋 Copied to {REPO_PATH}")

# ── Read the Excel ────────────────────────────────────────────────────────────
df = pd.read_excel(portfolio_file, engine="openpyxl")

# Assign column names based on known structure
expected_cols = [
    "self_other", "symbol", "qty", "buy_avg", "buy_value",
    "ltp", "present_value", "pnl", "pnl_pct",
    "gurpreet", "remarks1", "remarks2"
]
# Trim or pad columns to expected length
n = len(df.columns)
df.columns = expected_cols[:n] + [f"extra_{i}" for i in range(n - len(expected_cols))]

# Filter valid rows
df = df[df["symbol"].notna()]
df = df[~df["symbol"].astype(str).str.contains(" ")]          # remove mutual fund rows
df = df[df["qty"].apply(lambda x: str(x).replace(".", "").isdigit())]  # numeric qty only
df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
df["buy_avg"] = pd.to_numeric(df["buy_avg"], errors="coerce")
df = df.dropna(subset=["qty", "buy_avg"])

portfolio = df[["symbol", "qty", "buy_avg"]].reset_index(drop=True)
print(f"📊 Found {len(portfolio)} valid holdings in portfolio\n")

# ── Load existing stocks.json ─────────────────────────────────────────────────
stocks_path = "stocks.json"
with open(stocks_path, "r", encoding="utf-8") as f:
    stocks = json.load(f)

existing_tickers = {s["ticker"] for s in stocks}

# Add placeholder entries for tickers not in stocks.json
new_stubs = []
portfolio_tickers = set(str(row["symbol"]).strip() for _, row in portfolio.iterrows())

for _, row in portfolio.iterrows():
    sym = str(row["symbol"]).strip()
    if sym not in existing_tickers:
        stub = {
            "ticker": sym,
            "name": "auto",
            "sector": "Pending",
            "nse_symbol": sym,
            "buy_avg": float(row["buy_avg"]),
            "moat_type": "Pending",
            "moat_class": "pending",
            "conviction": 0,
            "moat": "Analysis pending — add manually or re-run Claude.ai analysis",
            "leadership": "Pending",
            "non_rep": "Pending",
            "tailwinds": ["Pending analysis"],
            "risks": ["Pending analysis"],
            "track": ["Add tracking KPIs"],
        }
        new_stubs.append(stub)
        existing_tickers.add(sym)

if new_stubs:
    stocks.extend(new_stubs)
    with open(stocks_path, "w", encoding="utf-8") as f:
        json.dump(stocks, f, indent=2, ensure_ascii=False)
    print(f"✅ Added {len(new_stubs)} new placeholder entries to stocks.json\n")

# Remove stocks from stocks.json that are no longer in the portfolio (unless marked as "pending")
# This ensures deleted rows in Google Sheet are removed from the dashboard
initial_stock_count = len(stocks)
stocks_to_keep = [s for s in stocks if s.get("ticker") in portfolio_tickers]
removed_count = initial_stock_count - len(stocks_to_keep)
if removed_count > 0:
    stocks = stocks_to_keep
    print(f"🗑️  Removed {removed_count} stocks no longer in portfolio\n")
    # Save filtered stocks immediately
    with open(stocks_path, "w", encoding="utf-8") as f:
        json.dump(stocks, f, indent=2, ensure_ascii=False)
else:
    stocks = stocks_to_keep

# ── Fetch prices ──────────────────────────────────────────────────────────────
prices = {}
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# Build lookup of buy_avg and qty from portfolio
portfolio_map = {
    str(row["symbol"]).strip(): {"qty": float(row["qty"]), "buy_avg": float(row["buy_avg"])}
    for _, row in portfolio.iterrows()
}

# Also check stocks.json for nse_symbol overrides (some tickers differ from Yahoo symbols)
nse_override = {}
for s in stocks:
    t = s["ticker"]
    ns = s.get("nse_symbol", t)
    if ns and ns != t:
        nse_override[t] = ns

success = 0
failed = []

for _, row in portfolio.iterrows():
    sym = str(row["symbol"]).strip()
    qty = float(row["qty"])
    buy_avg = float(row["buy_avg"])

    # Strip Zerodha-specific suffixes: -T (SME), -X (delisted/SME), -E (ETF variant), etc.
    # e.g. DEEDEV-T → DEEDEV, INCAP-X → INCAP, MON100-E → MON100
    import re as _re
    clean_sym = _re.sub(r'-[A-Z]$', '', sym)

    yf_sym = nse_override.get(sym, sym)
    clean_yf = _re.sub(r'-[A-Z]$', '', yf_sym)

    candidates = [
        yf_sym + ".NS",
        sym + ".NS",
        clean_sym + ".NS",
        clean_yf + ".NS",
        yf_sym + ".BO",
        sym + ".BO",
        clean_sym + ".BO",
        clean_yf + ".BO",
    ]
    # Deduplicate while preserving order
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    ltp = None
    fetched_name = None
    fetched_sector = None
    fetched_mcap = None
    fetched_pe = None
    fetched_roe = None
    ret_1d = None
    ret_1m = None
    ret_1y = None

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            
            # Fetch historical data for returns calculation
            hist = ticker_obj.history(period="1y")
            
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                ltp = round(float(price), 2)
                
                # Calculate returns based on historical data
                if len(hist) > 0:
                    curr_price = hist['Close'].iloc[-1]
                    
                    # 1-day return
                    if len(hist) >= 2:
                        prev_close = hist['Close'].iloc[-2]
                        ret_1d = round(((curr_price - prev_close) / prev_close * 100), 2) if prev_close > 0 else 0
                    
                    # 1-month return (approx 21 trading days)
                    if len(hist) >= 21:
                        price_1m_ago = hist['Close'].iloc[-21]
                        ret_1m = round(((curr_price - price_1m_ago) / price_1m_ago * 100), 2) if price_1m_ago > 0 else 0
                    
                    # 1-year return
                    if len(hist) >= 252:  # ~252 trading days in a year
                        price_1y_ago = hist['Close'].iloc[0]
                        ret_1y = round(((curr_price - price_1y_ago) / price_1y_ago * 100), 2) if price_1y_ago > 0 else 0
            else:
                # Fallback to fast_info
                fi = ticker_obj.fast_info
                price = fi.last_price
                if price and price > 0:
                    ltp = round(float(price), 2)
            
            if ltp and ltp > 0:
                # Fetch company info for name, sector, market cap, P/E, ROE
                try:
                    info = ticker_obj.info
                    fetched_name = info.get("longName") or info.get("shortName")
                    fetched_sector = info.get("sector") or info.get("industry")
                    
                    # Market cap in Crores (convert from actual market cap)
                    mcap = info.get("marketCap")
                    if mcap:
                        fetched_mcap = round(mcap / 10_000_000, 2)  # Convert to Crores
                    
                    fetched_pe = info.get("trailingPE")
                    fetched_roe = info.get("returnOnEquity")
                    
                except Exception as e:
                    pass
                
                break
        except Exception:
            continue

    pnl_abs = None
    pnl_pct = None
    if ltp is not None and buy_avg > 0:
        pnl_abs = round((ltp - buy_avg) * qty, 2)
        pnl_pct = round((ltp - buy_avg) / buy_avg * 100, 2)

    # Build prices entry with all available data
    prices[sym] = {
        "ltp": ltp,
        "buy_avg": buy_avg,
        "quantity": qty,
        "pnl_pct": pnl_pct,
        "pnl_abs": pnl_abs,
        "updated": now_utc,
    }
    
    # Add fetched metadata if available
    if fetched_mcap is not None:
        prices[sym]["mcap_cr"] = fetched_mcap
    if fetched_pe is not None:
        prices[sym]["pe"] = round(fetched_pe, 2) if fetched_pe > 0 else None
    if fetched_roe is not None:
        prices[sym]["roe"] = round(fetched_roe * 100, 2) if fetched_roe else None
    
    # Add return percentages
    if ret_1d is not None:
        prices[sym]["ret_1d"] = ret_1d
    if ret_1m is not None:
        prices[sym]["ret_1m"] = ret_1m
    if ret_1y is not None:
        prices[sym]["ret_1y"] = ret_1y

    if ltp is not None:
        pnl_str = f"  P&L: {pnl_pct:+.1f}% (₹{pnl_abs:+,.0f})" if pnl_pct is not None else ""
        print(f"✅ {sym:<18} LTP: ₹{ltp:>10,.2f}{pnl_str}")
        success += 1
        # Update placeholder name/sector if fetched
        if fetched_name:
            for s in stocks:
                if s["ticker"] == sym and s.get("name") in ("auto", None, ""):
                    s["name"] = fetched_name
                    if fetched_sector and s.get("sector") in ("Pending", None, ""):
                        s["sector"] = fetched_sector
    else:
        print(f"❌ {sym:<18} — price not available")
        failed.append(sym)

# ── Write prices.json ─────────────────────────────────────────────────────────
with open("prices.json", "w", encoding="utf-8") as f:
    json.dump(prices, f, indent=2, ensure_ascii=False)

# ── Save updated stocks.json (names populated for placeholders) ───────────────
with open(stocks_path, "w", encoding="utf-8") as f:
    json.dump(stocks, f, indent=2, ensure_ascii=False)

print(f"\n{'─'*55}")
print(f"✅ prices.json updated — {success}/{len(portfolio)} stocks fetched")
if failed:
    print(f"❌ Failed ({len(failed)}): {', '.join(failed)}")
print(f"🕐 Updated at {now_utc}")
