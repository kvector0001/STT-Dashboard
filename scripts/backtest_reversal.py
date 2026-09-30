"""Backtest the dashboard's REVERSAL trigger (D / W / M) on daily data.

Universe = today's equity holdings in prices.json, so there is survivorship bias: judge the
signal against the SAME-universe baseline (all stock-days), not in absolute terms.
A signal fires on day t; entry is the NEXT close (t+1), so there is no look-ahead.
Returns are excess vs the stock's size index (Nifty 50 / Midcap 150 / Smallcap 250).
Indicator formulas mirror scripts/fetch_prices.py exactly.
"""
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from yahoo_symbols import yahoo_symbol_candidates

ROOT = Path(__file__).resolve().parents[1]
BENCH = {"large": "^NSEI", "mid": "NIFTYMIDCAP150.NS", "small": "NIFTYSMLCAP250.NS"}
HORIZONS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126}
COOLDOWN = 20      # a new event needs 20 trading days without the same trigger
CONFIRM_AT = 21    # two-stage check: judge the surge 21 trading days after entry
SURGE_WIN = {"D": 1, "W": 5, "M": 20, "ANY": 5}
LIVE = {"d_ret": 5, "d_vol": 3, "w_ret": 12, "w_vol": 3, "m_ret": 15}


def _bucket(m):
    return "large" if m >= 50000 else "mid" if m >= 15000 else "small"


def _naive(idx):
    idx = pd.to_datetime(idx)
    return (idx.tz_localize(None) if idx.tz is not None else idx).normalize()


def _col(frame, sym, field):
    try:
        s = frame[(sym, field)] if isinstance(frame.columns, pd.MultiIndex) else frame[field]
    except KeyError:
        return pd.Series(dtype=float)
    return pd.to_numeric(s, errors="coerce")


def load_universe():
    prices = json.load(open(ROOT / "prices.json", encoding="utf-8"))
    nse = {s.get("ticker"): s.get("nse_symbol") for s in json.load(open(ROOT / "stocks.json", encoding="utf-8")) if s.get("ticker")}
    uni = {}
    for t, p in prices.items():
        if t.startswith("_") or not isinstance(p, dict) or p.get("ltp") is None:
            continue
        if (p.get("holding_type") or "Stocks") != "Stocks":
            continue
        uni[t] = {"cands": yahoo_symbol_candidates(t, nse.get(t)), "mcap": p.get("mcap_cr") or 0, "snap": p}
    return uni


def download(uni, start):
    first = {t: u["cands"][0] for t, u in uni.items()}
    print(f"Downloading {len(first)} stock histories from {start}...")
    frame = yf.download(sorted(set(first.values())), start=start, group_by="ticker", auto_adjust=True, threads=True, progress=False)
    hist = {}
    for t, sym in first.items():
        h = pd.DataFrame({"Close": _col(frame, sym, "Close"), "Volume": _col(frame, sym, "Volume")}).dropna(subset=["Close"])
        if len(h) < 300:
            for alt in uni[t]["cands"][1:]:
                try:
                    h2 = yf.Ticker(alt).history(start=start, auto_adjust=True)[["Close", "Volume"]].dropna(subset=["Close"])
                except Exception:
                    continue
                if len(h2) >= 300:
                    h = h2
                    break
        if len(h) >= 300:
            h.index = _naive(h.index)
            hist[t] = h[~h.index.duplicated(keep="last")]
    bf = yf.download(list(BENCH.values()), start=start, group_by="ticker", auto_adjust=True, threads=True, progress=False)
    bench = {}
    for k, sym in BENCH.items():
        s = _col(bf, sym, "Close").dropna()
        s.index = _naive(s.index)
        bench[k] = s[~s.index.duplicated(keep="last")]
    return hist, bench


def indicators(h):
    c, v = h["Close"], h["Volume"]
    x = pd.DataFrame(index=h.index)
    x["close"] = c
    x["r1d"] = c.pct_change() * 100
    x["r1w"] = (c / c.shift(5) - 1) * 100
    x["r1m"] = (c / c.shift(20) - 1) * 100
    # min_periods: pandas .mean() in fetch_prices skips missing bars, so a single gap must not blank the ratio
    x["vd"] = v / v.shift(1).rolling(30, min_periods=20).mean()
    x["vw"] = v.rolling(5, min_periods=3).mean() / v.shift(5).rolling(25, min_periods=15).mean()
    x["ath"] = (c / c.cummax() - 1) * 100
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    x["p50"] = (c / sma50 - 1) * 100
    x["p200"] = (c / sma200 - 1) * 100
    x["slope200"] = (sma200 / sma200.shift(30) - 1) * 100
    return x


def flags(x, th):
    d = (x["r1d"] >= th["d_ret"]) & (x["vd"] >= th["d_vol"])
    w = (x["r1w"] >= th["w_ret"]) & (x["vw"] >= th["w_vol"])
    m = x["r1m"] > th["m_ret"]
    return {"D": d, "W": w, "M": m, "ANY": d | w | m}


def first_fires(flag, lo):
    out, last = [], -10**9
    for i in np.flatnonzero(flag.fillna(False).values):
        if i - last > COOLDOWN and i >= lo:
            out.append(i)
        last = i
    return out


def _fwd(c, b, e, k):
    if e + k >= len(c) or np.isnan(b[e]) or np.isnan(b[e + k]):
        return np.nan
    return ((c[e + k] / c[e] - 1) - (b[e + k] / b[e] - 1)) * 100


def event_rows(t, tf, x, b, lo, th=LIVE, full=True):
    c, n = x["close"].values, len(x)
    rows = []
    for i in first_fires(flags(x, th)[tf], lo):
        e = i + 1
        if e >= n:
            continue
        r = {"ticker": t, "tf": tf, "date": x.index[i].date()}
        for hz, k in HORIZONS.items():
            r["ex_" + hz] = _fwd(c, b, e, k)
        if not full:
            rows.append(r)
            continue
        for f in ("r1d", "r1w", "r1m", "ath", "p200", "slope200"):
            r[f] = x[f].iat[i]
        s0 = max(0, i - SURGE_WIN[tf])
        pre_low, surge_high = c[max(0, s0 - 10):s0 + 1].min(), c[s0:i + 1].max()
        rng = surge_high - pre_low
        fut = c[i + 1:i + 43]
        if len(fut) >= 21 and rng > 0:
            r["broke_low"] = bool((fut < pre_low).any())
            r["giveback"] = (surge_high - fut.min()) / rng
        j = e + CONFIRM_AT
        if j < n and rng > 0:
            win = c[i + 1:j + 1]
            held = win.min() >= pre_low
            gb = (surge_high - win.min()) / rng
            trend_ok = (x["p200"].iat[j] >= 0) or (x["slope200"].iat[j] > x["slope200"].iat[i])
            if (not held) or gb > 0.75:
                r["stage"] = "Failed"
            elif gb <= 0.5 and x["p50"].iat[j] >= 0 and trend_ok:
                r["stage"] = "Confirmed"
            else:
                r["stage"] = "Unresolved"
            for hz, k in HORIZONS.items():
                r["post_" + hz] = _fwd(c, b, j + 1, k)
        rows.append(r)
    return rows


def baseline(xs, benches, lo_dates):
    out = {hz: [] for hz in HORIZONS}
    for t, x in xs.items():
        c, b = x["close"], benches[t]
        lo = lo_dates[t]
        for hz, k in HORIZONS.items():
            ex = ((c.shift(-(1 + k)) / c.shift(-1) - 1) - (b.shift(-(1 + k)) / b.shift(-1) - 1)) * 100
            out[hz].append(ex.iloc[lo:].dropna().values)
    return {hz: np.concatenate(v) if v else np.array([]) for hz, v in out.items()}


def stats(vals):
    v = pd.Series(vals).dropna()
    if not len(v):
        return "n=0"
    return f"n={len(v):>4} | mean {v.mean():+6.1f}% | median {v.median():+6.1f}% | beat index {100 * (v > 0).mean():4.0f}%"


def parity(uni, xs):
    agree = {"r1w": 0, "r1m": 0, "vw": 0}
    flag_agree, total, mism = 0, 0, []
    for t, x in xs.items():
        s = uni[t]["snap"]
        try:
            ts = pd.Timestamp(str(s.get("updated"))[:16]) + pd.Timedelta(hours=5, minutes=30)  # stored in UTC
        except Exception:
            continue
        # a snapshot taken before the 09:15 IST open reflects the previous session's close
        cutoff = ts.normalize() if (ts.hour, ts.minute) < (9, 15) else ts.normalize() + pd.Timedelta(days=1)
        prior = x.index[x.index < cutoff]
        if not len(prior):
            continue
        d = prior[-1]
        row, total = x.loc[d], total + 1
        for k, f, tol in (("r1w", "ret_1w", 1.0), ("r1m", "ret_1m", 1.0), ("vw", "vol_week_ratio", 0.15)):
            sv = s.get(f)
            if sv is not None and not np.isnan(row[k]) and abs(row[k] - sv) <= max(tol, abs(sv) * 0.05):
                agree[k] += 1
        snap_w = (s.get("ret_1w") or -99) >= 12 and (s.get("vol_week_ratio") or 0) >= 3
        snap_m = (s.get("ret_1m") or -99) > 15
        bt_w = bool(row["r1w"] >= 12 and row["vw"] >= 3)
        bt_m = bool(row["r1m"] > 15)
        if (snap_w, snap_m) == (bt_w, bt_m):
            flag_agree += 1
        else:
            mism.append(f"{t} dash W/M={int(snap_w)}{int(snap_m)} backtest={int(bt_w)}{int(bt_m)} "
                        f"(dash 1W {s.get('ret_1w')} vol {s.get('vol_week_ratio')} 1M {s.get('ret_1m')} | "
                        f"bt 1W {row['r1w']:.1f} vol {row['vw']:.2f} 1M {row['r1m']:.1f})")
    return total, agree, flag_agree, mism


def main():
    ap = argparse.ArgumentParser(description="Backtest the REVERSAL (D/W/M) trigger.")
    ap.add_argument("--years", type=int, default=5, help="Evaluation window in years (default 5).")
    args = ap.parse_args()
    today = date.today()
    eval_start = pd.Timestamp(today - timedelta(days=365 * args.years))
    uni = load_universe()
    hist, bench = download(uni, "2005-01-01")
    xs, benches, lo_dates = {}, {}, {}
    for t, h in hist.items():
        x = indicators(h)
        xs[t] = x
        benches[t] = bench[_bucket(uni[t]["mcap"])].reindex(x.index).ffill()
        lo_dates[t] = int(max(x.index.searchsorted(eval_start), 230))
    print(f"Histories: {len(xs)}/{len(uni)} stocks | eval window {eval_start.date()} → {today}")

    lines = [f"# Reversal trigger backtest — {today}", "",
             f"Universe: {len(xs)} current equity holdings (survivorship bias → compare to baseline). "
             f"Window: {eval_start.date()} → {today}. Entry next close. Excess vs size index. Cooldown {COOLDOWN} days.", ""]

    total, agree, fa, mism = parity(uni, xs)
    lines += ["## 1. Do the thresholds compute the same as the dashboard?",
              f"Compared {total} stocks against the dashboard snapshot (24 Sep 2026 14:40 IST, intraday — so small gaps vs the final close are expected).",
              f"- 1W return within tolerance: {agree['r1w']}/{total}",
              f"- 1M return within tolerance: {agree['r1m']}/{total}",
              f"- Weekly volume ratio within tolerance: {agree['vw']}/{total}",
              f"- W and M trigger flags identical: {fa}/{total}"] + [f"  - mismatch: {m}" for m in mism[:15]] + [""]

    base = baseline(xs, benches, lo_dates)
    ev = pd.DataFrame([r for t, x in xs.items() for tf in ("D", "W", "M", "ANY")
                       for r in event_rows(t, tf, x, benches[t].values, lo_dates[t])])
    lines += ["## 2. Current thresholds vs baseline (excess return after entry)", "```"]
    for hz in HORIZONS:
        lines.append(f"{hz}  BASELINE (all stock-days)  {stats(base[hz])}")
        for tf in ("D", "W", "M", "ANY"):
            lines.append(f"{hz}  {tf:<4}                      {stats(ev.loc[ev.tf == tf, 'ex_' + hz])}")
        lines.append("")
    lines += ["```", "", "## 3. Dead-cat diagnostics (next 42 trading days after the signal)", "```"]
    for tf in ("D", "W", "M", "ANY"):
        g = ev[ev.tf == tf]
        lines.append(f"{tf:<4} n={len(g):>4} | broke pre-surge low {100 * g['broke_low'].mean():4.0f}% | "
                     f"gave back >50% of surge {100 * (g['giveback'] > 0.5).mean():4.0f}%")
    lines += ["```", "", "## 4. Does context matter? (ANY trigger, 3M excess)", "```"]
    a = ev[ev.tf == "ANY"]
    for label, mask in (("Deep below ATH (< -40%)", a.ath < -40), ("Not deep (>= -40%)", a.ath >= -40),
                        ("Below 200-DMA", a.p200 < 0), ("Above 200-DMA", a.p200 >= 0),
                        ("Below FALLING 200-DMA", (a.p200 < 0) & (a.slope200 < 0)),
                        ("Above RISING 200-DMA", (a.p200 >= 0) & (a.slope200 > 0))):
        lines.append(f"{label:<26} 1M {stats(a.loc[mask, 'ex_1M'])}")
        lines.append(f"{'':<26} 3M {stats(a.loc[mask, 'ex_3M'])}")
    lines += ["```", "", f"## 5. Two-stage test: judged {CONFIRM_AT} days after entry, returns measured AFTER that", "```"]
    for st in ("Confirmed", "Unresolved", "Failed"):
        g = a[a.get("stage") == st]
        lines.append(f"{st:<11} 1M {stats(g['post_1M'])}")
        lines.append(f"{'':<11} 3M {stats(g['post_3M'])}")
        lines.append(f"{'':<11} 6M {stats(g['post_6M'])}")
    lines += ["```", "", "## 6. Threshold sensitivity (1M and 3M excess)", "```"]
    grid = [("D", dict(LIVE, d_ret=r, d_vol=v)) for r in (3, 5, 8) for v in (2, 3, 5)] + \
           [("W", dict(LIVE, w_ret=r, w_vol=v)) for r in (8, 12, 16) for v in (2, 3, 5)] + \
           [("M", dict(LIVE, m_ret=r)) for r in (10, 15, 20, 25)]
    for tf, th in grid:
        g = pd.DataFrame([r for t, x in xs.items() for r in event_rows(t, tf, x, benches[t].values, lo_dates[t], th, full=False)])
        lab = {"D": f"D 1D>={th['d_ret']}% vol>={th['d_vol']}x", "W": f"W 1W>={th['w_ret']}% vol>={th['w_vol']}x", "M": f"M 1M>{th['m_ret']}%"}[tf]
        live = " (LIVE)" if th == LIVE else ""
        lines.append(f"{lab + live:<30} 1M {stats(g.get('ex_1M', []))}")
        lines.append(f"{'':<30} 3M {stats(g.get('ex_3M', []))}")
    lines.append("```")

    out = ROOT / "prompt_outputs" / f"reversal_backtest_{today}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    ev.to_csv(ROOT / "prompt_outputs" / f"reversal_backtest_events_{today}.csv", index=False)
    print("\n".join(lines))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
