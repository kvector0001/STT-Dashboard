"""
Momentum classifier — canonical, testable implementation of the Movers v5 spec.

This mirrors the tag logic that runs in two places:
  * scripts/fetch_prices.py  (Python fetcher — writes base tags into prices.json)
  * index.html computeMover() / computeAlloc() (JS — recomputes tags live on load)

Keeping the rules here as pure functions lets us unit-test the three worked
examples from the spec without spinning up yfinance or a browser.

Tag vocabulary
--------------
Level breakouts / breakdowns (any timeframe):
  🔥 FIRE    lifetime (all-time) high breakout   — near ATH + strong up
  🧊 ICE     lifetime (all-time) low breakdown   — near ATL + strong down
  🚀 ROCKET  52-week high breakout               — near 52w high + strong up
  ❄️ SNOW    52-week low breakdown               — near 52w low  + strong down
Trending (weekly & monthly only — meaningful move + volume, NOT yet at an extreme):
  📈 UP      trending up   (early re-rating / pre-breakout — highest-alpha entry)
  📉 DOWN    trending down (early de-rating)
Daily surge / suspect:
  V, P, V+P  volume / price / both surge codes (daily only)
  ⚠️ SUSPECT abnormal volume spike (>=10x avg) with |day| >= 3% — overrides V/V+P/P
Overlay allocation (post-process across all 3 timeframes):
  💎 GEM     max-conviction increase (confirmed breakout building)
  🌱 SEED    early / start building (pre-breakout trend)
  ⏳ HOUR    extended / watch
  🚨 SIREN   exit / de-rate
"""

FIRE = "\U0001f525"     # 🔥
ICE = "\U0001f9ca"      # 🧊
ROCKET = "\U0001f680"   # 🚀
SNOW = "\u2744\ufe0f"   # ❄️
UP = "\U0001f4c8"       # 📈
DOWN = "\U0001f4c9"     # 📉
SUSPECT = "\u26a0\ufe0f"  # ⚠️
GEM = "\U0001f48e"      # 💎
SEED = "\U0001f331"     # 🌱
HOUR = "\u23f3"         # ⏳
SIREN = "\U0001f6a8"    # 🚨

# Sort rank (higher = stronger bullish / more urgent). Used by the dashboard sort.
SORT_ORDER = {
    FIRE: 11, ROCKET: 10, UP: 9, ICE: 8, SNOW: 7, DOWN: 6,
    "V+P": 4, "V": 3, "P": 2, "No": 1, SUSPECT: 0,
}


def classify(rvol, ret, *, near_ath=False, near_atl=False, near_52wh=False,
             near_52wl=False, vol_t, up_t, dn_t, trend_vol=None, trend_up=None,
             surge=False, suspect=False):
    """Return the base momentum tag for one timeframe.

    rvol  : relative volume (recent avg / baseline avg) for the timeframe
    ret   : % return over the timeframe (1d / ~1w / ~1m)
    near_*: location flags (within tolerance of the given extreme)
    vol_t/up_t/dn_t : breakout volume & +/- return thresholds
    trend_vol/trend_up : trending thresholds (weekly/monthly only; None disables)
    surge/suspect      : daily-only surge codes and suspect override
    """
    if rvol is None or ret is None:
        return None
    strong_up = rvol >= vol_t and ret >= up_t
    strong_dn = rvol >= vol_t and ret <= -dn_t
    # Level breakouts/breakdowns — ATH is checked before 52-week (priority).
    if near_ath and strong_up:
        return FIRE
    if near_atl and strong_dn:
        return ICE
    if near_52wh and strong_up:
        return ROCKET
    if near_52wl and strong_dn:
        return SNOW
    # Trending (weekly/monthly): only when NOT sitting at an extreme.
    if trend_vol is not None:
        at_high = near_ath or near_52wh
        at_low = near_atl or near_52wl
        if (not at_high) and rvol >= trend_vol and ret >= trend_up:
            return UP
        if (not at_low) and rvol >= trend_vol and ret <= -trend_up:
            return DOWN
        return "No"
    # Daily suspect override — huge volume spike, overrides V/V+P/P (but not breakouts).
    if suspect and rvol >= 10 and abs(ret) >= 3:
        return SUSPECT
    if surge:
        v = rvol >= 4 and abs(ret) >= 3
        p = rvol >= 3 and abs(ret) >= 6
        if v and p:
            return "V+P"
        if v:
            return "V"
        if p:
            return "P"
    return "No"


def classify_daily(rvol, ret, **levels):
    return classify(rvol, ret, vol_t=3, up_t=3, dn_t=3, surge=True, suspect=True, **levels)


def classify_weekly(rvol, ret, **levels):
    return classify(rvol, ret, vol_t=1.5, up_t=8, dn_t=8, trend_vol=1.3, trend_up=5, **levels)


def classify_monthly(rvol, ret, **levels):
    return classify(rvol, ret, vol_t=1.3, up_t=12, dn_t=12, trend_vol=1.2, trend_up=8, **levels)


def overlay_alloc(daily, weekly, monthly):
    """Post-process across timeframes -> allocation overlay tag ('' if none)."""
    down = lambda t: t in (ICE, SNOW, DOWN)
    up = lambda t: t in (FIRE, ROCKET, UP)
    bup = lambda t: t in (FIRE, ROCKET)      # breakout up (confirmed)
    bdn = lambda t: t in (ICE, SNOW)         # breakdown
    if bdn(monthly) or (bdn(weekly) and down(monthly)):
        return SIREN
    if bup(monthly) and up(weekly):
        return GEM
    if (weekly == UP or monthly == UP) and not down(daily) and not down(weekly) and not down(monthly):
        return SEED
    if bup(monthly) and down(weekly):
        return HOUR
    return ""
