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

# ── Path resolution (local OneDrive vs GitHub Actions) ──────────────────────
LOCAL_PATH = r"C:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard\Portfolio.xlsx"
LOCAL_DATA_PATH = r"C:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard\Data\Portfolio.xlsx"
REPO_PATH = "data/portfolio.xlsx"

if os.path.exists(REPO_PATH):
    portfolio_file = REPO_PATH
elif os.path.exists(LOCAL_PATH):
    portfolio_file = LOCAL_PATH
elif os.path.exists(LOCAL_DATA_PATH):
    portfolio_file = LOCAL_DATA_PATH
else:
    # Try any xlsx in current folder's Data subfolder
    found = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Data", "*.xlsx"))
    if not found:
        found = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "*.xlsx"))
    if found:
        portfolio_file = found[0]
    else:
        raise FileNotFoundError(
            "Portfolio.xlsx not found. Check path or add data/portfolio.xlsx to repo."
        )

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

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            fi = ticker_obj.fast_info
            price = fi.last_price
            if price and price > 0:
                ltp = round(float(price), 2)
                # Try to get name/sector for placeholder stocks
                try:
                    info = ticker_obj.info
                    fetched_name = info.get("longName") or info.get("shortName")
                    fetched_sector = info.get("sector") or info.get("industry")
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

    prices[sym] = {
        "ltp": ltp,
        "buy_avg": buy_avg,
        "quantity": qty,
        "pnl_pct": pnl_pct,
        "pnl_abs": pnl_abs,
        "updated": now_utc,
    }

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
