"""
Build a PURE QUALITATIVE quality score per holding from the ChatGPT batch files.
NO valuation / no P/E / no over-undervalued — those are handled live by the
peer-comparison prompt. Score = moat + management + capital allocation +
pricing power + moat durability + growth/earnings outlook.
Writes peer_comparison.json (qualitative-only schema).
"""
import json, glob, os, re

DOWNLOADS = os.path.join(os.environ["USERPROFILE"], "Downloads")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "peer_comparison.json")

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def num(v, d=0.0):
    try:
        if v is None: return d
        return float(v)
    except Exception:
        return d

# ── Load + merge all batches by ticker (prefer richer / non-pending) ──────────
records = {}
for path in sorted(glob.glob(os.path.join(DOWNLOADS, "batch_*.json"))):
    try:
        arr = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("skip", path, e); continue
    if isinstance(arr, dict):
        arr = arr.get("companies", list(arr.values()))
    for r in arr:
        if not isinstance(r, dict):
            continue
        t = (r.get("ticker") or "").strip()
        if not t: continue
        prev = records.get(t)
        if prev is None:
            records[t] = r
        else:
            # prefer the non-pending / higher conviction record
            if (prev.get("moat_class") == "pending") and (r.get("moat_class") != "pending"):
                records[t] = r
            elif num(r.get("conviction")) > num(prev.get("conviction")):
                records[t] = r

print("merged tickers:", len(records))

MOAT_BASE = {"wide": 9.0, "narrow": 6.5, "pending": 5.0}

def trend_word(s):
    s = (s or "").lower()
    if "widening" in s: return "Widening"
    if "eroding" in s: return "Eroding"
    return "Stable"

def growth_sub(r):
    rev = num(r.get("rev_cagr")); pat = num(r.get("pat_cagr"))
    if rev == 0 and pat == 0:
        return 5.0
    rev = clamp(rev, -25, 40); pat = clamp(pat, -25, 40)
    g = (rev + pat) / 2.0
    return clamp((g + 25) / 65 * 10, 0, 10)

def short(txt, n=160):
    txt = (txt or "").strip()
    txt = re.sub(r"\s+", " ", txt)
    return (txt[:n].rstrip() + "…") if len(txt) > n else txt

def tier_of(q):
    if q >= 8: return "Best-in-class"
    if q >= 7: return "High quality"
    if q >= 6: return "Above-average"
    if q >= 5: return "Average"
    return "Below-average"

entries = {}
for t, r in records.items():
    moat_class = (r.get("moat_class") or "narrow").lower()
    conv = num(r.get("conviction"))
    mgmt = clamp(num(r.get("mgmt_trust"), 6), 0, 10)
    cap = clamp(num(r.get("capital_allocation"), 5), 0, 10)
    pricing = clamp(num(r.get("pricing_power"), 5), 0, 10)
    tw = trend_word(r.get("moat_trend"))
    g = growth_sub(r)
    moat = clamp(MOAT_BASE.get(moat_class, 6.5) + (0.5 if tw == "Widening" else -0.8 if tw == "Eroding" else 0), 0, 10)

    pending = (moat_class == "pending") or conv == 0
    if pending:
        q = 0.30*mgmt + 0.25*cap + 0.20*pricing + 0.25*g
        conf = "Low"
        moat_disp = None
    else:
        conv10 = conv / 9.0 * 10.0
        q = (0.28*conv10 + 0.20*mgmt + 0.17*cap + 0.13*pricing + 0.12*moat + 0.10*g)
        conf = ("High" if (conv >= 7 and moat_class == "wide" and tw != "Eroding")
                else "Low" if conv <= 4 else "Moderate")
        moat_disp = round(moat, 1)
    q = round(clamp(q, 0, 10), 1)

    risks = r.get("risks") or []
    tails = r.get("tailwinds") or []
    entries[t] = {
        "q": q,
        "tier": tier_of(q),
        "conf": conf,
        "moat_class": moat_class,
        "comp": {
            "moat": moat_disp,
            "mgmt": round(mgmt, 1),
            "capital": round(cap, 1),
            "pricing": round(pricing, 1),
            "growth": round(g, 1),
        },
        "durability": tw,
        "moat_txt": short(r.get("moat")),
        "bull": short(r.get("bull_case"), 180),
        "bear": short(r.get("bear_case"), 140),
        "tailwind": short(tails[0] if tails else "", 120),
        "risk": short(risks[0] if risks else "", 120),
        "updated": "2026-06-25",
    }

# ── Overall quality rank (1 = best) ───────────────────────────────────────────
order = sorted(entries.keys(), key=lambda k: entries[k]["q"], reverse=True)
N = len(order)
for i, t in enumerate(order):
    entries[t]["rank"] = i + 1
    entries[t]["of"] = N

out = {
    "_meta": {
        "description": "PURE QUALITATIVE quality score per holding (0-10). Measures business quality only — moat strength & durability, management trust, capital allocation, pricing power and growth/earnings outlook. Valuation / over-under-valued is intentionally EXCLUDED (it changes daily and is fetched live via the peer-comparison prompt on click). Derived from ChatGPT public-source batch analysis. NOT investment advice.",
        "score_meaning": "q = quality /10. Weights: conviction/moat 28%, management 20%, capital allocation 17%, pricing power 13%, moat 12%, growth outlook 10%. tier: >=8 Best-in-class, >=7 High quality, >=6 Above-average, >=5 Average, else Below-average.",
        "fields": "q, tier, conf, moat_class, comp{moat,mgmt,capital,pricing,growth}, durability, moat_txt, bull, bear, tailwind, risk, rank(overall), of, updated",
        "updated": "2026-06-25",
    }
}
for t in order:
    out[t] = entries[t]

json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("wrote", OUT, "with", N, "companies")
print("\nTOP 15 by quality:")
for t in order[:15]:
    e = entries[t]; print(f"  {e['q']:>4} {e['tier']:<14} {t}")
print("\nBOTTOM 10 by quality:")
for t in order[-10:]:
    e = entries[t]; print(f"  {e['q']:>4} {e['tier']:<14} {t}  ({e['conf']})")
