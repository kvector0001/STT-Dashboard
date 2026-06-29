"""
Derive a QUALITATIVE peer rank for EVERY holding.

Source of truth:
  - peer_comparison.json   -> q (pure qualitative quality score /10) per ticker
  - ~/Downloads/batch_*.json (quality batches) -> `sector` + `name` per ticker

Method: bucket every ticker into a peer group (by sector keywords), then rank
within the group by q (descending). Attach a `peer` object:
  peer = { group, qual_rank, of, peers:[{rank,ticker,name,q,self}] }
The peers list is a trimmed display window (rank #1 + top 3 + neighbours around
self) so the hover stays compact for large groups.

Re-run after dropping new batch_*.json files into Downloads.
"""
import json, glob, os, re

DOWNLOADS = os.path.join(os.environ["USERPROFILE"], "Downloads")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PC = os.path.join(ROOT, "peer_comparison.json")

pc = json.load(open(PC, encoding="utf-8"))

# -- 1. ticker -> sector / name from the quality batch files --
meta = {}
for path in glob.glob(os.path.join(DOWNLOADS, "batch_*.json")):
    if "peer_verdict" in os.path.basename(path):
        continue
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
        if not t:
            continue
        meta[t] = {
            "sector": (r.get("sector") or "").strip(),
            "name": (r.get("name") or t).strip(),
        }

# -- 2. peer-group buckets (priority ordered: specific first, greedy keywords last) --
BUCKETS = [
    ("ETF / Index Funds", ["etf", "index fund", "index etf", "nasdaq", "fang"]),
    ("Defence Electronics", ["defence", "defense", "radar", "microwave", "avionics", "satellite"]),
    ("Pharma / API / CDMO", ["pharma", "api", "cdmo", "biosimilar", "biopharma", "formulation", "contrast media", "drug"]),
    ("Healthcare & Hospitals", ["hospital", "oncology", "dialysis", "ivf", "renal", "trauma", "cardiac", "medi world", "care services", "healthcare", "dental", "medical", "health"]),
    ("Bearings", ["bearing"]),
    ("Abrasives & Ceramics", ["abrasive", "ceramic", "tiles"]),
    ("Compressors & Pneumatics", ["compressor", "pneumatic"]),
    ("Turbines & Heavy Engineering", ["turbine", "boiler", "heavy engineering"]),
    ("Forgings & Precision", ["forging", "precision"]),
    ("Cutting Tools", ["cutting tool", "carbide"]),
    ("Cables & Wires", ["cable"]),
    ("Electrical Equipment", ["electrical", "switchgear", "transformer", "contact"]),
    ("Shipping", ["shipping"]),
    ("Telecom & Towers", ["telecom", "tower"]),
    ("IT / Software / Tech", ["it", "information", "software", "analytics", "saas", "technology", "semiconductor", "ad tech", "travel tech", "fintech", "government tech", "maps", "embedded", "location", "e-commerce", "ai", "hpc"]),
    ("Sugar & Agri", ["sugar"]),
    ("Power & Utilities", ["power", "hydro", "lignite", "renewable", "solar", "wind", "utilit"]),
    ("EMS / Electronics", ["ems", "electronics", "networking"]),
    ("Steel Pipes & Tubes", ["pipe", "tube"]),
    ("Steel / Metals / Materials", ["steel", "graphite", "aluminium", "metal", "basic materials", "material", "wire rope", "glass", "cement"]),
    ("Mining & Minerals", ["mining", "mineral"]),
    ("Auto Components & Mobility", ["auto ancillary", "auto component", "automobile", "automotive", "auto dealership", "engine component", "engines", "piston", "ignition", "mobility", "vehicle", "tiller", "tractor", "agricultural", "energy storage"]),
    ("Real Estate", ["real estate", "realty", "housing", "infraproject"]),
    ("Hotels & Hospitality", ["hotel", "hospitality"]),
    ("Construction / Infra EPC", ["construction", "epc", "infrastructure", "building", "pre-engineered", "water", "environment", "airport"]),
    ("Chemicals & Specialty", ["chemical", "fragrance", "pigment", "refrigerant", "fluorochemical", "aroma", "lubricant"]),
    ("Consumer / Retail", ["consumer", "apparel", "retail", "fmcg", "durable", "spirit", "alcohol", "beverage", "paint", "textile", "paper"]),
    ("Business Services", ["staffing", "business services", "marketing", "advertising", "media", "education", "skills", "ooh"]),
    ("Finance", ["finance", "financial", "nbfc"]),
    ("Industrials (general)", ["industrial", "capital goods", "engineering", "equipment", "machinery", "component", "manufacturing", "automation"]),
]


def group_for(sector):
    # word-boundary match (start anchored; short keys <=3 chars fully anchored)
    # so 'api' won't match 'cAPItal' and 'ems' won't match 'systEMS'.
    s = (sector or "").lower()
    if not s:
        return None
    for label, kws in BUCKETS:
        for kw in kws:
            pat = r'(?<![a-z0-9])' + re.escape(kw)
            if len(kw) <= 3:
                pat += r'(?![a-z0-9])'
            if re.search(pat, s):
                return label
    return "Other"


# -- 3. assign group + collect members --
# wipe any prior peer assignment so dropped/singleton tickers don't keep stale ranks
for v in pc.values():
    if isinstance(v, dict) and "peer" in v:
        del v["peer"]
groups = {}
for t, m in meta.items():
    if t not in pc or not isinstance(pc[t], dict):
        continue
    q = pc[t].get("q")
    if not isinstance(q, (int, float)):
        continue
    g = group_for(m["sector"])
    if not g or g == "Other":
        continue
    name = m["name"]
    if len(name) > 26:
        name = name[:24].rstrip() + "\u2026"
    groups.setdefault(g, []).append({"ticker": t, "name": name, "q": q})

# -- 4. rank within each group + build trimmed display window --
attached = 0
for g, members in groups.items():
    members.sort(key=lambda x: (-x["q"], x["name"]))
    of = len(members)
    if of < 2:
        continue
    for i, mem in enumerate(members):
        rank = i + 1
        idxs = {0, 1, 2, i - 1, i, i + 1, of - 1}
        idxs = sorted(x for x in idxs if 0 <= x < of)
        disp = [{
            "rank": j + 1,
            "ticker": members[j]["ticker"],
            "name": members[j]["name"],
            "q": members[j]["q"],
            "self": (j == i),
        } for j in idxs]
        pc[mem["ticker"]]["peer"] = {
            "group": g,
            "qual_rank": rank,
            "of": of,
            "peers": disp,
        }
        attached += 1

json.dump(pc, open(PC, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
ng = len([g for g, m in groups.items() if len(m) >= 2])
print(f"attached qualitative peer rank to {attached} tickers across {ng} peer groups")
print("group sizes:", sorted(((len(m), g) for g, m in groups.items()), reverse=True))
