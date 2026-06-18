#!/usr/bin/env python3
"""
score_companies.py — maintain Management Trust + Red Flags scores (NO API key needed).

Single source of truth:
  - management_trust.json   (keyed by ticker; 5-pillar weighted score)
  - red_flags.json          (keyed by ticker; 4-category weighted score)

Modes
-----
  python scripts/score_companies.py pending
      Find holdings in stocks.json that are missing a Management Trust and/or
      Red Flags score and write a ready-to-fill worklist + a merge template:
        prompt_outputs/_pending_scores_worklist.md   (snapshot + both prompts)
        prompt_outputs/_scores_to_merge.template.json (exact JSON shape to fill)

  python scripts/score_companies.py merge <reply.json>
      Merge a filled JSON (keyed by ticker, with mgmt_trust / red_flags blocks)
      into the two JSON files. The OVERALL score + verdict are recomputed here
      from the pillar/category sub-scores so everything stays consistent. Then
      both downloadable *_findings.md reports are regenerated.

  python scripts/score_companies.py report
      Regenerate both prompt_outputs/*_findings.md reports from the JSON files.

The merge input shape (see the generated *.template.json):
  {
    "TICKER": {
      "mgmt_trust": {
        "confidence": "Moderate", "summary": "...", "sources": "...",
        "etf": false,
        "pillars": {
          "promoter_profile":   {"score": 7, "reason": "..."},
          "ownership_behaviour":{"score": 7, "reason": "..."},
          "capital_allocation": {"score": 7, "reason": "..."},
          "governance":         {"score": 7, "reason": "..."},
          "execution":          {"score": 7, "reason": "..."}
        }
      },
      "red_flags": {
        "confidence": "Moderate", "summary": "...", "sources": "...",
        "etf": false, "critical_flags": [], "amber_flags": [],
        "categories": {
          "accounting": {"score": 7, "reason": "..."},
          "governance": {"score": 7, "reason": "..."},
          "financial":  {"score": 7, "reason": "..."},
          "business":   {"score": 7, "reason": "..."}
        }
      }
    }
  }
Either block may be omitted if that score already exists / is not needed.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS = os.path.join(ROOT, "stocks.json")
MT = os.path.join(ROOT, "management_trust.json")
RF = os.path.join(ROOT, "red_flags.json")
OUT = os.path.join(ROOT, "prompt_outputs")
PROMPTS = os.path.join(ROOT, "prompts")
TODAY = date.today().isoformat()

MT_WEIGHTS = {"promoter_profile": 0.20, "ownership_behaviour": 0.25,
              "capital_allocation": 0.20, "governance": 0.20, "execution": 0.15}
RF_WEIGHTS = {"accounting": 0.30, "governance": 0.30, "financial": 0.20, "business": 0.20}
DEF_SOURCES = ("Dashboard financials + curated governance/risk flags + public "
               "filings (BSE/NSE/screener.in), analyst knowledge")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def stock_rows():
    s = load(STOCKS, [])
    return s if isinstance(s, list) else s.get("stocks", s.get("data", []))


def keyset(d):
    return {k for k in d if not k.startswith("_")}


# ──────────────────────────────────────────────────────────────────────────
# verdict helpers (single source of truth for the scales)
# ──────────────────────────────────────────────────────────────────────────
def mt_verdict(sc, etf=False):
    if etf:
        return "N/A (ETF)"
    return "HIGH" if sc >= 8 else "MODERATE" if sc >= 6 else "LOW"


def rf_verdict(sc, etf=False):
    if etf:
        return "N/A (ETF)"
    return ("CLEAN" if sc >= 8 else "MINOR" if sc >= 6.5
            else "MODERATE" if sc >= 5 else "SERIOUS")


def build_mt_entry(block):
    p = block["pillars"]
    sc = round(sum(MT_WEIGHTS[k] * p[k]["score"] for k in MT_WEIGHTS), 2)
    etf = bool(block.get("etf"))
    return {
        "score": sc,
        "verdict": mt_verdict(sc, etf),
        "confidence": block.get("confidence", "Moderate"),
        "updated": block.get("updated", TODAY),
        "pillars": {k: {"score": p[k]["score"], "reason": p[k].get("reason", "")}
                    for k in MT_WEIGHTS},
        "summary": block.get("summary", ""),
        "sources": block.get("sources", DEF_SOURCES),
    }


def build_rf_entry(block):
    c = block["categories"]
    sc = round(sum(RF_WEIGHTS[k] * c[k]["score"] for k in RF_WEIGHTS), 2)
    etf = bool(block.get("etf"))
    return {
        "score": sc,
        "verdict": rf_verdict(sc, etf),
        "confidence": block.get("confidence", "Moderate"),
        "updated": block.get("updated", TODAY),
        "categories": {k: {"score": c[k]["score"], "reason": c[k].get("reason", "")}
                       for k in RF_WEIGHTS},
        "critical_flags": block.get("critical_flags", []),
        "amber_flags": block.get("amber_flags", []),
        "summary": block.get("summary", ""),
        "sources": block.get("sources", DEF_SOURCES),
    }


# ──────────────────────────────────────────────────────────────────────────
# PENDING
# ──────────────────────────────────────────────────────────────────────────
def snapshot(r):
    risks = r.get("risks") or []
    if isinstance(risks, list):
        risks = " | ".join(str(x) for x in risks)
    return (
        f"- Company: {r.get('name', r['ticker'])} ({r['ticker']})\n"
        f"- Sector: {r.get('sector', 'n/a')}\n"
        f"- Market cap: Rs {r.get('mcap_cr', 'n/a')} Cr\n"
        f"- Financials: ROE={r.get('roe')} | D/E={r.get('debt_to_equity')} | "
        f"DivYield={r.get('div_yield')} | PAT_CAGR={r.get('pat_cagr')} | "
        f"Rev_CAGR={r.get('rev_cagr')} | OCF(Cr)={r.get('ocf_cr')}\n"
        f"- Leadership: {r.get('leadership', 'n/a')}\n"
        f"- Risks: {risks or 'n/a'}"
    )


def read_prompt(name):
    try:
        with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"(prompt file prompts/{name} not found)"


def fill_prompt(tmpl, r):
    return (tmpl.replace("{{COMPANY_NAME}}", str(r.get("name", r["ticker"])))
                .replace("{{TICKER}}", str(r["ticker"]))
                .replace("{{SNAPSHOT}}", snapshot(r)))


def cmd_pending():
    rows = stock_rows()
    mt = load(MT, {})
    rf = load(RF, {})
    mt_keys, rf_keys = keyset(mt), keyset(rf)

    missing = []
    for r in rows:
        t = r.get("ticker")
        if not t:
            continue
        need_mt = t not in mt_keys
        need_rf = t not in rf_keys
        if need_mt or need_rf:
            missing.append((r, need_mt, need_rf))

    os.makedirs(OUT, exist_ok=True)
    if not missing:
        print("All holdings already have Management Trust and Red Flags scores. Nothing pending.")
        # still clear stale worklist
        for f in ("_pending_scores_worklist.md", "_scores_to_merge.template.json"):
            p = os.path.join(OUT, f)
            if os.path.exists(p):
                os.remove(p)
        return

    mt_tmpl = read_prompt("management_trust.md")
    rf_tmpl = read_prompt("red_flags.md")

    L = [f"# Pending Score Worklist ({len(missing)} holding(s) missing a score)\n",
         f"_Generated {TODAY}. Fill these in, then merge._\n",
         "## How to fill\n",
         "**Path A — VS Code agent mode (no API):** run `/score-pending` in chat; the agent scores all of these and merges.\n",
         "**Path B — Claude web:** paste each block below into Claude, collect the answers into "
         "`prompt_outputs/_scores_to_merge.json` using the shape in "
         "`_scores_to_merge.template.json`, then run `merge_scores.bat prompt_outputs\\_scores_to_merge.json`.\n",
         "> Scoring stays evidence-based — no fabrication. Use **Low** confidence for thin-data / new IPOs. "
         "You only provide the pillar/category sub-scores + reasons + summary; the overall score and verdict "
         "are computed automatically on merge.\n",
         "\n---\n"]

    for r, need_mt, need_rf in missing:
        t = r["ticker"]
        tags = []
        if need_mt:
            tags.append("Management Trust")
        if need_rf:
            tags.append("Red Flags")
        L.append(f"\n## {r.get('name', t)} ({t}) — needs: {', '.join(tags)}\n")
        L.append("```\n" + snapshot(r) + "\n```\n")
        if need_mt:
            L.append("<details><summary>👔 Management Trust prompt</summary>\n")
            L.append("\n```\n" + fill_prompt(mt_tmpl, r) + "\n```\n</details>\n")
        if need_rf:
            L.append("<details><summary>🚩 Red Flags prompt</summary>\n")
            L.append("\n```\n" + fill_prompt(rf_tmpl, r) + "\n```\n</details>\n")
        L.append("\n---\n")

    with open(os.path.join(OUT, "_pending_scores_worklist.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # merge template (one example entry per missing ticker, blocks only where needed)
    tmpl = {}
    for r, need_mt, need_rf in missing:
        entry = {}
        if need_mt:
            entry["mgmt_trust"] = {
                "confidence": "Moderate", "summary": "", "sources": DEF_SOURCES, "etf": False,
                "pillars": {k: {"score": 0, "reason": ""} for k in MT_WEIGHTS},
            }
        if need_rf:
            entry["red_flags"] = {
                "confidence": "Moderate", "summary": "", "sources": DEF_SOURCES, "etf": False,
                "critical_flags": [], "amber_flags": [],
                "categories": {k: {"score": 0, "reason": ""} for k in RF_WEIGHTS},
            }
        tmpl[r["ticker"]] = entry
    save(os.path.join(OUT, "_scores_to_merge.template.json"), tmpl)

    print(f"{len(missing)} holding(s) pending:")
    for r, need_mt, need_rf in missing:
        miss = "+".join([x for x, b in (("MT", need_mt), ("RF", need_rf)) if b])
        print(f"  - {r['ticker']:<12} ({miss})  {r.get('name', '')}")
    print("\nWrote:")
    print("  prompt_outputs/_pending_scores_worklist.md")
    print("  prompt_outputs/_scores_to_merge.template.json")


# ──────────────────────────────────────────────────────────────────────────
# MERGE
# ──────────────────────────────────────────────────────────────────────────
def cmd_merge(path):
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}")
        sys.exit(1)
    data = load(path, None)
    if not isinstance(data, dict):
        print("ERROR: merge file must be a JSON object keyed by ticker.")
        sys.exit(1)

    mt = load(MT, {})
    rf = load(RF, {})
    n_mt = n_rf = 0
    for ticker, blocks in data.items():
        if ticker.startswith("_") or not isinstance(blocks, dict):
            continue
        if "mgmt_trust" in blocks and blocks["mgmt_trust"].get("pillars"):
            try:
                mt[ticker] = build_mt_entry(blocks["mgmt_trust"])
                n_mt += 1
            except (KeyError, TypeError) as e:
                print(f"  ! skipped mgmt_trust for {ticker}: {e}")
        if "red_flags" in blocks and blocks["red_flags"].get("categories"):
            try:
                rf[ticker] = build_rf_entry(blocks["red_flags"])
                n_rf += 1
            except (KeyError, TypeError) as e:
                print(f"  ! skipped red_flags for {ticker}: {e}")

    save(MT, mt)
    save(RF, rf)
    print(f"Merged {n_mt} Management Trust and {n_rf} Red Flags entries.")
    cmd_report()


# ──────────────────────────────────────────────────────────────────────────
# REPORT (regenerate downloadable findings markdowns)
# ──────────────────────────────────────────────────────────────────────────
def _names_sectors():
    rows = stock_rows()
    name = {r["ticker"]: (r.get("name") or r["ticker"]) for r in rows if r.get("ticker")}
    sect = {r["ticker"]: (r.get("sector") or "") for r in rows if r.get("ticker")}
    return name, sect


def report_mt():
    mt = load(MT, {})
    name, sect = _names_sectors()
    items = [(k, v) for k, v in mt.items() if not k.startswith("_") and isinstance(v, dict)]
    order = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "N/A (ETF)": 3}
    items.sort(key=lambda kv: (order.get(kv[1].get("verdict"), 9), -float(kv[1].get("score") or 0)))
    L = ["# Management Trust Score - Full Findings (All Holdings)\n",
         "> 5-pillar weighted score - **Promoter Profile (20%)**, **Ownership Behaviour (25%)**, "
         "**Capital Allocation (20%)**, **Governance (20%)**, **Execution (15%)**. Grounded in reported "
         "financials, curated governance/risk flags and public filings. **Not investment advice.**\n",
         f"_Generated {TODAY} for {len(items)} holdings. Verdict: **HIGH** >= 8.0 | **MODERATE** 6.0-7.9 | "
         "**LOW** < 6.0 | **N/A** for ETFs._\n",
         "\n## Summary Table\n",
         "| # | Company | Ticker | Sector | Score | Verdict | Confidence |",
         "|---|---------|--------|--------|------:|---------|-----------|"]
    for i, (k, v) in enumerate(items, 1):
        L.append(f"| {i} | {name.get(k, k)} | {k} | {sect.get(k, '')} | {v.get('score')} | "
                 f"{v.get('verdict')} | {v.get('confidence')} |")
    L.append("\n---\n\n## Detailed Assessments\n")
    labels = [("promoter_profile", "Promoter Profile", "20%"),
              ("ownership_behaviour", "Ownership Behaviour", "25%"),
              ("capital_allocation", "Capital Allocation", "20%"),
              ("governance", "Governance", "20%"), ("execution", "Execution", "15%")]
    for k, v in items:
        L.append(f"### {name.get(k, k)} ({k}) - {v.get('score')} / 10 - {v.get('verdict')}")
        L.append(f"*Sector: {sect.get(k, 'n/a')} - Confidence: {v.get('confidence')} - Updated: {v.get('updated')}*\n")
        L.append(f"**Summary:** {v.get('summary', '')}\n")
        pil = v.get("pillars", {})
        L.append("| Pillar (weight) | Score | Rationale |")
        L.append("|---|:---:|---|")
        for key, lab, w in labels:
            p = pil.get(key, {})
            L.append(f"| {lab} ({w}) | {p.get('score', '-')} | {p.get('reason', '')} |")
        L.append(f"\n*Sources: {v.get('sources', '')}*\n\n---\n")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "management_trust_findings.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return len(items)


def report_rf():
    rf = load(RF, {})
    name, sect = _names_sectors()
    items = [(k, v) for k, v in rf.items() if not k.startswith("_") and isinstance(v, dict)]
    order = {"SERIOUS": 0, "MODERATE": 1, "MINOR": 2, "CLEAN": 3, "N/A (ETF)": 4}
    items.sort(key=lambda kv: (order.get(kv[1].get("verdict"), 9), float(kv[1].get("score") or 0)))
    L = ["# Red-Flag Forensic Scan - Full Findings (All Holdings)\n",
         "> 4-category weighted score - **Accounting (30%)**, **Governance (30%)**, **Financial (20%)**, "
         "**Business (20%)** - where **10 = clean** and **0-3 = serious red flags**. Higher = cleaner. "
         "**Not investment advice.**\n",
         f"_Generated {TODAY} for {len(items)} holdings. Verdict: **CLEAN** >= 8.0 | **MINOR** 6.5-7.9 | "
         "**MODERATE** 5.0-6.4 | **SERIOUS** < 5.0 | **N/A** for ETFs. Sorted worst-first._\n",
         "\n## Summary Table\n",
         "| # | Company | Ticker | Sector | Score | Verdict | Confidence |",
         "|---|---------|--------|--------|------:|---------|-----------|"]
    for i, (k, v) in enumerate(items, 1):
        L.append(f"| {i} | {name.get(k, k)} | {k} | {sect.get(k, '')} | {v.get('score')} | "
                 f"{v.get('verdict')} | {v.get('confidence')} |")
    L.append("\n---\n\n## Detailed Assessments\n")
    labels = [("accounting", "Accounting", "30%"), ("governance", "Governance", "30%"),
              ("financial", "Financial", "20%"), ("business", "Business", "20%")]
    for k, v in items:
        L.append(f"### {name.get(k, k)} ({k}) - {v.get('score')} / 10 - {v.get('verdict')}")
        L.append(f"*Sector: {sect.get(k, 'n/a')} - Confidence: {v.get('confidence')} - Updated: {v.get('updated')}*\n")
        L.append(f"**Summary:** {v.get('summary', '')}\n")
        cat = v.get("categories", {})
        L.append("| Category (weight) | Score | Key reason |")
        L.append("|---|:---:|---|")
        for key, lab, w in labels:
            c = cat.get(key, {})
            L.append(f"| {lab} ({w}) | {c.get('score', '-')} | {c.get('reason', '')} |")
        if v.get("critical_flags"):
            L.append("\n**Critical flags:**")
            for fl in v["critical_flags"]:
                L.append(f"- {fl}")
        if v.get("amber_flags"):
            L.append("\n**Amber flags:**")
            for fl in v["amber_flags"]:
                L.append(f"- {fl}")
        L.append(f"\n*Sources: {v.get('sources', '')}*\n\n---\n")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "red_flags_findings.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return len(items)


def cmd_report():
    n1 = report_mt()
    n2 = report_rf()
    print(f"Reports rebuilt: management_trust_findings.md ({n1}), red_flags_findings.md ({n2}).")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pending"
    if mode == "pending":
        cmd_pending()
    elif mode == "merge":
        if len(sys.argv) < 3:
            print("Usage: python scripts/score_companies.py merge <reply.json>")
            sys.exit(1)
        cmd_merge(sys.argv[2])
    elif mode == "report":
        cmd_report()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
