"""Action-change event log (ADD / REVERSAL / TRIM / EXIT).

Python port of the dashboard's Action rule (index.html: snST / snLT / setupOf / reversalTf / actionOf).
Keep the two in sync. Once per trading day after market close, compares each stock's Action with the
last recorded one and appends an event to action_log.json whenever it changes (e.g. EXIT -> ADD).
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

LOG_PATH = "action_log.json"
ACTION_LABEL = {"⏫": "ADD", "🔎": "REVERSAL", "✂️": "TRIM", "⏬": "EXIT", "": "—"}
IST = timezone(timedelta(hours=5, minutes=30))
CLOSE_IST = (15, 40)  # log only after the NSE close so intraday wobbles don't create events


def _n(v):
    return v if isinstance(v, (int, float)) and v == v else None


def _bench_ret6m(s, bm):
    mc = _n(s.get("mcap_cr")) or 0
    key = "nifty50" if mc >= 50000 else "midcap400" if mc >= 15000 else "smallcap250"
    r = _n((bm.get(key) or {}).get("ret_6m"))
    return r if r is not None else (_n((bm.get("smallcap250") or {}).get("ret_6m")) or 0)


def sn_st(s):
    sc = 0
    rsi, r1m, r1w, p50 = _n(s.get("rsi14")), _n(s.get("ret_1m")), _n(s.get("ret_1w")), _n(s.get("price_to_50dma_pct"))
    vol = _n(s.get("vol_today_ratio")) if _n(s.get("vol_today_ratio")) is not None else _n(s.get("vol_week_ratio"))
    mm = s.get("movers_m") or ""
    if rsi is not None:
        if 50 <= rsi <= 65: sc += 30
        elif 45 <= rsi < 50 or 65 < rsi <= 72: sc += 22
        elif rsi > 72: sc += 8
        elif rsi >= 40: sc += 15
        else: sc += 4
    else:
        sc += 12
    if p50 is not None:
        if 0 <= p50 <= 8: sc += 25
        elif p50 > 8: sc += 18
        elif p50 >= -4: sc += 12
    else:
        sc += 10
    rr = (r1m or 0) + (r1w or 0)
    if rr > 8: sc += 20
    elif rr > 2: sc += 15
    elif rr > -2: sc += 10
    elif rr > -8: sc += 4
    if vol is not None:
        if vol >= 1.5 and (r1w is None or r1w >= 0): sc += 15
        elif vol >= 1.2: sc += 10
        else: sc += 5
    else:
        sc += 6
    if mm:
        if re.search("🔥|🚀|📈", mm): sc += 10
        elif re.search("❄️|🧊|📉", mm): sc += 0
        else: sc += 5
    else:
        sc += 5
    if rsi is not None and rsi > 78:
        sc = min(sc, 55)
    return max(0, min(100, round(sc)))


def sn_lt(s, bm):
    sc = 0
    ts, r6, r1y = _n(s.get("trend_score")), _n(s.get("ret_6m")), _n(s.get("ret_1y"))
    ath, slope = _n(s.get("ath_pct")), _n(s.get("dma200_slope_30d_pct"))
    rs = (r6 - _bench_ret6m(s, bm)) if r6 is not None else None
    sc += round(ts / 100 * 35) if ts is not None else 12
    if rs is not None:
        if rs > 15: sc += 25
        elif rs > 5: sc += 20
        elif rs > -5: sc += 12
        elif rs > -15: sc += 5
    else:
        sc += 10
    rr = (r6 or 0) + (r1y or 0)
    if rr > 40: sc += 20
    elif rr > 10: sc += 15
    elif rr > 0: sc += 10
    elif rr > -20: sc += 4
    if ath is not None:
        if ath > -8: sc += 10
        elif ath > -20: sc += 7
        elif ath > -40: sc += 3
    else:
        sc += 4
    if slope is not None:
        if slope > 1: sc += 10
        elif slope > 0.3: sc += 7
        elif slope >= 0: sc += 4
    else:
        sc += 3
    return max(0, min(100, round(sc)))


def setup_of(s, bm):
    st, lt = sn_st(s), sn_lt(s, bm)
    if s.get("trend_score") is None or s.get("rsi14") is None:
        return "NA"
    lt_strong, lt_weak, st_strong, st_weak = lt >= 60, lt < 45, st >= 60, st < 45
    if lt >= 72 and st >= 66: key = "BUY"
    elif lt_strong and st_weak: key = "ACCUMULATE"
    elif lt_weak and st_strong: key = "BOUNCE"
    elif lt_weak and st_weak: key = "EXIT"
    else: key = "HOLD"
    a = s.get("movers_alloc") or ""
    if "🚨" in a:
        if key == "BUY": key = "ACCUMULATE"
        elif key == "HOLD" and lt_weak: key = "EXIT"
    elif re.search("🏆|💎", a):
        if key == "ACCUMULATE" and st_strong: key = "BUY"
        elif key == "HOLD" and lt_strong: key = "ACCUMULATE"
    return key


def reversal_tf(s):
    tf = []
    r1d, vd = _n(s.get("ret_1d")), _n(s.get("vol_today_ratio"))
    r1w, vw = _n(s.get("ret_1w")), _n(s.get("vol_week_ratio"))
    r1m = _n(s.get("ret_1m"))
    if r1d is not None and r1d >= 5 and vd is not None and vd >= 3: tf.append("D")
    if r1w is not None and r1w >= 12 and vw is not None and vw >= 3: tf.append("W")
    if r1m is not None and r1m > 15: tf.append("M")
    return tf


def action_of(s, bm):
    up = lambda m: m in ("🔥", "🚀", "📈", "💥")
    dn = lambda m: m in ("🧊", "❄️", "📉")
    ext, slope = _n(s.get("price_to_200dma_pct")), _n(s.get("dma200_slope_30d_pct"))
    r1m, r6, ath, vm = _n(s.get("ret_1m")), _n(s.get("ret_6m")), _n(s.get("ath_pct")), _n(s.get("vol_month_ratio"))
    setup = s["setup"] if isinstance(s.get("setup"), str) else setup_of(s, bm)
    if (setup == "BUY" and up(s.get("movers_m")) and slope is not None and slope > 0
            and ext is not None and -5 <= ext <= 40 and (r1m is None or r1m <= 30)):
        return "⏫"
    if dn(s.get("movers_m")) and slope is not None and slope < 0 and ext is not None and ext < 0:
        return "⏬"
    if ath is not None and ath > -10 and r1m is not None and r1m < -5 and vm is not None and vm >= 1.3 and r6 is not None and r6 > 20:
        return "✂️"
    # a reversal needs something to reverse: >=25% below ATH AND a flat/falling 200DMA (long downtrend)
    if ath is not None and ath <= -25 and slope is not None and slope <= 0.5 and reversal_tf(s):
        return "🔎"
    return ""


def update_action_log(prices, force=False):
    """Append Action-change events to action_log.json (once per trading day, after the close)."""
    now = datetime.now(IST)
    if not force and (now.weekday() >= 5 or (now.hour, now.minute) < CLOSE_IST):
        return 0
    today = now.strftime("%Y-%m-%d")
    log = {"state": {}, "last_eval": None, "events": []}
    if os.path.exists(LOG_PATH):
        try:
            log = json.load(open(LOG_PATH, encoding="utf-8"))
        except Exception as e:
            print(f"[ACTION LOG] Could not read {LOG_PATH} ({e}) — skipping to avoid overwriting it.")
            return 0
    if not force and log.get("last_eval") == today:
        return 0
    bm = prices.get("_benchmarks") or {}
    state, seeding, new_events = log.setdefault("state", {}), not log.get("state"), 0
    for sym, s in prices.items():
        if sym.startswith("_") or not isinstance(s, dict) or s.get("ltp") is None:
            continue
        if (s.get("holding_type") or "Stocks") != "Stocks":
            continue
        act = action_of(s, bm)
        prev = state.get(sym)
        if not seeding and prev is not None and prev != act:
            log["events"].append({
                "date": today, "ticker": sym, "name": s.get("name") or sym,
                "from": ACTION_LABEL.get(prev, prev), "to": ACTION_LABEL.get(act, act),
                "reversal_tf": "".join(reversal_tf(s)) if act == "🔎" else "",
                "setup": setup_of(s, bm), "alloc": s.get("movers_alloc") or "",
                "ltp": s.get("ltp"), "ret_1d": s.get("ret_1d"), "ret_1w": s.get("ret_1w"), "ret_1m": s.get("ret_1m"),
            })
            new_events += 1
        state[sym] = act
    log["last_eval"] = today
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=1, ensure_ascii=False)
    print(f"[ACTION LOG] {'Seeded baseline for ' + str(len(state)) + ' stocks' if seeding else str(new_events) + ' action change(s) logged'} ({today})")
    return new_events
