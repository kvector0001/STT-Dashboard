"""Scan the live Google Sheet for holdings whose analysis is still pending.

Read-only: downloads the sheet to a temp file (never overwrites
data/portfolio.xlsx) and compares equity tickers against every dataset the
dashboard loads — stocks.json (fundamentals), management_trust.json,
red_flags.json, peer_comparison.json (quality/rating) and peer_rank.json.
"""
import json
import os
import re
import tempfile

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GSHEET_URL = ("https://docs.google.com/spreadsheets/d/"
              "1TSn6HIdcsux4p8cdpU0fx78zKibyxFKnwUUZTHFKfNI/export?format=xlsx")
NON_EQUITY = {"cash", "gold", "silver", "mf", "mutual fund", "mutual funds"}


def find_col(df, keywords):
    for col in df.columns:
        c = str(col).lower().strip()
        if any(kw in c for kw in keywords):
            return col
    return None


def load(path, default):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean_ticker(sym):
    return re.sub(r"-[A-Z]$", "", str(sym).strip())


def sheet_equity_tickers():
    resp = requests.get(GSHEET_URL, timeout=60)
    resp.raise_for_status()
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with open(tmp, "wb") as f:
        f.write(resp.content)
    try:
        df = pd.read_excel(tmp, engine="openpyxl")
    finally:
        os.remove(tmp)

    sym_col = find_col(df, ["symbol", "ticker", "scrip", "stock"])
    type_col = find_col(df, ["type", "asset class", "category"])
    acct_col = find_col(df, ["account", "broker"])

    tickers = []
    for _, row in df.iterrows():
        sym = str(row.get(sym_col, "")).strip()
        if not sym or sym.lower() == "nan":
            continue
        if acct_col and str(row.get(acct_col, "")).strip().upper() == "TOTAL":
            continue
        htype = str(row.get(type_col, "")).strip().lower() if type_col else ""
        if htype in NON_EQUITY:
            continue
        if " " in sym:                      # mutual-fund names carry spaces
            continue
        if re.match(r"^\d+(\.\d+)?$", sym):  # reject purely numeric junk
            continue
        tickers.append(clean_ticker(sym))
    return sorted(set(tickers)), sym_col, type_col, acct_col


def is_pending_fundamentals(stock):
    if stock is None:
        return True
    moat_type = str(stock.get("moat_type", "")).strip().lower()
    moat = str(stock.get("moat", "")).strip().lower()
    return moat_type in ("", "pending") or moat.startswith("analysis pending")


def main():
    tickers, sym_col, type_col, acct_col = sheet_equity_tickers()

    stocks = load("stocks.json", [])
    stocks = stocks if isinstance(stocks, list) else stocks.get("stocks", [])
    stock_by_t = {s.get("ticker"): s for s in stocks if s.get("ticker")}
    mt = load("management_trust.json", {})
    rf = load("red_flags.json", {})
    pc = load("peer_comparison.json", {})
    pr = load("peer_rank.json", {})

    def has(d, t):
        return t in d

    report = []
    for t in tickers:
        missing = []
        if is_pending_fundamentals(stock_by_t.get(t)):
            missing.append("fundamentals")
        if not has(mt, t):
            missing.append("mgmt_trust")
        if not has(rf, t):
            missing.append("red_flags")
        if not has(pc, t):
            missing.append("quality")
        if not has(pr, t):
            missing.append("peer_rank")
        if missing:
            report.append((t, t in stock_by_t, missing))

    print(f"[cols] symbol={sym_col!r} type={type_col!r} account={acct_col!r}")
    print(f"Sheet equity tickers: {len(tickers)}")
    print(f"Pending in >=1 dataset: {len(report)}\n")

    brand_new = [t for t, in_json, _ in report if not in_json]
    print(f"NOT in stocks.json yet ({len(brand_new)}): {', '.join(brand_new) or '-'}\n")

    need_fund = [t for t, _, m in report if "fundamentals" in m]
    print(f"Need FUNDAMENTALS ({len(need_fund)}): {', '.join(need_fund) or '-'}\n")

    print("Full per-ticker breakdown:")
    for t, in_json, missing in report:
        tag = "" if in_json else "  [NEW]"
        print(f"  {t:<16}{tag}  missing: {', '.join(missing)}")

    print("\nBy dataset (pending count):")
    for key in ("fundamentals", "mgmt_trust", "red_flags", "quality", "peer_rank"):
        n = sum(1 for _, _, m in report if key in m)
        print(f"  {key:<14}: {n}")


if __name__ == "__main__":
    main()
