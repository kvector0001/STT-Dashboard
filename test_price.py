#!/usr/bin/env python3
"""Quick test to verify PARKHOSPS/PARKHOTELS pricing"""
import yfinance as yf
import json

# Test symbols for PARKHOSPS / PARKHOTELS
test_symbols = [
    "PARKHOSPS.NS",
    "PARKHOTELS.NS", 
    "PARKHOTELS.BO",
    "PARKHOSPS.BO",
]

print("Testing PARKHOSPS / PARKHOTELS symbols:\n")
for sym in test_symbols:
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            print(f"✓ {sym:20} → ₹{price:,.2f}")
        else:
            # Try fast_info
            fi = ticker.fast_info
            price = fi.last_price
            if price and price > 0:
                print(f"✓ {sym:20} → ₹{price:,.2f} (fast_info)")
            else:
                print(f"✗ {sym:20} → No data")
    except Exception as e:
        print(f"✗ {sym:20} → Error: {str(e)[:40]}")

# Now test the actual fetch logic
print("\n" + "="*60)
print("Testing with buy_avg from portfolio:")
print("="*60)
buy_avg = 158.81
for sym in ["PARKHOTELS.NS", "PARKHOTELS.BO"]:
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1d")
        if not hist.empty:
            ltp = hist['Close'].iloc[-1]
            pnl_pct = (ltp - buy_avg) / buy_avg * 100
            print(f"{sym:20} LTP: ₹{ltp:>8,.2f}  |  P&L: {pnl_pct:+.2f}%")
    except:
        pass
