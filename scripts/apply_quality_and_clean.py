"""
(1) Persist the qualitative quality score into the stocks.json master file
    (quality_score + quality_rank within the portfolio).
(2) Strip the OLD sector-group `peer` objects out of peer_comparison.json — peer
    rank now comes from peer_rank.json (6 real-market competitors), not portfolio
    sector grouping.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PC = os.path.join(ROOT, "peer_comparison.json")
ST = os.path.join(ROOT, "stocks.json")

pc = json.load(open(PC, encoding="utf-8"))

# rank tickers by quality score (desc) for a portfolio-wide quality_rank
scored = [(t, v["q"]) for t, v in pc.items()
          if isinstance(v, dict) and isinstance(v.get("q"), (int, float))]
scored.sort(key=lambda x: -x[1])
rank_of = {t: i + 1 for i, (t, _) in enumerate(scored)}
total = len(scored)

# (1) write into stocks.json
stocks = json.load(open(ST, encoding="utf-8"))
upd = 0
for s in stocks:
    t = (s.get("ticker") or "").strip()
    e = pc.get(t)
    if isinstance(e, dict) and isinstance(e.get("q"), (int, float)):
        s["quality_score"] = e["q"]
        s["quality_tier"] = e.get("tier")
        s["quality_rank"] = rank_of.get(t)
        s["quality_of"] = total
        upd += 1
json.dump(stocks, open(ST, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# (2) strip stale sector peer objects
removed = 0
for v in pc.values():
    if isinstance(v, dict) and "peer" in v:
        del v["peer"]; removed += 1
json.dump(pc, open(PC, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

print(f"stocks.json: wrote quality_score to {upd} companies (of {len(stocks)})")
print(f"peer_comparison.json: removed {removed} stale sector peer objects")
