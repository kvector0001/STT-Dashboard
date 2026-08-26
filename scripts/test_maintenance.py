"""Focused regression tests for refresh and score-worklist maintenance."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import fetch_extended_data
from portfolio_data import (apply_missing_price_fallback,
                           apply_sheet_price_fallback, extract_cash_rows)
from score_companies import is_company_holding
from yahoo_symbols import yahoo_symbol_candidates


class _FastInfo:
    last_price = 100


class _FakeTicker:
    fast_info = _FastInfo()
    info = {}

    def history(self, period):
        return pd.DataFrame()


class MaintenanceTests(unittest.TestCase):
    def test_known_symbol_overrides_are_first(self):
        self.assertEqual(yahoo_symbol_candidates("SKFINDUS")[0], "SKFINDUS.NS")
        self.assertEqual(yahoo_symbol_candidates("PARKHOSPS")[0], "PARKHOSPS.BO")
        self.assertEqual(yahoo_symbol_candidates("MAFANG-E")[0], "MAFANG.NS")

    def test_non_company_holdings_are_not_scored(self):
        self.assertFalse(is_company_holding({"ticker": "Cash"}))
        self.assertFalse(is_company_holding({"ticker": "GOLDBEES", "holding_type": "Gold"}))
        self.assertFalse(is_company_holding({"ticker": "FUND", "holding_type": "MF"}))
        self.assertTrue(is_company_holding({"ticker": "CMSINFO", "sector": "Cash Management"}))

    def test_cash_rows_are_aggregated_and_removed(self):
        frame = pd.DataFrame([
            {"symbol": "Cash", "account": "A", "holding_type": "Cash", "present_value": 1000},
            {"symbol": "Cash", "account": "A", "holding_type": " cash ", "present_value": 250},
            {"symbol": "Cash", "account": "B", "holding_type": "Cash", "present_value": 500},
            {"symbol": "CMSINFO", "account": "A", "holding_type": "Stocks", "present_value": 900},
        ])

        holdings, cash = extract_cash_rows(frame)

        self.assertEqual(cash, {"A": 1250.0, "B": 500.0})
        self.assertEqual(holdings["symbol"].tolist(), ["CMSINFO"])

    def test_wrong_yahoo_price_uses_sheet_and_blanks_returns(self):
        entry = {
            "ltp": 200, "buy_avg": 80, "quantity": 10,
            "ret_1d": 5, "ret_1m": 30, "movers": "V",
        }

        changed = apply_sheet_price_fallback(entry, 100, ("ret_1d", "ret_1m", "movers"))

        self.assertTrue(changed)
        self.assertEqual(entry["ltp"], 100)
        self.assertEqual(entry["yf_ltp"], 200)
        self.assertEqual(entry["pnl_abs"], 200)
        self.assertEqual(entry["pnl_pct"], 25)
        self.assertIsNone(entry["ret_1d"])
        self.assertIsNone(entry["ret_1m"])
        self.assertIsNone(entry["movers"])

    def test_nan_yahoo_price_is_not_treated_as_wrong_security(self):
        entry = {"ltp": float("nan"), "buy_avg": 80, "quantity": 10, "ret_1m": 5}
        changed = apply_sheet_price_fallback(entry, 100, ("ret_1m",))
        self.assertFalse(changed)
        self.assertNotIn("price_suspect", entry)
        self.assertEqual(entry["ret_1m"], 5)

    def test_missing_yahoo_price_falls_back_to_sheet_without_suspect(self):
        entry = {"ltp": float("nan"), "buy_avg": 80, "quantity": 10}
        changed = apply_missing_price_fallback(entry, 100)
        self.assertTrue(changed)
        self.assertEqual(entry["ltp"], 100)
        self.assertEqual(entry["pnl_pct"], 25)
        self.assertNotIn("price_suspect", entry)
        self.assertEqual(entry["price_source"], "sheet_no_yf")

    def test_valid_yahoo_price_is_not_overwritten_by_sheet(self):
        entry = {"ltp": 250, "buy_avg": 80, "quantity": 10}
        self.assertFalse(apply_missing_price_fallback(entry, 100))
        self.assertEqual(entry["ltp"], 250)

    def test_final_partial_batch_is_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stocks_path = os.path.join(temp_dir, "stocks.json")
            prices_path = os.path.join(temp_dir, "prices.json")
            with open(stocks_path, "w", encoding="utf-8") as f:
                json.dump([{"ticker": "SKFINDUS"}], f)

            with patch.object(fetch_extended_data, "STOCKS_PATH", stocks_path), \
                    patch.object(fetch_extended_data, "PRICES_PATH", prices_path), \
                    patch.object(fetch_extended_data.yf, "Ticker", return_value=_FakeTicker()):
                fetch_extended_data.fetch_all()

            self.assertTrue(os.path.exists(prices_path))
            with open(prices_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {})


if __name__ == "__main__":
    unittest.main()