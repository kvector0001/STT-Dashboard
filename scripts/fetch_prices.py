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

# ── Hardcoded overrides for tickers that yfinance misidentifies ───────────────
# Maps portfolio ticker → correct display name (overrides whatever yfinance returns)
NAME_OVERRIDES = {
    "PARKHOSPS": "Park Medi World Limited",
    "INCAP": "Incap Limited",
}
# Maps portfolio ticker → preferred yfinance symbol (put first in candidates list)
YFINANCE_SYMBOL_OVERRIDES = {
    "PARKHOSPS": "PARKHOSPS.BO",
    "INCAP": "INCAP.BO",
    "MAFANG": "MAFANG.NS",   # .BO only has 1 row of history; .NS has full 5y
}

# ── Path resolution (Google Sheets vs local vs GitHub Actions) ──────────────
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TSn6HIdcsux4p8cdpU0fx78zKibyxFKnwUUZTHFKfNI/export?format=xlsx"
REPO_PATH = "data/portfolio.xlsx"

def download_portfolio():
    import requests
    print(f"[DOWNLOAD] Downloading portfolio from Google Sheets...")
    try:
        response = requests.get(GSHEET_URL, timeout=30)
        response.raise_for_status()
        os.makedirs("data", exist_ok=True)
        with open(REPO_PATH, "wb") as f:
            f.write(response.content)
        print(f"[SUCCESS] Downloaded to {REPO_PATH}")
        return REPO_PATH
    except Exception as e:
        print(f"[ERROR] Failed to download from Google Sheets: {e}")
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
        # Use relative paths from the script directory
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        LOCAL_PATH = os.path.join(BASE_DIR, "Portfolio.xlsx")
        LOCAL_DATA_PATH = os.path.join(BASE_DIR, "Data", "Portfolio.xlsx")
        if os.path.exists(LOCAL_PATH):
            portfolio_file = LOCAL_PATH
        elif os.path.exists(LOCAL_DATA_PATH):
            portfolio_file = LOCAL_DATA_PATH
        elif os.path.exists(REPO_PATH):
            portfolio_file = REPO_PATH

if not portfolio_file:
    raise FileNotFoundError("Portfolio file not found and Google Sheets download failed.")

print(f"[INFO] Reading portfolio from: {portfolio_file}")
# ── Copy to data/portfolio.xlsx for git tracking ─────────────────────────────
os.makedirs("data", exist_ok=True)
if os.path.abspath(portfolio_file) != os.path.abspath(REPO_PATH):
    shutil.copy2(portfolio_file, REPO_PATH)
    print(f"[INFO] Copied to {REPO_PATH}")

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
print(f"[INFO] Found {len(portfolio)} valid holdings in portfolio\n")

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
    print(f"[SUCCESS] Added {len(new_stubs)} new placeholder entries to stocks.json\n")

# Remove stocks from stocks.json that are no longer in the portfolio (unless marked as "pending")
# This ensures deleted rows in Google Sheet are removed from the dashboard
initial_stock_count = len(stocks)
stocks_to_keep = [s for s in stocks if s.get("ticker") in portfolio_tickers]
removed_count = initial_stock_count - len(stocks_to_keep)
if removed_count > 0:
    stocks = stocks_to_keep
    print(f"[INFO] Removed {removed_count} stocks no longer in portfolio\n")
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
    # If there's a hardcoded yfinance symbol override, put it first
    if sym in YFINANCE_SYMBOL_OVERRIDES:
        preferred = YFINANCE_SYMBOL_OVERRIDES[sym]
        candidates = [preferred] + [c for c in candidates if c != preferred]
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
    ret_6m = None
    ret_1y = None
    ret_3y = None
    ret_5y = None
    fetched_ocf = None
    fetched_de = None
    fetched_eps = None
    fetched_bv = None
    fetched_dy = None
    fetched_pat = None
    fetched_rev = None
    fetched_vol_yest_ratio = None
    fetched_vol_30m_ratio = None

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            
            # Fetch historical data for returns calculation (5 years max)
            hist = ticker_obj.history(period="5y")
            
            if not hist.empty and len(hist) > 1:
                curr_price = hist['Close'].iloc[-1]
                ltp = round(float(curr_price), 2)
                
                # Calculate returns based on available historical data
                # 1-day return
                if len(hist) >= 2:
                    ret_1d = round(((curr_price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100), 2)
                
                # 1-month return (~21 trading days)
                if len(hist) >= 21:
                    ret_1m = round(((curr_price - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100), 2)
                
                # 6-month return (~126 trading days)
                if len(hist) >= 126:
                    ret_6m = round(((curr_price - hist['Close'].iloc[-126]) / hist['Close'].iloc[-126] * 100), 2)
                
                # 1-year return (~252 trading days)
                if len(hist) >= 252:
                    ret_1y = round(((curr_price - hist['Close'].iloc[-252]) / hist['Close'].iloc[-252] * 100), 2)
                
                # 3-year return (~756 trading days)
                if len(hist) >= 756:
                    ret_3y = round(((curr_price - hist['Close'].iloc[-756]) / hist['Close'].iloc[-756] * 100), 2)
                
                # 5-year return (~1260 trading days)
                if len(hist) >= 1260:
                    ret_5y = round(((curr_price - hist['Close'].iloc[-1260]) / hist['Close'].iloc[-1260] * 100), 2)
            else:
                # Fallback to fast_info
                fi = ticker_obj.fast_info
                price = fi.last_price
                if price and price > 0:
                    ltp = round(float(price), 2)
            
            if ltp and ltp > 0:
                # Fetch company info for name, sector, market cap, P/E, ROE, and other metrics
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

                    # Additional fundamental metrics
                    ocf = info.get("operatingCashflow")
                    if ocf is not None:
                        fetched_ocf = round(ocf / 10_000_000, 2)  # Convert to Crores

                    de = info.get("debtToEquity")
                    if de is not None:
                        fetched_de = round(de, 3)

                    eps = info.get("trailingEps")
                    if eps is not None:
                        fetched_eps = round(eps, 2)

                    bv = info.get("bookValue")
                    if bv is not None:
                        fetched_bv = round(bv, 2)

                    dy = info.get("dividendYield")
                    if dy is not None:
                        fetched_dy = round(dy * 100, 2)  # Convert to %

                    pat = info.get("earningsGrowth")
                    if pat is not None:
                        fetched_pat = round(pat * 100, 2)  # Convert to %

                    rev = info.get("revenueGrowth")
                    if rev is not None:
                        fetched_rev = round(rev * 100, 2)  # Convert to %

                    # ── New metrics ──────────────────────────────────────────
                    # Margin metrics
                    gm   = info.get("grossMargins")
                    if gm is not None:   prices[sym]["gross_margin"]     = round(gm * 100, 2)
                    om   = info.get("operatingMargins")
                    if om is not None:   prices[sym]["operating_margin"]  = round(om * 100, 2)
                    pm   = info.get("profitMargins")
                    if pm is not None:   prices[sym]["profit_margin"]     = round(pm * 100, 2)
                    roa  = info.get("returnOnAssets")
                    if roa is not None:  prices[sym]["roa"]               = round(roa * 100, 2)
                    ebitda = info.get("ebitdaMargins")
                    if ebitda is not None: prices[sym]["ebitda_margin"]   = round(ebitda * 100, 2)

                    # Growth metrics
                    qrg = info.get("revenueQuarterlyGrowth") or info.get("quarterlyRevenueGrowth")
                    if qrg is not None:  prices[sym]["qtrly_rev_growth"]  = round(qrg * 100, 2)
                    qeg = info.get("earningsQuarterlyGrowth")
                    if qeg is not None:  prices[sym]["qtrly_earn_growth"] = round(qeg * 100, 2)

                    # Cash flow metrics (in Crores)
                    fcf = info.get("freeCashflow")
                    if fcf is not None:  prices[sym]["fcf_cr"]            = round(fcf / 10_000_000, 2)
                    lfcf = info.get("leveredFreeCashFlow") or info.get("totalCashFromOperatingActivities")
                    if lfcf is not None: prices[sym]["lfcf_cr"]           = round(lfcf / 10_000_000, 2)

                    # Price info
                    hi52 = info.get("fiftyTwoWeekHigh")
                    lo52 = info.get("fiftyTwoWeekLow")
                    if hi52 is not None: prices[sym]["week52_high"]       = round(hi52, 2)
                    if lo52 is not None: prices[sym]["week52_low"]        = round(lo52, 2)

                    # Promoter / insider holding (yfinance "heldPercentInsiders")
                    ins = info.get("heldPercentInsiders")
                    if ins is not None:  prices[sym]["promoter_holding"]  = round(ins * 100, 2)

                except Exception as e:
                    pass

                # Volume ratios from already-fetched history
                try:
                    if hist is not None and len(hist) >= 2:
                        yest_vol = float(hist['Volume'].iloc[-2])
                        avg_vol  = float(hist['Volume'].tail(30).mean())
                        if avg_vol > 0:
                            fetched_vol_yest_ratio = round(yest_vol / avg_vol, 2)
                except Exception:
                    pass

                # 30-min intraday volume vs avg 30-min volume
                try:
                    intra = ticker_obj.history(period="1d", interval="5m")
                    if intra is not None and len(intra) > 0:
                        last_30m_vol = float(intra['Volume'].tail(6).sum())
                        avg_30m_vol  = float(intra['Volume'].mean()) * 6
                        if avg_30m_vol > 0:
                            fetched_vol_30m_ratio = round(last_30m_vol / avg_30m_vol, 2)
                except Exception:
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
    if fetched_ocf is not None:
        prices[sym]["ocf_cr"] = fetched_ocf
    if fetched_de is not None:
        prices[sym]["debt_to_equity"] = fetched_de
    if fetched_eps is not None:
        prices[sym]["eps"] = fetched_eps
    if fetched_bv is not None:
        prices[sym]["book_value"] = fetched_bv
    if fetched_dy is not None:
        prices[sym]["div_yield"] = fetched_dy
    if fetched_pat is not None:
        prices[sym]["pat_cagr"] = fetched_pat
    if fetched_rev is not None:
        prices[sym]["rev_cagr"] = fetched_rev
    # mcap_3y: use 3-year price return as proxy
    if ret_3y is not None:
        prices[sym]["mcap_3y"] = ret_3y
    if fetched_vol_yest_ratio is not None:
        prices[sym]["vol_yest_ratio"] = fetched_vol_yest_ratio
    if fetched_vol_30m_ratio is not None:
        prices[sym]["vol_30m_ratio"] = fetched_vol_30m_ratio
    
    # Add return percentages
    if ret_1d is not None:
        prices[sym]["ret_1d"] = ret_1d
    if ret_1m is not None:
        prices[sym]["ret_1m"] = ret_1m
    if ret_6m is not None:
        prices[sym]["ret_6m"] = ret_6m
    if ret_1y is not None:
        prices[sym]["ret_1y"] = ret_1y
    if ret_3y is not None:
        prices[sym]["ret_3y"] = ret_3y
    if ret_5y is not None:
        prices[sym]["ret_5y"] = ret_5y

    if ltp is not None:
        pnl_str = f"  P&L: {pnl_pct:+.1f}% ({pnl_abs:+,.0f})" if pnl_pct is not None else ""
        print(f"[SUCCESS] {sym:<18} LTP: {ltp:>10,.2f}{pnl_str}")
        success += 1
        # Update placeholder name/sector if fetched
        if fetched_name:
            for s in stocks:
                if s["ticker"] == sym and s.get("name") in ("auto", None, ""):
                    s["name"] = fetched_name
                    if fetched_sector and s.get("sector") in ("Pending", None, ""):
                        s["sector"] = fetched_sector
        # Always apply hardcoded name override (never let yfinance overwrite it)
        if sym in NAME_OVERRIDES:
            for s in stocks:
                if s["ticker"] == sym:
                    s["name"] = NAME_OVERRIDES[sym]
            prices[sym]["name"] = NAME_OVERRIDES[sym]
    else:
        print(f"[ERROR] {sym:<18} — price not available")
        failed.append(sym)

# ── Write prices.json — sanitise NaN/Inf to null so JSON stays valid ─────────
import math

def sanitise(obj):
    """Recursively replace float NaN/Inf with None so json.dumps stays valid."""
    if isinstance(obj, dict):
        return {k: sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitise(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

with open("prices.json", "w", encoding="utf-8") as f:
    json.dump(sanitise(prices), f, indent=2, ensure_ascii=False)

# ── Save updated stocks.json (names populated for placeholders) ───────────────
with open(stocks_path, "w", encoding="utf-8") as f:
    json.dump(stocks, f, indent=2, ensure_ascii=False)

print(f"\n{'='*55}")
print(f"[SUCCESS] prices.json updated — {success}/{len(portfolio)} stocks fetched")
if failed:
    print(f"[ERROR] Failed ({len(failed)}): {', '.join(failed)}")
print(f"[INFO] Updated at {now_utc}")
