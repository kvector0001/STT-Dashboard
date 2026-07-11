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
    FIRE, ROCKET, UP, DOWN, ICE, SNOW, SUSPECT, GEM, SEED, HOUR, SIREN,
)


# --- Worked example 1: WELCORP at an all-time high -------------------------
# Weekly rvol 3.64 / +12.0% and Monthly rvol 1.57 / +15.4%, both sitting at ATH.
# Expectation: 🔥 on both weekly & monthly; overlay = 💎 (confirmed breakout building).
def test_welcorp_at_ath():
    w = classify_weekly(3.64, 12.04, near_ath=True, near_52wh=True)
    m = classify_monthly(1.57, 15.38, near_ath=True, near_52wh=True)
    d = classify_daily(1.2, 0.8)  # quiet on the day
    assert w == FIRE, w
    assert m == FIRE, m
    assert overlay_alloc(d, w, m) == GEM


# --- Worked example 2: trending-up (early re-rating, pre-breakout) ----------
# Meaningful move + volume but NOT near any extreme -> 📈, and overlay = 🌱.
def test_trending_up():
    w = classify_weekly(1.6, 9.0, near_ath=False, near_52wh=False)
    m = classify_monthly(1.4, 10.0, near_ath=False, near_52wh=False)
    d = classify_daily(1.1, 0.5)
    assert w == UP, w
    assert m == UP, m
    assert overlay_alloc(d, w, m) == SEED
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


# --- Overlay coverage: 🚨 exit, ⏳ watch -----------------------------------
def test_overlay_edges():
    assert overlay_alloc("No", "No", ICE) == SIREN        # monthly breakdown -> exit
    assert overlay_alloc("No", DOWN, SNOW) == SIREN       # weekly+monthly down -> exit
    assert overlay_alloc("No", DOWN, FIRE) == HOUR        # monthly up but weekly down -> watch
    assert overlay_alloc("No", "No", "No") == ""          # nothing notable


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
