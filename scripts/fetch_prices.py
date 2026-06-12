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

print(f"[INFO] Sheet columns: {list(df.columns)}")

# ── Find required columns by searching header names (case-insensitive) ────────
def find_col(df, keywords):
    """Return the first column name whose header contains any of the keywords (case-insensitive)."""
    for col in df.columns:
        col_str = str(col).lower().strip()
        for kw in keywords:
            if kw in col_str:
                return col
    return None

sym_col  = find_col(df, ["symbol", "ticker", "scrip", "stock"])
qty_col  = find_col(df, ["qty", "quantity", "shares", "units"])
avg_col  = find_col(df, ["buy avg", "buyavg", "avg price", "avg cost", "purchase price", "buy_avg", "avg"])

missing = []
if sym_col  is None: missing.append("Symbol/Ticker column (tried: symbol, ticker, scrip, stock)")
if qty_col  is None: missing.append("Qty column (tried: qty, quantity, shares, units)")
if avg_col  is None: missing.append("Buy Avg column (tried: buy avg, avg price, avg cost, purchase price)")

if missing:
    err = "SYNC FAILED — Required columns not found in Google Sheet:\n" + "\n".join(f"  - {m}" for m in missing)
    print(f"[ERROR] {err}")
    # Write a sync error marker so the UI can show it
    import json as _json2
    err_marker = {"_sync_error": err, "_sync_time": now_utc}
    if os.path.exists("prices.json"):
        with open("prices.json", "r", encoding="utf-8") as f:
            try:
                existing = _json2.load(f)
                existing["_sync_error"] = err
                existing["_sync_time"] = now_utc
            except Exception:
                existing = err_marker
        with open("prices.json", "w", encoding="utf-8") as f:
            _json2.dump(existing, f, indent=2, ensure_ascii=False)
    import sys
    sys.exit(1)

print(f"[INFO] Using columns: symbol={sym_col!r}, qty={qty_col!r}, buy_avg={avg_col!r}")

# Detect optional MB / Must Buy column — exact match on column name
mb_col = None
for col in df.columns:
    if str(col).strip().lower() in ['mb', 'must buy', 'mustbuy', 'must_buy']:
        mb_col = col
        break
if mb_col:
    print(f"[INFO] Found MB column: {mb_col!r}")

# Filter valid rows using detected column names
cols_to_keep = ["symbol", "qty", "buy_avg"]
df = df.rename(columns={sym_col: "symbol", qty_col: "qty", avg_col: "buy_avg"})
if mb_col and mb_col not in [sym_col, qty_col, avg_col]:
    df = df.rename(columns={mb_col: "must_buy"})
    cols_to_keep.append("must_buy")
df = df[cols_to_keep].copy()

# Strip Zerodha risk-indicator suffixes like -T, -X, -E, -B, -Z etc.
# e.g. MODISONLTD-T → MODISONLTD, LAKSELEC-X → LAKSELEC
import re as _re_suffix
df["symbol"] = df["symbol"].astype(str).str.replace(r'-[A-Z]$', '', regex=True)

# Filter valid rows
df = df[df["symbol"].notna()]
df = df[~df["symbol"].astype(str).str.contains(" ")]          # remove mutual fund rows
df = df[df["qty"].apply(lambda x: str(x).replace(".", "").isdigit())]  # numeric qty only
df = df[~df["symbol"].astype(str).str.match(r'^\d')]           # reject numeric-only symbols (Excel formatting errors)
df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
df["buy_avg"] = pd.to_numeric(df["buy_avg"], errors="coerce")
df = df.dropna(subset=["qty", "buy_avg"])

portfolio = df[["symbol", "qty", "buy_avg"]].reset_index(drop=True)
print(f"[INFO] Found {len(portfolio)} valid holdings in portfolio\n")

# ── Sanity check: abort if portfolio looks empty or corrupt ─────────────────
# Load existing prices.json to use as fallback if fetch gives bad results
prices_path = "prices.json"
fallback_prices = {}
try:
    if os.path.exists(prices_path):
        with open(prices_path, "r", encoding="utf-8") as f:
            raw_fallback = f.read()
        import re as _re2
        raw_fallback = raw_fallback.replace(': NaN', ': null').replace(':NaN', ':null')
        fallback_prices = json.loads(raw_fallback)
        # Filter out numeric tickers from fallback too
        fallback_prices = {k: v for k, v in fallback_prices.items() if not _re2.match(r'^\d', k)}
except Exception:
    pass

if len(portfolio) < 5:
    print(f"[ERROR] Portfolio has only {len(portfolio)} valid stocks — looks corrupt. Aborting to preserve existing prices.json.")
    import sys
    sys.exit(1)

# ── Load existing stocks.json ─────────────────────────────────────────────────
stocks_path = "stocks.json"
with open(stocks_path, "r", encoding="utf-8") as f:
    stocks = json.load(f)

existing_tickers = {s["ticker"] for s in stocks}

# Add placeholder entries for tickers not in stocks.json
import re as _re_clean
def _clean_ticker(t):
    return _re_clean.sub(r'-[A-Z]$', '', str(t).strip())

new_stubs = []
portfolio_tickers = set(_clean_ticker(row["symbol"]) for _, row in portfolio.iterrows())

for _, row in portfolio.iterrows():
    sym = _clean_ticker(row["symbol"])
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

# Build lookup of buy_avg and qty from portfolio (use clean tickers as keys)
portfolio_map = {
    _clean_ticker(row["symbol"]): {"qty": float(row["qty"]), "buy_avg": float(row["buy_avg"]),
                                    "must_buy": str(row["must_buy"]).strip().upper() == "MUSTBUY" if "must_buy" in portfolio.columns else False}
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
    raw_sym = str(row["symbol"]).strip()
    qty = float(row["qty"])
    buy_avg = float(row["buy_avg"])

    # Strip Zerodha-specific suffixes: -T (SME), -X (delisted/SME), -E (ETF variant), etc.
    # e.g. DEEDEV-T → DEEDEV, INCAP-X → INCAP, MON100-E → MON100
    import re as _re
    sym = _re.sub(r'-[A-Z]$', '', raw_sym)   # use clean ticker as the canonical key

    yf_sym = nse_override.get(raw_sym, nse_override.get(sym, sym))
    clean_yf = _re.sub(r'-[A-Z]$', '', yf_sym)

    candidates = [
        yf_sym + ".NS",
        sym + ".NS",
        clean_yf + ".NS",
        yf_sym + ".BO",
        sym + ".BO",
        clean_yf + ".BO",
    ]
    # If there's a hardcoded yfinance symbol override, put it first (check both raw and clean)
    override_key = raw_sym if raw_sym in YFINANCE_SYMBOL_OVERRIDES else (sym if sym in YFINANCE_SYMBOL_OVERRIDES else None)
    if override_key:
        preferred = YFINANCE_SYMBOL_OVERRIDES[override_key]
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
    ret_2y = None
    ret_3y = None
    ret_4y = None
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
    fetched_mover_a = None
    fetched_mover_c = None
    fetched_vol_today_ratio = None
    fetched_trend_score = None
    fetched_trend_signal = None
    fetched_price_to_200dma_pct = None
    fetched_dma200_slope_30d_pct = None
    fetched_days_above_200dma_10d = None
    fetched_gross_margin = None
    fetched_op_margin = None
    fetched_profit_margin = None
    fetched_roa = None
    fetched_ebitda_margin = None
    fetched_qtrly_rev_growth = None
    fetched_qtrly_earn_growth = None
    fetched_fcf_cr = None
    fetched_opcf_3yr_avg = None
    fetched_fcf_3yr_avg = None
    fetched_price_to_book = None
    fetched_ev_ebitda = None
    fetched_week52_high = None
    fetched_week52_low = None
    fetched_insider_pct = None

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

                # 2-year return (~504 trading days)
                if len(hist) >= 504:
                    ret_2y = round(((curr_price - hist['Close'].iloc[-504]) / hist['Close'].iloc[-504] * 100), 2)

                # 4-year return (~1008 trading days)
                if len(hist) >= 1008:
                    ret_4y = round(((curr_price - hist['Close'].iloc[-1008]) / hist['Close'].iloc[-1008] * 100), 2)

                # 5-year return (~1200 trading days, slightly lower to account for holidays)
                if len(hist) >= 1200:
                    ret_5y = round(((curr_price - hist['Close'].iloc[-1200]) / hist['Close'].iloc[-1200] * 100), 2)
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

                    # ── New metrics — store in locals, applied after prices[sym] is created ──
                    # Margin metrics
                    gm   = info.get("grossMargins")
                    if gm is not None:   fetched_gross_margin    = round(gm * 100, 2)
                    om   = info.get("operatingMargins")
                    if om is not None:   fetched_op_margin       = round(om * 100, 2)
                    pm   = info.get("profitMargins")
                    if pm is not None:   fetched_profit_margin   = round(pm * 100, 2)
                    roa  = info.get("returnOnAssets")
                    if roa is not None:  fetched_roa             = round(roa * 100, 2)
                    ebitda = info.get("ebitdaMargins")
                    if ebitda is not None: fetched_ebitda_margin = round(ebitda * 100, 2)

                    # Growth metrics
                    qrg = info.get("revenueQuarterlyGrowth") or info.get("quarterlyRevenueGrowth")
                    if qrg is not None:  fetched_qtrly_rev_growth  = round(qrg * 100, 2)
                    qeg = info.get("earningsQuarterlyGrowth")
                    if qeg is not None:  fetched_qtrly_earn_growth = round(qeg * 100, 2)

                    # Cash flow metrics (latest year, in Crores)
                    fcf = info.get("freeCashflow")
                    if fcf is not None:  fetched_fcf_cr = round(fcf / 10_000_000, 2)
                    ocf_val = info.get("operatingCashflow")
                    if ocf_val is not None: fetched_ocf = round(ocf_val / 10_000_000, 2)

                    # 3-year average FCF and OCF from cashflow statement
                    try:
                        cf = ticker_obj.cashflow
                        if cf is not None and not cf.empty:
                            for lbl in ['Operating Cash Flow', 'Total Cash From Operating Activities', 'Cash From Operations']:
                                rows = [r for r in cf.index if lbl.lower() in r.lower()]
                                if rows:
                                    vals = cf.loc[rows[0]].dropna().head(3).values
                                    if len(vals) > 0:
                                        fetched_opcf_3yr_avg = round(float(vals.mean()) / 10_000_000, 2)
                                    break
                            for lbl in ['Free Cash Flow', 'Levered Free Cash Flow']:
                                rows = [r for r in cf.index if lbl.lower() in r.lower()]
                                if rows:
                                    vals = cf.loc[rows[0]].dropna().head(3).values
                                    if len(vals) > 0:
                                        fetched_fcf_3yr_avg = round(float(vals.mean()) / 10_000_000, 2)
                                    break
                    except Exception:
                        pass

                    # Valuation ratios
                    pb  = info.get("priceToBook")
                    if pb is not None:   fetched_price_to_book = round(pb, 2)
                    ev_eb = info.get("enterpriseToEbitda")
                    if ev_eb is not None: fetched_ev_ebitda    = round(ev_eb, 2)

                    # Price info
                    hi52 = info.get("fiftyTwoWeekHigh")
                    lo52 = info.get("fiftyTwoWeekLow")
                    if hi52 is not None: fetched_week52_high = round(hi52, 2)
                    if lo52 is not None: fetched_week52_low  = round(lo52, 2)

                    # Insider holding
                    ins = info.get("heldPercentInsiders")
                    if ins is not None:  fetched_insider_pct = round(ins * 100, 2)

                except Exception as e:
                    pass

                # Volume ratios and Movers from already-fetched history
                try:
                    if hist is not None and len(hist) >= 2:
                        today_vol  = float(hist['Volume'].iloc[-1])
                        yest_vol   = float(hist['Volume'].iloc[-2])
                        # Exclude today from averages so today's spike isn't diluted
                        avg_30d = float(hist['Volume'].tail(31).iloc[:-1].mean()) if len(hist) >= 31 else float(hist['Volume'].iloc[:-1].mean())
                        avg_5d  = float(hist['Volume'].tail(6).iloc[:-1].mean())  if len(hist) >= 6  else float(hist['Volume'].iloc[:-1].mean())
                        if avg_30d > 0:
                            fetched_vol_today_ratio = round(today_vol / avg_30d, 2)
                            fetched_vol_yest_ratio  = round(yest_vol  / avg_30d, 2)
                        # Mover A: strict — vol > 3x 30d AND > 3x 5d AND (ret > +3% OR ret < -3%)
                        if avg_30d > 0 and avg_5d > 0 and ret_1d is not None:
                            fetched_mover_a = (today_vol > 3 * avg_30d and today_vol > 3 * avg_5d and (ret_1d > 3.0 or ret_1d < -3.0))
                        # Mover C: balanced — vol > 2x 30d AND (ret > +4% OR ret < -4%)
                        if avg_30d > 0 and ret_1d is not None:
                            fetched_mover_c = (today_vol > 2 * avg_30d and (ret_1d > 4.0 or ret_1d < -4.0))

                        # 200DMA Trend Score (3-12 month positional framework)
                        try:
                            if len(hist) >= 210:  # need 200 bars + buffer
                                close_s = hist['Close']
                                dma200 = close_s.rolling(200).mean()
                                dma200_today = float(dma200.iloc[-1])
                                dma200_30d_ago = float(dma200.iloc[-31]) if len(dma200) >= 31 else None
                                curr_close = float(close_s.iloc[-1])

                                p200_pct = round((curr_close - dma200_today) / dma200_today * 100, 2)
                                fetched_price_to_200dma_pct = p200_pct

                                if dma200_30d_ago is not None and dma200_30d_ago > 0:
                                    slope = round((dma200_today - dma200_30d_ago) / dma200_30d_ago * 100, 2)
                                    fetched_dma200_slope_30d_pct = slope
                                else:
                                    slope = None

                                # Days above 200DMA in last 10 sessions
                                last10_close = close_s.iloc[-10:]
                                last10_dma   = dma200.iloc[-10:]
                                days_above = int((last10_close.values > last10_dma.values).sum())
                                fetched_days_above_200dma_10d = days_above

                                # Trend Score (0-100)
                                # Component 1: Price vs 200DMA (40 pts)
                                if   0 <= p200_pct <= 10:   c1 = 40
                                elif 10 < p200_pct <= 20:  c1 = 28
                                elif p200_pct > 20:         c1 = 15
                                elif -5 <= p200_pct < 0:   c1 = 18
                                elif -10 <= p200_pct < -5: c1 = 10
                                else:                       c1 = 0

                                # Component 2: 200DMA slope (30 pts)
                                if slope is None:              c2 = 0
                                elif slope > 1.0:              c2 = 30
                                elif slope > 0.3:              c2 = 22
                                elif slope >= 0:               c2 = 14
                                elif slope >= -0.3:            c2 = 8
                                else:                          c2 = 0

                                # Component 3: Days above 200DMA in last 10 (30 pts)
                                if   days_above >= 9: c3 = 30
                                elif days_above >= 7: c3 = 22
                                elif days_above >= 5: c3 = 14
                                elif days_above >= 3: c3 = 7
                                else:                 c3 = 0

                                score = c1 + c2 + c3
                                fetched_trend_score = score

                                # Signal considers BOTH score AND price zone
                                # Only stocks in 0-10% zone (sweet spot) can be Bullish/Strong Bullish
                                in_sweet_zone = 0 <= p200_pct <= 10
                                if   score >= 85 and in_sweet_zone: fetched_trend_signal = 'Strong Bullish'
                                elif score >= 70 and in_sweet_zone: fetched_trend_signal = 'Bullish'
                                elif score >= 70:                    fetched_trend_signal = 'Extended'
                                elif score >= 55:                    fetched_trend_signal = 'Watch'
                                elif score >= 35:                    fetched_trend_signal = 'Hold'
                                else:                               fetched_trend_signal = 'Bearish'
                        except Exception:
                            pass
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
        "must_buy": portfolio_map.get(sym, {}).get("must_buy", False),
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
    if fetched_vol_today_ratio is not None:
        prices[sym]["vol_today_ratio"] = fetched_vol_today_ratio
    if fetched_vol_yest_ratio is not None:
        prices[sym]["vol_yest_ratio"] = fetched_vol_yest_ratio
    # Movers: combine A and C into one field
    if fetched_mover_a is not None and fetched_mover_c is not None:
        if fetched_mover_a and fetched_mover_c:
            prices[sym]["movers"] = "A+C"
        elif fetched_mover_a:
            prices[sym]["movers"] = "A"
        elif fetched_mover_c:
            prices[sym]["movers"] = "C"
        else:
            prices[sym]["movers"] = "No"
    # Trend Signal (200DMA framework)
    if fetched_trend_score is not None:
        prices[sym]["trend_score"] = fetched_trend_score
    if fetched_trend_signal is not None:
        prices[sym]["trend_signal"] = fetched_trend_signal
    if fetched_price_to_200dma_pct is not None:
        prices[sym]["price_to_200dma_pct"] = fetched_price_to_200dma_pct
    if fetched_dma200_slope_30d_pct is not None:
        prices[sym]["dma200_slope_30d_pct"] = fetched_dma200_slope_30d_pct
    if fetched_days_above_200dma_10d is not None:
        prices[sym]["days_above_200dma_10d"] = fetched_days_above_200dma_10d
    if fetched_gross_margin is not None:
        prices[sym]["gross_margin"] = fetched_gross_margin
    if fetched_op_margin is not None:
        prices[sym]["operating_margin"] = fetched_op_margin
    if fetched_profit_margin is not None:
        prices[sym]["profit_margin"] = fetched_profit_margin
    if fetched_roa is not None:
        prices[sym]["roa"] = fetched_roa
    if fetched_ebitda_margin is not None:
        prices[sym]["ebitda_margin"] = fetched_ebitda_margin
    if fetched_qtrly_rev_growth is not None:
        prices[sym]["qtrly_rev_growth"] = fetched_qtrly_rev_growth
    if fetched_qtrly_earn_growth is not None:
        prices[sym]["qtrly_earn_growth"] = fetched_qtrly_earn_growth
    if fetched_fcf_cr is not None:
        prices[sym]["fcf_cr"] = fetched_fcf_cr
    if fetched_opcf_3yr_avg is not None:
        prices[sym]["opcf_3yr_avg"] = fetched_opcf_3yr_avg
    if fetched_fcf_3yr_avg is not None:
        prices[sym]["fcf_3yr_avg"] = fetched_fcf_3yr_avg
    if fetched_price_to_book is not None:
        prices[sym]["price_to_book"] = fetched_price_to_book
    if fetched_ev_ebitda is not None:
        prices[sym]["ev_ebitda"] = fetched_ev_ebitda
    if fetched_week52_high is not None:
        prices[sym]["week52_high"] = fetched_week52_high
    if fetched_week52_low is not None:
        prices[sym]["week52_low"] = fetched_week52_low
    if fetched_insider_pct is not None:
        prices[sym]["insider_pct"] = fetched_insider_pct

    # Add return percentages
    if ret_1d is not None:
        prices[sym]["ret_1d"] = ret_1d
    if ret_1m is not None:
        prices[sym]["ret_1m"] = ret_1m
    if ret_6m is not None:
        prices[sym]["ret_6m"] = ret_6m
    if ret_1y is not None:
        prices[sym]["ret_1y"] = ret_1y
    if ret_2y is not None:
        prices[sym]["ret_2y"] = ret_2y
    if ret_3y is not None:
        prices[sym]["ret_3y"] = ret_3y
    if ret_4y is not None:
        prices[sym]["ret_4y"] = ret_4y
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

# ── Write prices.json — sanity check before writing ────────────────────────
# If new prices have far fewer valid stocks than fallback, keep fallback
import re as _re3
valid_new = {k: v for k, v in prices.items() if not _re3.match(r'^\d', k) and v.get('ltp') is not None}
if len(fallback_prices) > 10 and len(valid_new) < len(fallback_prices) * 0.5:
    print(f"[WARNING] New prices have only {len(valid_new)} valid stocks vs fallback {len(fallback_prices)}. Merging to preserve data.")
    # Merge: keep fallback as base, update with valid new prices
    merged_prices = dict(fallback_prices)
    merged_prices.update(valid_new)
    prices = merged_prices
else:
    # Filter out any remaining numeric-ticker entries
    prices = {k: v for k, v in prices.items() if not _re3.match(r'^\d', k)}
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
