"""Backtest the dashboard momentum signals without using future price data.

The universe is today's stocks.json, so results have survivorship bias. Signals
are sampled at month-end and entered at the next close to avoid look-ahead.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from momentum_classifier import GEM, TROPHY, classify_daily, classify_monthly, classify_weekly, overlay_alloc
from yahoo_symbols import yahoo_symbol_candidates


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = {
    "large": "^NSEI",
    "mid": "MID150BEES.NS",
    "small": "HDFCSML250.NS",
}
HORIZONS = {"1W": 5, "1M": 21, "2M": 42, "3M": 63, "6M": 126}


def _series(frame, symbol, field):
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        try:
            result = frame[(symbol, field)]
        except KeyError:
            try:
                result = frame[(field, symbol)]
            except KeyError:
                return pd.Series(dtype=float)
    else:
        result = frame.get(field, pd.Series(dtype=float))
    return pd.to_numeric(result, errors="coerce").dropna()


def _download_universe(stocks, start):
    symbol_map = {stock["ticker"]: yahoo_symbol_candidates(stock["ticker"], stock.get("nse_symbol"))[0] for stock in stocks}
    symbols = sorted(set(symbol_map.values()))
    print(f"Downloading {len(symbols)} stock histories...")
    frame = yf.download(symbols, start=start, group_by="ticker", auto_adjust=True, threads=True, progress=False)
    histories = {}
    for ticker, symbol in symbol_map.items():
        close = _series(frame, symbol, "Close")
        volume = _series(frame, symbol, "Volume")
        history = pd.concat([close.rename("Close"), volume.rename("Volume")], axis=1).dropna(subset=["Close"])
        if len(history) >= 210:
            histories[ticker] = history
    return histories


def _download_benchmarks(start):
    frame = yf.download(list(BENCHMARKS.values()), start=start, group_by="ticker", auto_adjust=True, threads=True, progress=False)
    return {bucket: _series(frame, symbol, "Close") for bucket, symbol in BENCHMARKS.items()}


def _bucket(mcap_cr):
    if mcap_cr >= 50000:
        return "large"
    if mcap_cr >= 15000:
        return "mid"
    return "small"


def _trend_score(ext, slope, days_above):
    c1 = pd.Series(0.0, index=ext.index)
    c1[(ext >= 0) & (ext <= 10)] = 40
    c1[(ext > 10) & (ext <= 20)] = 28
    c1[ext > 20] = 15
    c1[(ext >= -5) & (ext < 0)] = 18
    c1[(ext >= -10) & (ext < -5)] = 10
    c2 = pd.Series(0.0, index=ext.index)
    c2[slope > 1] = 30
    c2[(slope > 0.3) & (slope <= 1)] = 22
    c2[(slope >= 0) & (slope <= 0.3)] = 14
    c2[(slope >= -0.3) & (slope < 0)] = 8
    c3 = pd.Series(0.0, index=ext.index)
    c3[days_above >= 9] = 30
    c3[(days_above >= 7) & (days_above < 9)] = 22
    c3[(days_above >= 5) & (days_above < 7)] = 14
    c3[(days_above >= 3) & (days_above < 5)] = 7
    return c1 + c2 + c3


def _rsi(close):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, float("nan")))


def _st_score(row):
    score = 0
    rsi = row.rsi14
    if 50 <= rsi <= 65:
        score += 30
    elif 45 <= rsi < 50 or 65 < rsi <= 72:
        score += 22
    elif rsi > 72:
        score += 8
    elif rsi >= 40:
        score += 15
    else:
        score += 4
    if 0 <= row.p50 <= 8:
        score += 25
    elif row.p50 > 8:
        score += 18
    elif row.p50 >= -4:
        score += 12
    momentum = row.r1m + row.r1w
    score += 20 if momentum > 8 else 15 if momentum > 2 else 10 if momentum > -2 else 4 if momentum > -8 else 0
    score += 15 if row.vol_d >= 1.5 and row.r1w >= 0 else 10 if row.vol_d >= 1.2 else 5
    score += 10 if row.mover_m in ("🔥", "🚀", "📈") else 0 if row.mover_m in ("❄️", "🧊", "📉") else 5
    if rsi > 78:
        score = min(score, 55)
    return max(0, min(100, round(score)))


def _lt_score(row):
    score = round(row.trend_score / 100 * 35)
    score += 25 if row.rs6 > 15 else 20 if row.rs6 > 5 else 12 if row.rs6 > -5 else 5 if row.rs6 > -15 else 0
    momentum = row.r6m + row.r1y
    score += 20 if momentum > 40 else 15 if momentum > 10 else 10 if momentum > 0 else 4 if momentum > -20 else 0
    score += 10 if row.ath_pct > -8 else 7 if row.ath_pct > -20 else 3 if row.ath_pct > -40 else 0
    score += 10 if row.slope > 1 else 7 if row.slope > 0.3 else 4 if row.slope >= 0 else 0
    return max(0, min(100, round(score)))


def _setup(row):
    lt_strong, lt_weak = row["lt"] >= 60, row["lt"] < 45
    st_strong, st_weak = row["st"] >= 60, row["st"] < 45
    if row["lt"] >= 72 and row["st"] >= 66:
        result = "BUY"
    elif lt_strong and st_weak:
        result = "ACCUMULATE"
    elif lt_weak and st_strong:
        result = "BOUNCE"
    elif lt_weak and st_weak:
        result = "EXIT"
    else:
        result = "HOLD"
    if row.alloc == "🚨":
        if result == "BUY":
            result = "ACCUMULATE"
        elif result == "HOLD" and lt_weak:
            result = "EXIT"
    elif row.alloc in (TROPHY, GEM):
        if result == "ACCUMULATE" and st_strong:
            result = "BUY"
        elif result == "HOLD" and lt_strong:
            result = "ACCUMULATE"
    return result


def _entry_quality(row):
    rsi_score = 100 if 50 <= row.rsi14 <= 65 else 75 if 45 <= row.rsi14 <= 72 else 25
    p50_score = 100 if 0 <= row.p50 <= 8 else 60 if -4 <= row.p50 <= 15 else 20
    ext_score = 100 if 0 <= row.ext <= 20 else 70 if -5 <= row.ext <= 40 else 20
    volume_score = 100 if max(row.vol_d, row.vol_w) >= 1.2 else 50
    return (rsi_score + p50_score + ext_score + volume_score) / 4


def _point_in_time_rows(ticker, stock, history, benchmark, cutoff):
    close, volume = history.Close, history.Volume.fillna(0)
    dma50, dma200 = close.rolling(50).mean(), close.rolling(200).mean()
    ext = (close / dma200 - 1) * 100
    slope = dma200.pct_change(30) * 100
    days_above = (close > dma200).rolling(10).sum()
    r1w, r1m = close.pct_change(5) * 100, close.pct_change(20) * 100
    r6m, r1y = close.pct_change(125) * 100, close.pct_change(251) * 100
    vol_d = volume / volume.shift(1).rolling(30).mean()
    vol_w = volume.rolling(5).mean() / volume.shift(5).rolling(25).mean()
    vol_m = volume.rolling(21).mean() / volume.shift(21).rolling(126).mean()
    high52, low52 = close.rolling(252, min_periods=2).max(), close.rolling(252, min_periods=2).min()
    ath, atl = close.expanding(2).max(), close.expanding(2).min()
    bench_aligned = benchmark.reindex(close.index, method="ffill")
    bench_r6 = bench_aligned.pct_change(125) * 100
    data = pd.DataFrame({
        "close": close, "r1w": r1w, "r1m": r1m, "r6m": r6m, "r1y": r1y,
        "vol_d": vol_d, "vol_w": vol_w, "vol_m": vol_m, "ext": ext, "slope": slope,
        "days_above": days_above, "p50": (close / dma50 - 1) * 100, "rsi14": _rsi(close),
        "ath_pct": (close / ath - 1) * 100, "rs6": r6m - bench_r6,
    })
    data["trend_score"] = _trend_score(ext, slope, days_above)
    month_ends = data.groupby(data.index.to_period("M")).tail(1)
    month_ends = month_ends[month_ends.index >= pd.Timestamp(cutoff, tz=month_ends.index.tz)]
    rows = []
    for timestamp, row in month_ends.dropna().iterrows():
        location = close.index.get_loc(timestamp)
        if location + 1 >= len(close):
            continue
        levels = {
            "near_ath": close.iloc[location] >= 0.98 * ath.iloc[location],
            "near_atl": close.iloc[location] <= 1.02 * atl.iloc[location],
            "near_52wh": close.iloc[location] >= 0.98 * high52.iloc[location],
            "near_52wl": close.iloc[location] <= 1.02 * low52.iloc[location],
        }
        mover_d = classify_daily(row.vol_d, close.pct_change().iloc[location] * 100, **levels)
        mover_w = classify_weekly(row.vol_w, row.r1w, **levels)
        mover_m = classify_monthly(row.vol_m, row.r1m, **levels)
        row["mover_m"] = mover_m
        row["alloc"] = overlay_alloc(mover_d, mover_w, mover_m, row.ext, row.slope, row.days_above, row.r1m, row.trend_score)
        row["st"] = _st_score(row)
        row["lt"] = _lt_score(row)
        row["setup"] = _setup(row)
        row["entry_quality"] = _entry_quality(row)
        row["rank_score"] = 0.40 * row["lt"] + 0.25 * row["st"] + 0.20 * max(0, min(100, (row.rs6 + 20) / 60 * 100)) + 0.15 * row.entry_quality
        output = {"date": timestamp.date(), "ticker": ticker, "mcap_cr": stock.get("mcap_cr") or 0, **row.to_dict()}
        entry = close.iloc[location + 1]
        bench_location = bench_aligned.index.get_loc(timestamp)
        bench_entry = bench_aligned.iloc[bench_location + 1] if bench_location + 1 < len(bench_aligned) else float("nan")
        for label, days in HORIZONS.items():
            output[label] = (close.iloc[location + 1 + days] / entry - 1) * 100 if location + 1 + days < len(close) else float("nan")
            output[label + "_bench"] = (bench_aligned.iloc[bench_location + 1 + days] / bench_entry - 1) * 100 if bench_location + 1 + days < len(bench_aligned) else float("nan")
        rows.append(output)
    return rows


def _summarize(events):
    definitions = {
        "All eligible": pd.Series(True, index=events.index),
        "Setup BUY": events.setup.eq("BUY"),
        "Dashboard Increase": events.setup.eq("BUY") & events.alloc.isin([TROPHY, GEM]),
        "Continuation ⏫ (revised gate)": events.setup.eq("BUY") & events.mover_m.isin(["🔥", "🚀", "📈"]) & (events.slope > 0) & (events.ext >= -5) & (events.ext <= 40) & (events.r1m <= 30),
        "Continuation vol_m>=1.5 (raised)": events.setup.eq("BUY") & events.mover_m.isin(["🔥", "🚀", "📈"]) & (events.slope > 0) & (events.ext >= -5) & (events.ext <= 40) & (events.r1m <= 30) & (events.vol_m >= 1.5),
        "Continuation vol_m>=2.0 (raised)": events.setup.eq("BUY") & events.mover_m.isin(["🔥", "🚀", "📈"]) & (events.slope > 0) & (events.ext >= -5) & (events.ext <= 40) & (events.r1m <= 30) & (events.vol_m >= 2.0),
        "Reversal 🔼 (monthly accum)": events.mover_m.eq("🔼"),
        "Reversal (deep+jump: ATH<-40, 1M>15)": (events.ath_pct < -40) & (events.r1m > 15) & events.mover_m.isin(["🔥", "🚀", "📈", "🔼"]),
        "Exit ⏬ (monthly-down + falling 200DMA)": events.mover_m.isin(["🧊", "❄️", "📉"]) & (events.slope < 0) & (events.ext < 0),
        "Trim HEAVY-vol (near-high,1M<-5,volm>=1.3,6M>20)": (events.ath_pct > -10) & (events.r1m < -5) & (events.vol_m >= 1.3) & (events.r6m > 20),
        "Trim LOW-vol (near-high,1M<-5,volm<1.3,6M>20)": (events.ath_pct > -10) & (events.r1m < -5) & (events.vol_m < 1.3) & (events.r6m > 20),
        "Strict confluence": (events["lt"] >= 60) & (events.st >= 60) & (events.ext > 0) & (events.slope > 0) & (events.days_above >= 7) & (events.rs6 > 0) & (events.rsi14 <= 78) & (events.r1m <= 30) & (events.ext <= 50) & events.mover_m.isin(["🔥", "🚀", "📈"]),
    }
    confluence = definitions["Strict confluence"]
    percentile = events[confluence].groupby("date").rank_score.transform(lambda values: values.rank(pct=True))
    definitions["Top-ranked confluence"] = confluence & percentile.ge(0.8)
    results = []
    for strategy, mask in definitions.items():
        chosen = events[mask]
        for label in HORIZONS:
            valid = chosen.dropna(subset=[label, label + "_bench"]).copy()
            if valid.empty:
                continue
            valid["excess"] = valid[label] - valid[label + "_bench"]
            monthly = valid.groupby("date")[[label, label + "_bench", "excess"]].mean()
            holdout_start = monthly.index.sort_values()[len(monthly) // 2]
            holdout = monthly[monthly.index >= holdout_start]
            results.append({
                "strategy": strategy, "horizon": label, "signals": len(valid), "months": len(monthly),
                "avg_return": monthly[label].mean(), "median_return": monthly[label].median(),
                "hit_rate": (valid[label] > 0).mean() * 100, "beat_rate": (valid.excess > 0).mean() * 100,
                "avg_excess": monthly.excess.mean(), "median_excess": valid.excess.median(),
                "cohort_win_rate": (monthly.excess > 0).mean() * 100,
                "holdout_excess": holdout.excess.mean(),
            })
    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="Backtest dashboard momentum signals.")
    parser.add_argument("--years", type=int, default=3, help="Signal lookback window (default: 3 years).")
    args = parser.parse_args()
    stocks = json.loads((ROOT / "stocks.json").read_text(encoding="utf-8"))
    stocks = [
        stock for stock in stocks
        if stock.get("ticker")
        and stock["ticker"] != "CASH"
        and stock.get("holding_type", "Stocks") == "Stocks"
        and stock.get("moat_type") != "ETF"
    ]
    warm_start = date.today() - timedelta(days=args.years * 365 + 500)
    cutoff = date.today() - timedelta(days=args.years * 365)
    histories = _download_universe(stocks, warm_start)
    benchmarks = _download_benchmarks(warm_start)
    rows = []
    for index, stock in enumerate(stocks, 1):
        ticker = stock["ticker"]
        history = histories.get(ticker)
        if history is None:
            continue
        benchmark = benchmarks[_bucket(stock.get("mcap_cr") or 0)]
        if benchmark.empty:
            benchmark = benchmarks["large"]
        rows.extend(_point_in_time_rows(ticker, stock, history, benchmark, cutoff))
        if index % 50 == 0:
            print(f"Processed {index}/{len(stocks)} stocks")
    events = pd.DataFrame(rows)
    if events.empty:
        raise SystemExit("No backtest observations were produced.")
    summary = _summarize(events)
    output_dir = ROOT / "prompt_outputs"
    output_dir.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    events.to_csv(output_dir / f"momentum_backtest_events_{stamp}.csv", index=False)
    summary.to_csv(output_dir / f"momentum_backtest_summary_{stamp}.csv", index=False)
    report = [
        f"# Momentum backtest ({args.years} years)", "",
        "Monthly point-in-time signals; next-close entry; equal-weight monthly portfolios.",
        "Current dashboard universe: results have survivorship and current-size-bucket bias.", "",
        "```", summary.to_string(index=False, float_format=lambda value: f"{value:.2f}"), "```", "",
    ]
    (output_dir / f"momentum_backtest_{stamp}.md").write_text("\n".join(report), encoding="utf-8")
    print(summary.to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print(f"\nSaved outputs to {output_dir}")


if __name__ == "__main__":
    main()