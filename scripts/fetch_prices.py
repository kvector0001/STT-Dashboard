"""
fetch_prices.py — Portfolio price fetcher
Reads Portfolio.xlsx, fetches live prices from yfinance, writes prices.json.
Also auto-updates stocks.json with placeholder entries for any new tickers.

CHANGELOG — Momentum classifier v5:
  * Monthly breakout threshold relaxed from ±15% to ±12%.
  * Added 📈/📉 trending tags (weekly & monthly only): meaningful move + volume
    but NOT near a high/low extreme  (weekly rvol≥1.3× & |ret_1w|≥5%,
    monthly rvol≥1.2× & |ret_1m|≥8%).
  * Added ⚠️ SUSPECT daily override (rvol≥10× AND |ret_1d|≥3%) — takes
    precedence over V / V+P / P surge codes.
  * Added overlay allocation tag (movers_alloc) computed from all 3 timeframes:
    💎 max-conviction increase · 🌱 early build · ⏳ extended/watch · 🚨 exit.
  * Sort rank: 🔥>🚀>📈>🧊>❄️>📉>V+P>V>P>No>⚠️.
  Preserved: rvol formulas, location defs, V/V+P/P codes, "ATH before 52-week"
  ordering, and the 🧊=lifetime-low / ❄️=52-week-low mapping.
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
acct_col = find_col(df, ["account"])
bv_col   = find_col(df, ["buy value", "buyvalue"])
pv_col   = find_col(df, ["present value", "current value", "market value"])
type_col = find_col(df, ["type", "asset class", "category"])
if acct_col:
    print(f"[INFO] Found Account column: {acct_col!r}")
if type_col:
    print(f"[INFO] Found Type column: {type_col!r}")

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

# Detect optional MB / Must Buy column — check BEFORE any renaming
mb_col = None
for col in df.columns:
    if str(col).strip().lower() in ['mb', 'must buy', 'mustbuy', 'must_buy']:
        mb_col = col
        break
if mb_col:
    print(f"[INFO] Found MB column: {mb_col!r}")

# ── Read the separate "Must Buy" sheet (a second tab in the same workbook) ──
# The Google Sheet has a dedicated "MB" tab listing Must-Buy tickers. We always
# merge it in, so Must-Buy works whether or not the main sheet has an MB column.
MUSTBUY_SET = set()
import re as _re_mb
try:
    all_sheets = pd.read_excel(portfolio_file, sheet_name=None, engine="openpyxl")
    mb_sheet_name = None
    for sname in all_sheets:
        low = str(sname).strip().lower()
        if any(kw in low for kw in ['must buy', 'mustbuy', 'must_buy', 'must-buy']) or low in ['mb', 'mustbuy']:
            mb_sheet_name = sname
            break
    if mb_sheet_name is not None:
        mb_df = all_sheets[mb_sheet_name]
        # Prefer a symbol/ticker column; otherwise use the first column
        mb_tcol = find_col(mb_df, ["symbol", "ticker", "scrip", "stock", "mustbuy", "must buy"])
        if mb_tcol is None and len(mb_df.columns) > 0:
            mb_tcol = mb_df.columns[0]
        if mb_tcol is not None:
            for v in mb_df[mb_tcol].dropna().astype(str):
                t = _re_mb.sub(r'\s+', '', v.strip().upper())
                t = _re_mb.sub(r'-[A-Z]$', '', t)   # strip Zerodha suffix
                if t and not t.replace('.', '').isdigit():
                    MUSTBUY_SET.add(t)
        print(f"[INFO] Read Must Buy sheet {mb_sheet_name!r}: {len(MUSTBUY_SET)} tickers")
    else:
        print("[INFO] No separate Must Buy sheet found.")
except Exception as e:
    print(f"[WARN] Could not read Must Buy fallback sheet: {e}")

# Filter valid rows using detected column names
cols_to_keep = ["symbol", "qty", "buy_avg"]
df = df.rename(columns={sym_col: "symbol", qty_col: "qty", avg_col: "buy_avg"})
if acct_col and acct_col not in [sym_col, qty_col, avg_col]:
    df = df.rename(columns={acct_col: "account"})
    cols_to_keep.append("account")
if bv_col and bv_col not in [sym_col, qty_col, avg_col, acct_col]:
    df = df.rename(columns={bv_col: "buy_value"})
    cols_to_keep.append("buy_value")
if mb_col and mb_col not in [sym_col, qty_col, avg_col, acct_col, bv_col]:
    df = df.rename(columns={mb_col: "must_buy"})
    cols_to_keep.append("must_buy")
if pv_col and pv_col not in [sym_col, qty_col, avg_col, acct_col, bv_col, mb_col]:
    df = df.rename(columns={pv_col: "present_value"})
    cols_to_keep.append("present_value")
if type_col and type_col not in [sym_col, qty_col, avg_col, acct_col, bv_col, mb_col, pv_col]:
    df = df.rename(columns={type_col: "holding_type"})
    cols_to_keep.append("holding_type")
df = df[cols_to_keep].copy()
# Exclude the spreadsheet TOTAL summary row(s) (Account Name == "TOTAL")
if "account" in df.columns:
    df = df[df["account"].astype(str).str.strip().str.upper() != "TOTAL"]

# ── Separate non-equity holdings (Gold / Silver / MF) ───────────────────────
# These are NOT on yfinance, so we price them straight from the sheet's
# Present value column and keep them out of the equity (yfinance) pipeline.
def _norm_htype(v):
    s = str(v).strip().lower()
    if s == "gold":   return "Gold"
    if s == "silver": return "Silver"
    if s in ("mf", "mutual fund", "mutual funds"): return "MF"
    return "Stocks"

import re as _re_ne
def _clean_ne(t):
    return _re_ne.sub(r'-[A-Z]$', '', str(t).strip())

SECTOR_FOR_TYPE = {"Gold": "Gold", "Silver": "Silver", "MF": "Mutual Fund"}
nonequity_df = pd.DataFrame()
nonequity_tickers = set()
if "holding_type" in df.columns:
    _ht = df["holding_type"].map(_norm_htype)
    nonequity_df = df[_ht != "Stocks"].copy()
    if not nonequity_df.empty:
        nonequity_df["holding_type"] = nonequity_df["holding_type"].map(_norm_htype)
        nonequity_tickers = set(_clean_ne(s) for s in nonequity_df["symbol"])
        # Drop them from the equity dataframe (priced from sheet instead)
        df = df[_ht == "Stocks"].copy()
        print(f"[INFO] Holding non-equity rows for {len(nonequity_tickers)} tickers "
              f"(Gold/Silver/MF) priced from the sheet.")

# Strip Zerodha risk-indicator suffixes like -T, -X, -E, -B, -Z etc.
# e.g. MODISONLTD-T → MODISONLTD, LAKSELEC-X → LAKSELEC
import re as _re_suffix
df["symbol"] = df["symbol"].astype(str).str.replace(r'-[A-Z]$', '', regex=True)

# Filter valid rows
df = df[df["symbol"].notna()]
df = df[~df["symbol"].astype(str).str.contains(" ")]          # remove mutual fund rows
df = df[df["qty"].apply(lambda x: str(x).replace(".", "").isdigit())]  # numeric qty only
df = df[~df["symbol"].astype(str).str.match(r'^\d+(\.\d+)?$')]  # reject purely numeric symbols (Excel errors like 7.0, 26.0) but allow 3MINDIA
df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
df["buy_avg"] = pd.to_numeric(df["buy_avg"], errors="coerce")
df = df.dropna(subset=["qty", "buy_avg"])

# ── Aggregate by ticker across accounts ──────────────────────────────────────
# The sheet now lists the same stock once per ACCOUNT. Collapse to one row per
# ticker (total qty + buy-value-weighted average buy price) and remember the
# per-account split so the dashboard can show it. df["symbol"] is already suffix
# stripped above, so it doubles as the canonical (clean) ticker key.
if "buy_value" in df.columns:
    df["buy_value"] = pd.to_numeric(df["buy_value"], errors="coerce")
    df["buy_value"] = df["buy_value"].fillna(df["qty"] * df["buy_avg"])
else:
    df["buy_value"] = df["qty"] * df["buy_avg"]

accounts_map = {}
if "account" in df.columns:
    for _, r in df.iterrows():
        tk = str(r["symbol"]).strip()
        accounts_map.setdefault(tk, []).append({
            "name": str(r["account"]).strip(),
            "qty": float(r["qty"]),
            "buy_avg": round(float(r["buy_avg"]), 2),
            "invested": round(float(r["buy_value"]), 2),
        })
    for tk in accounts_map:
        accounts_map[tk].sort(key=lambda a: -a["invested"])

agg_rows = []
for tk, g in df.groupby("symbol", sort=False):
    tot_qty = float(g["qty"].sum())
    tot_bv = float(g["buy_value"].sum())
    wavg = round(tot_bv / tot_qty, 4) if tot_qty else 0.0
    is_mb = ("must_buy" in g.columns and
             any(str(v).strip().upper() == "MUSTBUY" for v in g["must_buy"]))
    agg_rows.append({"symbol": str(tk).strip(), "qty": tot_qty, "buy_avg": wavg,
                     "must_buy": "MUSTBUY" if is_mb else ""})

portfolio = pd.DataFrame(agg_rows).reset_index(drop=True)
print(f"[INFO] Found {len(portfolio)} unique holdings across "
      f"{sum(len(v) for v in accounts_map.values()) or len(portfolio)} account rows\n")

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
# Keep non-equity (Gold/Silver/MF) tickers in the "known" set so the removal
# logic below does not wipe their stubs from stocks.json.
portfolio_tickers |= nonequity_tickers

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

# NOTE: We intentionally do NOT delete stocks from stocks.json when a ticker
# leaves the Google Sheet. Positions (qty / value) are rebuilt from the sheet
# via prices.json each run, but the qualitative analysis (moat, conviction,
# thesis, etc.) must persist forever so it always stays on the Deep Analysis
# tab — even for holdings that are no longer in the current portfolio.
# The stock simply becomes an "orphan" analysis card with no live position.
not_in_portfolio = [s.get("ticker") for s in stocks if s.get("ticker") not in portfolio_tickers]
if not_in_portfolio:
    print(f"[INFO] Keeping qualitative analysis for {len(not_in_portfolio)} "
          f"stock(s) no longer in the sheet: {', '.join(str(t) for t in not_in_portfolio)}\n")

# ── Fetch prices ──────────────────────────────────────────────────────────────
prices = {}
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# Build lookup of buy_avg and qty from portfolio (use clean tickers as keys)
def _is_mustbuy(row, clean_sym):
    col_flag = ("must_buy" in portfolio.columns and str(row["must_buy"]).strip().upper() == "MUSTBUY")
    return bool(col_flag or (clean_sym.strip().upper() in MUSTBUY_SET))

portfolio_map = {
    _clean_ticker(row["symbol"]): {"qty": float(row["qty"]), "buy_avg": float(row["buy_avg"]),
                                    "must_buy": _is_mustbuy(row, _clean_ticker(row["symbol"]))}
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
    ret_1w = None
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
    fetched_mover_z = None
    fetched_movers = None
    fetched_movers_w = None
    fetched_movers_m = None
    fetched_movers_alloc = None
    fetched_vol_week_ratio = None
    fetched_vol_month_ratio = None
    fetched_ath_pct = None
    fetched_atl_pct = None
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
            
            # Fetch full historical data (max) for returns + true all-time high/low
            hist = ticker_obj.history(period="max")
            
            if not hist.empty and len(hist) > 1:
                curr_price = hist['Close'].iloc[-1]
                ltp = round(float(curr_price), 2)
                
                # Calculate returns based on available historical data
                # 1-day return
                if len(hist) >= 2:
                    ret_1d = round(((curr_price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100), 2)
                
                # 1-week return (~5 trading days)
                if len(hist) >= 6:
                    ret_1w = round(((curr_price - hist['Close'].iloc[-6]) / hist['Close'].iloc[-6] * 100), 2)
                
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

                # All-time high / low (from full history) — % from ATH (<=0) and % above ATL (>=0)
                try:
                    ath_v = float(hist['Close'].max())
                    atl_v = float(hist['Close'].min())
                    if ath_v > 0:
                        fetched_ath_pct = round((curr_price - ath_v) / ath_v * 100, 2)
                    if atl_v > 0:
                        fetched_atl_pct = round((curr_price - atl_v) / atl_v * 100, 2)
                except Exception:
                    pass
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
                        # Movers v4: volume + momentum, LIFETIME (all-time) vs 52-week levels
                        if avg_30d > 0 and ret_1d is not None:
                            rvol = today_vol / avg_30d
                            ar = abs(ret_1d)
                            cclose = float(hist['Close'].iloc[-1])
                            near_high = bool(fetched_week52_high and cclose >= 0.98 * fetched_week52_high)
                            near_low  = bool(fetched_week52_low  and cclose <= 1.02 * fetched_week52_low)
                            near_ath  = bool(fetched_ath_pct is not None and fetched_ath_pct >= -2)
                            near_atl  = bool(fetched_atl_pct is not None and fetched_atl_pct <= 2)
                            strong_up = rvol >= 3 and ret_1d >= 3
                            strong_dn = rvol >= 3 and ret_1d <= -3
                            if   near_ath and strong_up:  fetched_movers = "\U0001f525"   # 🔥 lifetime high breakout
                            elif near_atl and strong_dn:  fetched_movers = "\U0001f9ca"   # 🧊 lifetime low breakdown
                            elif near_high and strong_up: fetched_movers = "\U0001f680"   # 🚀 52-week high breakout
                            elif near_low  and strong_dn: fetched_movers = "\u2744\ufe0f" # ❄️ 52-week low breakdown
                            elif rvol >= 10 and ar >= 3:
                                fetched_movers = "\u26a0\ufe0f"  # ⚠️ SUSPECT — abnormal volume spike (>=10x) with |day|>=3%, overrides V/V+P/P
                            else:
                                _V = rvol >= 4 and ar >= 3
                                _P = rvol >= 3 and ar >= 6
                                if   _V and _P: fetched_movers = "V+P"
                                elif _V:        fetched_movers = "V"
                                elif _P:        fetched_movers = "P"
                                else:           fetched_movers = "No"

                        # Weekly / Monthly volume ratios + breakout/breakdown (level-based)
                        vols = hist['Volume']
                        cclose2 = float(hist['Close'].iloc[-1])
                        def _vol_ratio(win, base_win):
                            if len(vols) < win + 3:
                                return None
                            recent = float(vols.tail(win).mean())
                            if len(vols) >= base_win + win:
                                base = float(vols.tail(base_win + win).iloc[:-win].mean())
                            else:
                                base = float(vols.iloc[:-win].mean())
                            return round(recent / base, 2) if base and base > 0 else None
                        fetched_vol_week_ratio  = _vol_ratio(5, 25)
                        fetched_vol_month_ratio = _vol_ratio(21, 126)
                        def _mover_tf(rv, ret, vol_t, up_t, dn_t, tr_vol, tr_up):
                            if rv is None or ret is None:
                                return None
                            na  = fetched_ath_pct is not None and fetched_ath_pct >= -2
                            nl  = fetched_atl_pct is not None and fetched_atl_pct <= 2
                            nh  = bool(fetched_week52_high and cclose2 >= 0.98 * fetched_week52_high)
                            nlo = bool(fetched_week52_low  and cclose2 <= 1.02 * fetched_week52_low)
                            up = rv >= vol_t and ret >= up_t
                            dn = rv >= vol_t and ret <= -dn_t
                            if na and up:  return "\U0001f525"
                            if nl and dn:  return "\U0001f9ca"
                            if nh and up:  return "\U0001f680"
                            if nlo and dn: return "\u2744\ufe0f"
                            at_high = na or nh
                            at_low  = nl or nlo
                            if (not at_high) and rv >= tr_vol and ret >=  tr_up: return "\U0001f4c8"  # 📈 trending up
                            if (not at_low)  and rv >= tr_vol and ret <= -tr_up: return "\U0001f4c9"  # 📉 trending down
                            return "No"
                        fetched_movers_w = _mover_tf(fetched_vol_week_ratio, ret_1w, 1.5, 8, 8, 1.3, 5)
                        fetched_movers_m = _mover_tf(fetched_vol_month_ratio, ret_1m, 1.3, 12, 12, 1.2, 8)
                        # Allocation-ACTION overlay (momentum x 200DMA trend context incl. Trend Score).
                        # 🏆 STRONG ADD · 💎 ADD · 🌱 START-SMALL · ⏳ HOLD (extended or pullback) · 🚨 REDUCE.
                        # Thresholds calibrated on the live portfolio; CALLED AFTER the 200DMA block below.
                        def _alloc(d, w, m, ext, slope, da, r1m, ts):
                            down = lambda t: t in ("\U0001f9ca", "\u2744\ufe0f", "\U0001f4c9")
                            up   = lambda t: t in ("\U0001f525", "\U0001f680", "\U0001f4c8")
                            hard_dn = lambda t: t in ("\U0001f9ca", "\u2744\ufe0f")  # new 52wk/lifetime low
                            m_up, m_dn = up(m), down(m)
                            w_up, w_dn = up(w), down(w)
                            up_cat = m_up or w_up
                            have_trend = ext is not None and slope is not None
                            strong_trend = (slope is not None and slope >= 1 and ext is not None and ext > 0
                                            and (da is None or da >= 7) and (ts is None or ts >= 70))
                            below_falling_ma = ext is not None and slope is not None and ext < -3 and slope < -1
                            # 1) REDUCE — genuine de-rating (Stage 4), not a mere pullback
                            if hard_dn(m) or below_falling_ma or (m_dn and not strong_trend):
                                return "\U0001f6a8"  # 🚨 REDUCE
                            # 2) Down-momentum but still above a rising/flat 200DMA → pullback → HOLD
                            if m_dn or w_dn:
                                return "\u23f3"  # ⏳ HOLD/watch
                            if not up_cat:
                                return ""
                            if (ext is not None and ext > 50) or (r1m is not None and r1m > 30):
                                return "\u23f3"  # ⏳ HOLD/TRIM
                            if m_up and have_trend and slope >= 1 and ext <= 20 and da is not None and da >= 9 and (r1m is None or r1m <= 20) and not w_dn:
                                return "\U0001f3c6"  # 🏆 STRONG ADD (low-risk sweet spot)
                            if m_up and have_trend and slope >= 1 and ext <= 40 and (r1m is None or r1m <= 20) and (da is None or da >= 6) and not w_dn:
                                return "\U0001f48e"  # 💎 ADD
                            if up_cat and (slope is None or slope >= -2) and (r1m is None or r1m <= 28):
                                return "\U0001f331"  # 🌱 START-SMALL
                            return ""

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

                        # Allocation action (needs the 200DMA context computed just above)
                        fetched_movers_alloc = _alloc(fetched_movers, fetched_movers_w, fetched_movers_m,
                                                      fetched_price_to_200dma_pct, fetched_dma200_slope_30d_pct,
                                                      fetched_days_above_200dma_10d, ret_1m, fetched_trend_score)
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
        "holding_type": "Stocks",
    }
    # Per-account holdings breakdown (same stock split across accounts)
    if sym in accounts_map:
        prices[sym]["accounts"] = accounts_map[sym]
    
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
    # Movers v4 (🔥 lifetime-high / 🚀 52wk-high / 🧊 lifetime-low / ❄️ 52wk-low / V+P / V / P / No)
    if fetched_movers is not None:
        prices[sym]["movers"] = fetched_movers
    if fetched_movers_w is not None:
        prices[sym]["movers_w"] = fetched_movers_w
    if fetched_movers_m is not None:
        prices[sym]["movers_m"] = fetched_movers_m
    if fetched_movers_alloc:
        prices[sym]["movers_alloc"] = fetched_movers_alloc
    if fetched_vol_week_ratio is not None:
        prices[sym]["vol_week_ratio"] = fetched_vol_week_ratio
    if fetched_vol_month_ratio is not None:
        prices[sym]["vol_month_ratio"] = fetched_vol_month_ratio
    # All-time high/low percentages
    if fetched_ath_pct is not None:
        prices[sym]["ath_pct"] = fetched_ath_pct
    if fetched_atl_pct is not None:
        prices[sym]["atl_pct"] = fetched_atl_pct
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
    if ret_1w is not None:
        prices[sym]["ret_1w"] = ret_1w
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

# ── Benchmark index returns (Nifty 50 / Smallcap 250 / Midcap 400) ──────────
# Stored under prices["_benchmarks"] for the dashboard's expandable Benchmarks panel.
# Yahoo Finance symbols for these NSE indices are not fully standardised, so we try
# a list of candidates per index and keep the first that returns history.
BENCHMARK_SYMBOLS = {
    "nifty50":     ["^NSEI"],                                  # Nifty 50 index (full history)
    "smallcap250": ["HDFCSML250.NS", "MOSMALL250.NS"],         # Nifty Smallcap 250 (ETF proxy; ~3y history, no 5y on Yahoo)
    "midcap400":   ["MID150BEES.NS", "MIDCAPETF.NS", "NIFTYMIDCAP150.NS", "^NSEMDCP50"],  # Nifty Midcap 150 (broad-midcap proxy)
}

def _ret(hist, n):
    if len(hist) > n:
        base = hist['Close'].iloc[-1 - n]
        if base:
            return round((hist['Close'].iloc[-1] - base) / base * 100, 2)
    return None

# Index-fund NAV source (AMFI via mfapi.in) — used to fill long-term returns that
# the recently-launched ETFs don't have history for (e.g. Smallcap 250 5-year).
def _mf_returns(scheme_code):
    import requests as _rq
    from datetime import datetime as _dt, timedelta as _td
    d = _rq.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=30).json()
    pts = []
    for x in d.get("data", []):
        try:
            v = float(x["nav"])
            if v > 0:
                pts.append((_dt.strptime(x["date"], "%d-%m-%Y"), v))
        except Exception:
            pass
    if len(pts) < 2:
        return {}
    pts.sort()
    last_date, latest = pts[-1]
    def r(days):
        target = last_date - _td(days=days)
        c = [p for p in pts if p[0] <= target]
        if not c:
            return None
        base = c[-1][1]
        return round((latest - base) / base * 100, 2) if base else None
    prev = pts[-2][1]
    return {
        "ret_1d": round((latest - prev) / prev * 100, 2) if prev else None,
        "ret_1m": r(30), "ret_1y": r(365), "ret_3y": r(365 * 3), "ret_5y": r(365 * 5),
    }

# Fallback index-fund scheme codes for periods the ETF can't cover
BENCHMARK_MF_FALLBACK = {
    "smallcap250": 148519,   # Nippon India Nifty Smallcap 250 Index Fund (history since Oct 2020)
}

benchmarks = {}
for key, candidates in BENCHMARK_SYMBOLS.items():
    for cand in candidates:
        try:
            h = yf.Ticker(cand).history(period="5y")
            if h is None or h.empty or len(h) < 2:
                continue
            benchmarks[key] = {
                "symbol": cand,
                "ret_1d": _ret(h, 1),
                "ret_1m": _ret(h, 21),
                "ret_1y": _ret(h, 252),
                "ret_3y": _ret(h, 756),
                "ret_5y": _ret(h, 1200),
            }
            print(f"[INFO] Benchmark {key}: {cand} fetched")
            break
        except Exception as e:
            print(f"[WARN] Benchmark {key} candidate {cand} failed: {e}")

# Fill any missing long-term returns from the index-fund NAV source
for key, scheme in BENCHMARK_MF_FALLBACK.items():
    row = benchmarks.get(key)
    if not row or any(row.get(f) is None for f in ("ret_3y", "ret_5y")):
        try:
            mf = _mf_returns(scheme)
            if mf:
                if not row:
                    row = {"symbol": f"MF:{scheme}"}
                    benchmarks[key] = row
                for f in ("ret_1d", "ret_1m", "ret_1y", "ret_3y", "ret_5y"):
                    if row.get(f) is None and mf.get(f) is not None:
                        row[f] = mf[f]
                print(f"[INFO] Benchmark {key}: filled long-term returns from index fund {scheme}")
        except Exception as e:
            print(f"[WARN] Benchmark {key} MF fallback {scheme} failed: {e}")

if benchmarks:
    prices["_benchmarks"] = benchmarks
elif isinstance(fallback_prices, dict) and fallback_prices.get("_benchmarks"):
    # Keep previous benchmark data if this run could not fetch any
    prices["_benchmarks"] = fallback_prices["_benchmarks"]

# ── Inject non-equity holdings (Gold / Silver / MF) priced from the sheet ────
if not nonequity_df.empty:
    ne = nonequity_df.copy()
    ne["tk"] = ne["symbol"].map(_clean_ne)
    ne["qty"] = pd.to_numeric(ne["qty"], errors="coerce")
    ne["buy_avg"] = pd.to_numeric(ne["buy_avg"], errors="coerce")
    if "buy_value" in ne.columns:
        ne["buy_value"] = pd.to_numeric(ne["buy_value"], errors="coerce").fillna(ne["qty"] * ne["buy_avg"])
    else:
        ne["buy_value"] = ne["qty"] * ne["buy_avg"]
    if "present_value" in ne.columns:
        ne["present_value"] = pd.to_numeric(ne["present_value"], errors="coerce")
    else:
        ne["present_value"] = pd.NA
    ne = ne.dropna(subset=["qty"])
    ne = ne[ne["qty"] > 0]

    stock_tickers_now = {s.get("ticker") for s in stocks}
    ne_added = 0
    for tk, g in ne.groupby("tk"):
        tot_qty = float(g["qty"].sum())
        if tot_qty <= 0:
            continue
        tot_bv = float(pd.to_numeric(g["buy_value"], errors="coerce").fillna(0).sum())
        tot_pv = float(pd.to_numeric(g["present_value"], errors="coerce").fillna(0).sum())
        wavg = round(tot_bv / tot_qty, 4) if tot_qty else 0.0
        htype = g["holding_type"].iloc[0]
        accts = [{
            "name": str(r["account"]).strip() if "account" in g.columns else "",
            "qty": float(r["qty"]),
            "buy_avg": round(float(r["buy_avg"]), 2) if pd.notna(r["buy_avg"]) else 0.0,
            "invested": round(float(r["buy_value"]), 2) if pd.notna(r["buy_value"]) else 0.0,
        } for _, r in g.iterrows()]
        accts.sort(key=lambda a: -a["invested"])
        prices[tk] = {
            "ltp": round(tot_pv / tot_qty, 4) if tot_qty else None,
            "buy_avg": round(wavg, 2),
            "quantity": tot_qty,
            "pnl_pct": round((tot_pv - tot_bv) / tot_bv * 100, 2) if tot_bv else None,
            "pnl_abs": round(tot_pv - tot_bv, 2),
            "updated": now_utc,
            "must_buy": False,
            "holding_type": htype,
            "accounts": accts,
        }
        if tk not in stock_tickers_now:
            stocks.append({
                "ticker": tk,
                "name": str(g["symbol"].iloc[0]).strip(),
                "sector": SECTOR_FOR_TYPE.get(htype, htype),
                "nse_symbol": tk,
                "moat_type": "\u2014",
                "moat_class": "na",
                "conviction": 0,
                "holding_type": htype,
                "is_non_equity": True,
            })
            stock_tickers_now.add(tk)
        ne_added += 1
    print(f"[INFO] Added {ne_added} non-equity (Gold/Silver/MF) holdings priced from the sheet.")

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
