"""Shared Yahoo Finance symbol resolution for portfolio refresh scripts."""

import re


YFINANCE_SYMBOL_OVERRIDES = {
    "PARKHOSPS": "PARKHOSPS.BO",
    "INCAP": "INCAP.BO",
    "MAFANG": "MAFANG.NS",
    "SKFINDUS": "SKFINDUS.NS",
}


def yahoo_symbol_candidates(raw_symbol, mapped_symbol=None):
    """Return deduplicated Yahoo candidates with known-good overrides first."""
    raw_symbol = str(raw_symbol).strip()
    clean_symbol = re.sub(r"-[A-Z]$", "", raw_symbol)
    mapped_symbol = str(mapped_symbol or clean_symbol).strip()
    clean_mapped = re.sub(r"-[A-Z]$", "", mapped_symbol)

    candidates = [
        mapped_symbol + ".NS",
        clean_symbol + ".NS",
        clean_mapped + ".NS",
        mapped_symbol + ".BO",
        clean_symbol + ".BO",
        clean_mapped + ".BO",
    ]
    override_key = raw_symbol if raw_symbol in YFINANCE_SYMBOL_OVERRIDES else clean_symbol
    preferred = YFINANCE_SYMBOL_OVERRIDES.get(override_key)
    if preferred:
        candidates.insert(0, preferred)
    return list(dict.fromkeys(candidates))