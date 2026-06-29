"""
apply_accounts.py — patch prices.json (and stocks.json) from the live Google Sheet.

Reads the "Portfolio" tab which has:
  - an "Account Name" column (same holding split across accounts),
  - a "Type" column classifying each row as Stocks / Gold / Silver / MF.

For every ticker it:
  - aggregates qty across accounts + buy-value-weighted average buy price,
  - stores the per-account split under prices.json[ticker]["accounts"],
  - records prices.json[ticker]["holding_type"]  (Stocks / Gold / Silver / MF).

Equity ("Stocks") holdings keep their yfinance ltp (pnl recomputed from it).
Non-equity holdings (Gold / Silver / MF) are NOT on yfinance, so they are priced
straight from the sheet (ltp = present_value / qty) and added to both prices.json
and stocks.json (as lightweight non-equity stubs) if missing.

Columns are located BY NAME so the sheet can be reordered safely. The spreadsheet
"TOTAL" summary row is excluded. Does NOT call yfinance — fast + safe to run while
the GitHub sync is unavailable.
"""

import io
import json
import os
import re
from datetime import datetime, timezone

import pandas as pd
import requests

GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TSn6HIdcsux4p8cdpU0fx78zKibyxFKnwUUZTHFKfNI/export?format=xlsx"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(BASE_DIR, "prices.json")
STOCKS_PATH = os.path.join(BASE_DIR, "stocks.json")

SECTOR_FOR_TYPE = {"Gold": "Gold", "Silver": "Silver", "MF": "Mutual Fund"}


def find_col(df, keywords):
    for col in df.columns:
        low = str(col).lower().strip()
        for kw in keywords:
            if kw in low:
                return col
    return None


def clean_ticker(t):
    return re.sub(r"-[A-Z]$", "", str(t).strip())


def norm_type(v):
    s = str(v).strip().lower()
    if s == "gold":
        return "Gold"
    if s == "silver":
        return "Silver"
    if s in ("mf", "mutual fund", "mutual funds"):
        return "MF"
    return "Stocks"  # default (incl. blank/NaN)


def main():
    print("[DOWNLOAD] Fetching Google Sheet...")
    r = requests.get(GSHEET_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="Portfolio", engine="openpyxl")

    acc_col = find_col(df, ["account"])
    sym_col = find_col(df, ["symbol", "ticker", "scrip", "stock"])
    qty_col = find_col(df, ["qty", "quantity", "shares", "units"])
    avg_col = find_col(df, ["buy avg", "buyavg", "avg price", "avg cost", "buy_avg", "avg"])
    bv_col = find_col(df, ["buy value", "buyvalue"])
    pv_col = find_col(df, ["present value", "current value", "market value"])
    type_col = find_col(df, ["type", "asset class", "category"])

    print(f"[INFO] Columns -> account={acc_col!r} symbol={sym_col!r} qty={qty_col!r} "
          f"buy_avg={avg_col!r} buy_value={bv_col!r} present={pv_col!r} type={type_col!r}")
    if not all([acc_col, sym_col, qty_col, avg_col]):
        raise SystemExit("[ERROR] Required columns not found by name.")

    keep = [acc_col, sym_col, qty_col, avg_col]
    names = ["account", "symbol", "qty", "buy_avg"]
    for c, n in [(bv_col, "buy_value"), (pv_col, "present_value"), (type_col, "type")]:
        if c:
            keep.append(c)
            names.append(n)
    df = df[keep].copy()
    df.columns = names

    # Drop TOTAL summary row and blanks (keep MF/Gold rows that contain spaces!)
    df = df[df["symbol"].notna() & df["account"].notna()]
    df = df[df["account"].astype(str).str.strip().str.upper() != "TOTAL"]

    df["tk"] = df["symbol"].map(clean_ticker)
    df = df[~df["tk"].str.match(r"^\d+(\.\d+)?$")]  # reject purely numeric symbols
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["buy_avg"] = pd.to_numeric(df["buy_avg"], errors="coerce")
    if "buy_value" not in df.columns:
        df["buy_value"] = df["qty"] * df["buy_avg"]
    df["buy_value"] = pd.to_numeric(df["buy_value"], errors="coerce").fillna(df["qty"] * df["buy_avg"])
    if "present_value" not in df.columns:
        df["present_value"] = pd.NA
    df["present_value"] = pd.to_numeric(df["present_value"], errors="coerce")
    if "type" not in df.columns:
        df["type"] = "Stocks"
    df = df.dropna(subset=["qty"])
    df = df[df["qty"] > 0]

    with open(PRICES_PATH, "r", encoding="utf-8") as f:
        prices = json.load(f)
    with open(STOCKS_PATH, "r", encoding="utf-8") as f:
        stocks = json.load(f)
    stock_tickers = {s.get("ticker") for s in stocks}

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    updated, added_nonequity, missing = 0, 0, []

    for tk, g in df.groupby("tk"):
        tot_qty = float(g["qty"].sum())
        if tot_qty <= 0:
            continue
        tot_bv = float(pd.to_numeric(g["buy_value"], errors="coerce").fillna(0).sum())
        tot_pv = float(pd.to_numeric(g["present_value"], errors="coerce").fillna(0).sum())
        wavg = round(tot_bv / tot_qty, 4) if tot_qty else 0.0

        types = [norm_type(v) for v in g["type"].tolist()]
        non_stock = [t for t in types if t != "Stocks"]
        htype = non_stock[0] if non_stock else "Stocks"

        accounts = [
            {
                "name": str(row["account"]).strip(),
                "qty": float(row["qty"]),
                "buy_avg": round(float(row["buy_avg"]), 2) if pd.notna(row["buy_avg"]) else 0.0,
                "invested": round(float(row["buy_value"]), 2) if pd.notna(row["buy_value"]) else 0.0,
            }
            for _, row in g.iterrows()
        ]
        accounts.sort(key=lambda a: -a["invested"])

        entry = prices.get(tk)
        if isinstance(entry, dict):
            # Existing (priced) holding — keep its ltp, refresh holdings fields.
            entry["quantity"] = tot_qty
            entry["buy_avg"] = round(wavg, 2)
            entry["accounts"] = accounts
            entry["holding_type"] = htype
            ltp = entry.get("ltp")
            if isinstance(ltp, (int, float)) and wavg:
                entry["pnl_abs"] = round((ltp - wavg) * tot_qty, 2)
                entry["pnl_pct"] = round((ltp - wavg) / wavg * 100, 2)
            updated += 1
        elif htype != "Stocks":
            # Non-equity (Gold/Silver/MF): not on yfinance — price from the sheet.
            ltp = round(tot_pv / tot_qty, 4) if tot_qty else None
            prices[tk] = {
                "ltp": ltp,
                "buy_avg": round(wavg, 2),
                "quantity": tot_qty,
                "pnl_abs": round(tot_pv - tot_bv, 2),
                "pnl_pct": round((tot_pv - tot_bv) / tot_bv * 100, 2) if tot_bv else None,
                "updated": now_utc,
                "must_buy": False,
                "accounts": accounts,
                "holding_type": htype,
            }
            if tk not in stock_tickers:
                stocks.append({
                    "ticker": tk,
                    "name": str(g["symbol"].iloc[0]).strip(),
                    "sector": SECTOR_FOR_TYPE.get(htype, htype),
                    "nse_symbol": tk,
                    "moat_type": "—",
                    "moat_class": "na",
                    "conviction": 0,
                    "holding_type": htype,
                    "is_non_equity": True,
                })
                stock_tickers.add(tk)
            added_nonequity += 1
        else:
            missing.append(tk)  # a Stock not yet priced — leave for the full sync

    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2, ensure_ascii=False)
    with open(STOCKS_PATH, "w", encoding="utf-8") as f:
        json.dump(stocks, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Updated {updated} equity tickers; added {added_nonequity} non-equity (Gold/Silver/MF).")
    if missing:
        print(f"[WARN] {len(missing)} stock tickers in sheet but not yet priced (run full sync): {missing}")


if __name__ == "__main__":
    main()
