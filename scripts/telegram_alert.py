#!/usr/bin/env python3
"""Send the current DAILY movers (Mov(D) column) to a Telegram chat.

Simple trigger: every held stock that has any daily mover tag in prices.json is
included. Meant to run right after fetch_prices.py (the morning refresh), so the
tags are freshly computed.

Config (never committed): a `telegram_config.json` in the Dashboard root, or the
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables.
    { "bot_token": "123456:ABC-DEF...", "chat_id": "123456789" }
"""
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from momentum_classifier import classify_daily  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "prices.json"
CONFIG = ROOT / "telegram_config.json"

# Daily mover tags, ordered strongest-signal first, with a plain-language meaning.
TAG_MEANING = {
    "\U0001f4a5": "Explosive breakout (huge volume at a fresh high)",
    "\U0001f525": "Lifetime-high breakout",
    "\U0001f680": "52-week-high breakout",
    "\U0001f9ca": "Lifetime-low breakdown",
    "\u2744\ufe0f": "52-week-low breakdown",
    "\U0001f53b": "Distribution (heavy selling at the highs)",
    "\U0001f53c": "Accumulation (heavy buying at the lows)",
    "V+P": "Volume + price surge",
    "V": "Heavy volume",
    "P": "Price surge",
}
TAG_ORDER = list(TAG_MEANING.keys())
BLANK = {None, "", "No", "\u2014"}


def load_config():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return token, str(chat_id)
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if token and chat_id and not str(token).startswith("PASTE_"):
            return str(token), str(chat_id)
    return None, None


def _yesterday_tag(y):
    # Same inputs the dashboard feeds computeMover for the D-1 tag under Mov(D).
    if not isinstance(y, dict) or y.get("v") is None or y.get("r") is None:
        return None
    near = lambda v, test: v is not None and test(v)
    return classify_daily(
        y["v"], y["r"],
        near_ath=near(y.get("ath"), lambda v: v >= -2),
        near_atl=near(y.get("atl"), lambda v: v <= 2),
        near_52wh=near(y.get("h"), lambda v: v >= -2),
        near_52wl=near(y.get("l"), lambda v: v <= 2),
    )


def _sort(rows):
    rows.sort(key=lambda r: (TAG_ORDER.index(r["tag"]) if r["tag"] in TAG_ORDER else 99, r["ticker"]))
    return rows


def daily_movers():
    """Return (today_rows, yesterday_rows, yesterday_date) for held stocks."""
    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    today, yest, ydate = [], [], None
    for tk, s in prices.items():
        if tk.startswith("_") or not isinstance(s, dict):
            continue
        if (s.get("quantity") or 0) <= 0:
            continue
        tag = s.get("movers")
        if tag not in BLANK:
            today.append({"ticker": tk, "tag": tag,
                          "ret": s.get("ret_1d"), "vol": s.get("vol_today_ratio")})
        y = s.get("mv_yest")
        ytag = _yesterday_tag(y)
        if ytag not in BLANK:
            yest.append({"ticker": tk, "tag": ytag, "ret": y.get("r"), "vol": y.get("v")})
            ydate = ydate or y.get("d")
    return _sort(today), _sort(yest), ydate


def _section(title, rows, empty):
    lines = [title]
    if not rows:
        lines.append(f"  {empty}")
        return lines
    for r in rows:
        ret = f"{r['ret']:+.1f}%" if isinstance(r["ret"], (int, float)) else "\u2014"
        vol = f"{r['vol']:.0f}\u00d7" if isinstance(r["vol"], (int, float)) else "\u2014"
        lines.append(f"{r['tag']}  {r['ticker']}   {ret} \u00b7 {vol} vol")
    return lines


def format_message(today, yest, ydate=None):
    from datetime import datetime
    now = datetime.now()
    lines = [f"\U0001f4c8 Daily Movers \u2014 {now:%a %d %b %Y}", ""]
    lines += _section(f"TODAY (as of {now:%H:%M}) \u2014 {len(today)}", today, "No movers yet today.")
    lines.append("")
    ylabel = datetime.strptime(ydate, "%Y-%m-%d").strftime("%a %d %b") if ydate else "previous session"
    lines += _section(f"YESTERDAY ({ylabel}, full day) \u2014 {len(yest)}", yest, "No movers yesterday.")
    # Legend for the tags that actually appear
    rows = today + yest
    seen = [t for t in TAG_ORDER if any(r["tag"] == t for r in rows)]
    if seen:
        lines.append("")
        lines.append("\u2014")
        for t in seen:
            lines.append(f"{t} = {TAG_MEANING[t]}")
    return "\n".join(lines)


def send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram caps a single message at 4096 chars; chunk on line boundaries.
    chunks, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > 3800:
            chunks.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        chunks.append(buf)
    for chunk in chunks:
        resp = requests.post(url, json={"chat_id": chat_id, "text": chunk,
                                        "disable_web_page_preview": True}, timeout=20)
        if not resp.ok:
            print(f"  Telegram error {resp.status_code}: {resp.text[:200]}")
            return False
    return True


def find_chat_id():
    """One-time setup: read the latest message sent to the bot and save its chat id."""
    if not CONFIG.exists():
        print("telegram_config.json not found.")
        return 1
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = str(cfg.get("bot_token") or "")
    if not token or token.startswith("PASTE_"):
        print("Paste your bot token into telegram_config.json first.")
        return 1
    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    if not resp.ok:
        print(f"Telegram error {resp.status_code} - check the token is pasted correctly.")
        return 1
    chats = {}
    for upd in resp.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
    if not chats:
        print("No messages found. Open your bot in Telegram, tap Start, send 'hi', then re-run.")
        return 1
    chat_id, name = list(chats.items())[-1]
    cfg["chat_id"] = str(chat_id)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"Found chat id {chat_id} ({name}) - saved to telegram_config.json.")
    return 0


def main():
    if "--get-chat-id" in sys.argv:
        return find_chat_id()
    token, chat_id = load_config()
    if not token or not chat_id:
        print("Telegram alert skipped: no credentials.")
        print("  Create telegram_config.json in the Dashboard folder with:")
        print('    { "bot_token": "<from @BotFather>", "chat_id": "<your id>" }')
        return 0  # don't fail the morning refresh

    today, yest, ydate = daily_movers()
    msg = format_message(today, yest, ydate)
    ok = send(token, chat_id, msg)
    print(f"Telegram alert {'sent' if ok else 'FAILED'}: {len(today)} today, {len(yest)} yesterday.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
