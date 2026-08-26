#!/usr/bin/env python3
"""Merge quality (peer_comparison.json) and peer-rank (peer_rank.json) entries.

Usage: python scripts/merge_peers.py <peers.json>

<peers.json> has two keys: "quality" (dict keyed by ticker) and "peer_rank"
(dict keyed by ticker). Quality entries are added/updated and the overall
quality rank/of is recomputed by q across all non-meta entries.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PC = os.path.join(ROOT, "peer_comparison.json")
PR = os.path.join(ROOT, "peer_rank.json")
TODAY = date.today().isoformat()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main(path):
    data = load(path)
    quality = data.get("quality", {})
    peer_rank = data.get("peer_rank", {})

    pc = load(PC)
    for ticker, entry in quality.items():
        entry.setdefault("updated", TODAY)
        pc[ticker] = {**pc.get(ticker, {}), **entry}

    ranked = sorted(
        ((k, v) for k, v in pc.items() if not k.startswith("_") and isinstance(v, dict) and v.get("q") is not None),
        key=lambda kv: -float(kv[1]["q"]),
    )
    total = len(ranked)
    for i, (k, v) in enumerate(ranked, 1):
        v["rank"] = i
        v["of"] = total
    save(PC, pc)

    pr = load(PR)
    for ticker, entry in peer_rank.items():
        pr[ticker] = entry
    save(PR, pr)

    print(f"Quality: added/updated {len(quality)}; ranked {total} total.")
    print(f"Peer rank: added/updated {len(peer_rank)}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/merge_peers.py <peers.json>")
        sys.exit(1)
    main(sys.argv[1])
