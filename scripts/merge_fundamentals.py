#!/usr/bin/env python3
"""Merge qualitative fundamental analysis into stocks.json.

Usage: python scripts/merge_fundamentals.py <analysis.json>

<analysis.json> is a dict keyed by ticker. For each ticker, the matching
stocks.json entry is updated field-by-field (existing keys such as buy_avg and
Yahoo-sourced fundamentals are preserved unless explicitly overwritten). Tickers
not present in stocks.json are appended as new entries.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS = os.path.join(ROOT, "stocks.json")


def main(path):
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    with open(STOCKS, encoding="utf-8") as f:
        stocks = json.load(f)

    by_ticker = {s.get("ticker"): s for s in stocks if s.get("ticker")}
    updated, added = [], []
    for ticker, fields in data.items():
        if ticker.startswith("_"):
            continue
        entry = by_ticker.get(ticker)
        if entry is None:
            new_entry = {"ticker": ticker, "nse_symbol": ticker}
            new_entry.update(fields)
            stocks.append(new_entry)
            by_ticker[ticker] = new_entry
            added.append(ticker)
        else:
            entry.update(fields)
            updated.append(ticker)

    with open(STOCKS, "w", encoding="utf-8") as f:
        json.dump(stocks, f, indent=2, ensure_ascii=False)

    print(f"Updated {len(updated)}: {', '.join(sorted(updated)) or '-'}")
    print(f"Added {len(added)}: {', '.join(sorted(added)) or '-'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/merge_fundamentals.py <analysis.json>")
        sys.exit(1)
    main(sys.argv[1])
