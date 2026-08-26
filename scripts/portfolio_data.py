"""Pure portfolio-data helpers used by the price refresh pipeline."""

import math

import pandas as pd


def extract_cash_rows(frame):
    """Return non-cash rows and cash totals grouped by account."""
    if "holding_type" not in frame.columns:
        return frame, {}

    cash_mask = frame["holding_type"].astype(str).str.strip().str.lower() == "cash"
    if not cash_mask.any():
        return frame, {}

    amount_column = (
        "present_value" if "present_value" in frame.columns
        else "buy_value" if "buy_value" in frame.columns
        else None
    )
    cash_by_account = {}
    for _, row in frame[cash_mask].iterrows():
        account = str(row["account"]).strip() if "account" in frame.columns else "—"
        amount = pd.to_numeric(pd.Series([row.get(amount_column)]), errors="coerce").iloc[0] if amount_column else None
        if amount is not None and not pd.isna(amount) and float(amount) != 0:
            cash_by_account[account] = round(cash_by_account.get(account, 0.0) + float(amount), 2)
    return frame[~cash_mask].copy(), cash_by_account


def apply_sheet_price_fallback(entry, sheet_ltp, blank_fields, threshold=0.25):
    """Replace a divergent Yahoo price with the sheet price and blank derived data."""
    yahoo_ltp = entry.get("ltp")
    if not sheet_ltp or not yahoo_ltp or sheet_ltp <= 0:
        return False
    yahoo_ltp = float(yahoo_ltp)
    if math.isnan(yahoo_ltp) or math.isinf(yahoo_ltp):  # missing Yahoo data is not a wrong-security signal
        return False
    if abs(yahoo_ltp - sheet_ltp) / sheet_ltp <= threshold:
        return False

    entry["price_source"] = "sheet"
    entry["price_suspect"] = True
    entry["yf_ltp"] = round(float(yahoo_ltp), 2)
    entry["ltp"] = round(float(sheet_ltp), 2)
    buy_avg = entry.get("buy_avg") or 0
    quantity = entry.get("quantity") or 0
    if buy_avg and quantity:
        entry["pnl_abs"] = round((entry["ltp"] - buy_avg) * quantity, 2)
        entry["pnl_pct"] = round((entry["ltp"] - buy_avg) / buy_avg * 100, 2)
    for field in blank_fields:
        if field in entry:
            entry[field] = None
    return True


def apply_missing_price_fallback(entry, sheet_ltp):
    """Fill LTP from the sheet when Yahoo returned no usable price.

    This is a data-availability fallback, NOT a wrong-security signal, so it does
    not set price_suspect or blank returns (which are already absent).
    """
    if not sheet_ltp or sheet_ltp <= 0:
        return False
    yahoo_ltp = entry.get("ltp")
    if yahoo_ltp is not None:
        try:
            value = float(yahoo_ltp)
            if not math.isnan(value) and not math.isinf(value) and value > 0:
                return False
        except (TypeError, ValueError):
            pass

    entry["ltp"] = round(float(sheet_ltp), 2)
    entry["price_source"] = "sheet_no_yf"
    buy_avg = entry.get("buy_avg") or 0
    quantity = entry.get("quantity") or 0
    if buy_avg and quantity:
        entry["pnl_abs"] = round((entry["ltp"] - buy_avg) * quantity, 2)
        entry["pnl_pct"] = round((entry["ltp"] - buy_avg) / buy_avg * 100, 2)
    return True