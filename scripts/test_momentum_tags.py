"""
Unit tests for the Movers v5 momentum classifier (spec section 7 worked examples).

Run:  python scripts/test_momentum_tags.py      (no pytest needed)
  or: pytest scripts/test_momentum_tags.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from momentum_classifier import (  # noqa: E402
    classify_daily, classify_weekly, classify_monthly, overlay_alloc,
    FIRE, ROCKET, UP, DOWN, ICE, SNOW, SUSPECT, GEM, TROPHY, SEED, HOUR, SIREN,
)


# --- Worked example 1: WELCORP at an all-time high -------------------------
# Weekly rvol 3.64 / +12.0% and Monthly rvol 1.57 / +15.4%, both sitting at ATH.
# Expectation: 🔥 on both weekly & monthly; but it is +63% above a rising 200DMA
# (very extended) -> allocation overlay = ⏳ HOLD/TRIM (don't chase).
def test_welcorp_at_ath():
    w = classify_weekly(3.64, 12.04, near_ath=True, near_52wh=True)
    m = classify_monthly(1.57, 15.38, near_ath=True, near_52wh=True)
    d = classify_daily(1.2, 0.8)  # quiet on the day
    assert w == FIRE, w
    assert m == FIRE, m
    # ext=63% (>50) -> extended -> TRIM regardless of the modest 1M move
    assert overlay_alloc(d, w, m, ext=63, slope=9.4, da=10, r1m=15) == HOUR


# --- Worked example 2: trending-up (early re-rating, pre-breakout) ----------
# Meaningful move + volume but NOT near any extreme -> 📈. Allocation depends on
# the 200DMA context: early + rising trend + not extended -> 💎 ADD.
def test_trending_up():
    w = classify_weekly(1.6, 9.0, near_ath=False, near_52wh=False)
    m = classify_monthly(1.4, 10.0, near_ath=False, near_52wh=False)
    d = classify_daily(1.1, 0.5)
    assert w == UP, w
    assert m == UP, m
    # HAPPYFORGE-like: +32% above a rising 200DMA (past the sweet spot) but early -> ADD
    assert overlay_alloc(d, w, m, ext=32, slope=7.0, da=10, r1m=17) == GEM
    # TVSELECT/RATNAVEER-like sweet spot: ext<=20 AND da>=9 -> STRONG ADD
    assert overlay_alloc(d, w, m, ext=8, slope=2.2, da=10, r1m=13) == TROPHY
    # ext just over the sweet-spot cap (20) stays a regular ADD, not STRONG
    assert overlay_alloc(d, w, m, ext=25, slope=2.2, da=10, r1m=13) == GEM
    # Same tags but 200DMA still flat/turning (slope 0.4) -> not yet confirmed -> START-SMALL
    assert overlay_alloc(d, w, m, ext=14, slope=0.4, da=10, r1m=10) == SEED
    # A strong-up weekly that IS near the 52w high must NOT be 📈 (it's a 🚀 breakout).
    assert classify_weekly(1.6, 9.0, near_52wh=True) == ROCKET


# --- Worked example 3: suspect pump (daily) --------------------------------
# rvol 12x and +4% but no clean breakout -> ⚠️ (overrides V/V+P/P).
def test_suspect_pump():
    assert classify_daily(12.0, 4.0) == SUSPECT
    assert classify_daily(12.0, -4.0) == SUSPECT
    # A genuine breakout still wins over suspect: 12x + 4% AT the ATH is 🔥, not ⚠️.
    assert classify_daily(12.0, 4.0, near_ath=True) == FIRE
    # Just below the suspect bar -> falls back to a normal surge code, not ⚠️.
    assert classify_daily(9.0, 4.0) == "V"


# --- Boundary: monthly breakout threshold is +/-12% (was +/-15%) -----------
def test_monthly_threshold_12pct():
    # +13% at ATH clears the 12% bar -> 🔥.
    assert classify_monthly(1.4, 13.0, near_ath=True, near_52wh=True) == FIRE
    # +11% at ATH is below 12% -> not a breakout, and at an extreme so not trending.
    assert classify_monthly(1.4, 11.0, near_ath=True, near_52wh=True) == "No"


# --- Overlay coverage: pullback-vs-reduce (TS-aware) + trim + guards ---------
def test_overlay_edges():
    assert overlay_alloc("No", "No", ICE) == SIREN                       # new lifetime low -> reduce
    assert overlay_alloc("No", UP, UP, ext=-16, slope=-8.7, da=0, r1m=29) == SIREN  # below a falling 200DMA -> reduce
    assert overlay_alloc("No", UP, ROCKET, ext=45, slope=-0.8, da=10, r1m=42) == HOUR  # GREAVESCOT: already ran 42% -> hold/trim
    # SOUTHWEST case: monthly dip but 200DMA rising hard + TS high -> PULLBACK -> HOLD, not reduce
    assert overlay_alloc("No", "No", DOWN, ext=11, slope=8.0, da=10, r1m=-11, ts=88) == HOUR
    # Same monthly dip but the 200DMA is flat and TS weak -> genuine de-rating -> REDUCE
    assert overlay_alloc("No", "No", DOWN, ext=11, slope=0.4, da=10, r1m=-11, ts=50) == SIREN
    # EIMCO case: weekly dip, monthly up, price above a (mildly falling) 200DMA -> HOLD, not reduce
    assert overlay_alloc("No", DOWN, UP, ext=8, slope=-4.5, da=10, r1m=12) == HOUR
    assert overlay_alloc("No", "No", "No") == ""                          # nothing notable


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
