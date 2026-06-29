"""
One-off: populate true all-time ATH% and ATL% into prices.json without a full
re-fetch. Uses yfinance max history; % from ATH (<=0) and % above ATL (>=0)
relative to the current ltp already in prices.json. fetch_prices.py also
computes these on its normal run.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import yfinance as yf
except Exception as e:
    print("yfinance not available:", e); sys.exit(1)

stocks = json.load(open(os.path.join(ROOT, "stocks.json"), encoding="utf-8"))
prices = json.load(open(os.path.join(ROOT, "prices.json"), encoding="utf-8"))
nse = {s["ticker"]: (s.get("nse_symbol") or s["ticker"]) for s in stocks}

done = 0
fail = []
for sym, pdata in prices.items():
    if sym.startswith("_") or not isinstance(pdata, dict):
        continue
    nsym = nse.get(sym, sym)
    ltp = pdata.get("ltp")
    got = False
    for cand in [f"{nsym}.NS", f"{sym}.NS", f"{nsym}.BO", f"{sym}.BO"]:
        try:
            h = yf.Ticker(cand).history(period="max")
            if h is None or len(h) < 5:
                continue
            ath = float(h["Close"].max())
            atl = float(h["Close"].min())
            px = float(ltp) if ltp else float(h["Close"].iloc[-1])
            if ath > 0:
                pdata["ath_pct"] = round((px - ath) / ath * 100, 2)
            if atl > 0:
                pdata["atl_pct"] = round((px - atl) / atl * 100, 2)
            got = True
            done += 1
            break
        except Exception:
            continue
    if not got:
        fail.append(sym)

json.dump(prices, open(os.path.join(ROOT, "prices.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"populated ATH/ATL for {done} tickers; failed: {len(fail)}")
if fail:
    print("failed:", fail[:30])
