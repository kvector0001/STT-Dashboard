"""
fetch_extended_data.py — Fetches fundamental and historical return data
Updates stocks.json with fundamental data and prices.json with returns.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf
import re

# ── Paths ──────────────────────────────────────────────────────────────────
STOCKS_PATH = "stocks.json"
PRICES_PATH = "prices.json"

def get_return(hist, days):
    if len(hist) < 2: return None
    current = hist['Close'].iloc[-1]
    # Find the index closest to 'days' ago
    idx = max(0, len(hist) - days - 1)
    past = hist['Close'].iloc[idx]
    if past == 0 or pd.isna(past): return None
    return round(((current / past) - 1) * 100, 2)

def fetch_all():
    if not os.path.exists(STOCKS_PATH):
        print("❌ stocks.json not found.")
        return

    with open(STOCKS_PATH, "r", encoding="utf-8") as f:
        stocks = json.load(f)

    # We also need prices.json to update it
    if os.path.exists(PRICES_PATH):
        with open(PRICES_PATH, "r", encoding="utf-8") as f:
            prices = json.load(f)
    else:
        prices = {}

    print(f"🚀 Fetching extended data for {len(stocks)} stocks...")

    for i, stock in enumerate(stocks):
        ticker = stock["ticker"]
        # Use ticker directly (like fetch_prices.py)
        yf_sym = ticker
        
        # Clean suffix for Yahoo
        clean_yf = re.sub(r'-[A-Z]$', '', yf_sym)
        
        # Try .NS then .BO
        t_obj = None
        for suffix in [".NS", ".BO"]:
            try:
                test_sym = clean_yf + suffix
                t_obj = yf.Ticker(test_sym)
                # Quick check if it exists
                if t_obj.fast_info.last_price > 0:
                    break
            except:
                t_obj = None

        if not t_obj:
            print(f"  [{(i+1):>3}/{len(stocks)}] ❌ {ticker} - Not found on Yahoo")
            continue

        print(f"  [{(i+1):>3}/{len(stocks)}] 📡 {ticker}...")

        try:
            # 1. Fundamentals
            info = t_obj.info
            stock["mcap_cr"] = round((info.get("marketCap", 0) or 0) / 10000000, 2)
            stock["pe"] = info.get("trailingPE")
            stock["roe"] = round((info.get("returnOnEquity", 0) or 0) * 100, 2)
            stock["ocf_cr"] = round((info.get("operatingCashflow", 0) or 0) / 10000000, 2)
            stock["debt_to_equity"] = info.get("debtToEquity")
            stock["eps"] = info.get("trailingEps")
            stock["book_value"] = info.get("bookValue")
            stock["div_yield"] = round((info.get("dividendYield", 0) or 0) * 100, 2)
            
            # Growth metrics
            stock["pat_cagr"] = round((info.get("earningsGrowth", 0) or 0) * 100, 2)
            stock["rev_cagr"] = round((info.get("revenueGrowth", 0) or 0) * 100, 2)

            # 2. Returns (Historical)
            # Fetch 5 years to cover all periods
            hist = t_obj.history(period="5y")
            if not hist.empty:
                prices_entry = prices.get(ticker, {})
                prices_entry["ret_1d"] = get_return(hist, 1)
                prices_entry["ret_1m"] = get_return(hist, 21)
                prices_entry["ret_6m"] = get_return(hist, 126)
                prices_entry["ret_1y"] = get_return(hist, 252)
                prices_entry["ret_3y"] = get_return(hist, 756)
                prices_entry["ret_5y"] = get_return(hist, 1260)
                
                # MCap Growth 3Y is same as Ret 3Y for relative comparison
                stock["mcap_3y"] = prices_entry["ret_3y"]
                
                prices[ticker] = prices_entry

        except Exception as e:
            print(f"  [{(i+1):>3}/{len(stocks)}] ⚠️ {ticker} - Info error: {e}")

        # Save every 10 stocks for progress
        if (i+1) % 10 == 0:
            with open(STOCKS_PATH, "w", encoding="utf-8") as f:
                json.dump(stocks, f, indent=2, ensure_ascii=False)
            with open(PRICES_PATH, "w", encoding="utf-8") as f:
                json.dump(prices, f, indent=2, ensure_ascii=False)
            print(f"  [Progress] Saved update at stock {i+1}")

    # Final Save update

if __name__ == "__main__":
    fetch_all()
