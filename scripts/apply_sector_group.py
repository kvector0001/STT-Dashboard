"""
Assign each holding a normalized SECTOR GROUP (the ~24 buckets used across the
dashboard) and write it into stocks.json as `sector_group`, so both pages can
offer a sector dropdown. Uses the same bucket logic as build_peer_rank.py, plus
a few manual overrides where the source sector tag mislabels the company.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = os.path.join(ROOT, "stocks.json")

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

# manual fixes where the source sector tag mislabels the actual company
OVERRIDES = {
    "ENRIN": "Power & Utilities",          # Siemens Energy India (tagged Water/Environment)
    "ASALCBR": "Consumer / Retail",        # Associated Alcohols (tagged Specialty Chemicals)
    "TREL": "Real Estate",                 # Transindia Real Estate (tagged Textiles/Paper)
    "SHREEJISPG": "Shipping",              # Shreeji Shipping (tagged Steel Pipes)
    "ANURAS": "Chemicals & Specialty",     # Anupam Rasayan (tagged Pharma/API)
    "VIYASH": "Pharma / API / CDMO",       # Viyash Scientific API/CDMO (tagged Healthcare)
}


def group_for(sector):
    s = (sector or "").lower()
    if not s:
        return "Other"
    for label, kws in BUCKETS:
        for kw in kws:
            pat = r'(?<![a-z0-9])' + re.escape(kw)
            if len(kw) <= 3:
                pat += r'(?![a-z0-9])'
            if re.search(pat, s):
                return label
    return "Other"


stocks = json.load(open(ST, encoding="utf-8"))
from collections import Counter
cnt = Counter()
for s in stocks:
    t = (s.get("ticker") or "").strip()
    g = OVERRIDES.get(t) or group_for(s.get("sector", ""))
    s["sector_group"] = g
    cnt[g] += 1

json.dump(stocks, open(ST, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"assigned sector_group to {len(stocks)} stocks across {len(cnt)} groups")
for g, n in cnt.most_common():
    print(f"  {n:3d}  {g}")
