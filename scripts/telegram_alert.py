#!/usr/bin/env python3
"""Send portfolio alerts to a Telegram chat (percentages only - no rupee values).

What is sent depends on the IST time of the run (or --slot):
  morning (<11:00)   : daily movers + reversal watch + news & filings for those names
  midday  (11-14:00) : daily movers only
  close   (>=14:00)  : daily movers + top gainers/losers (daily + weekly)
Meant to run right after fetch_prices.py so the data is fresh.

Flags: --slot morning|midday|close|all   --dry-run (print, don't send)   --get-chat-id

Config (never committed): a `telegram_config.json` in the Dashboard root, or the
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables.
    { "bot_token": "123456:ABC-DEF...", "chat_id": "123456789" }
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from momentum_classifier import classify_daily  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "prices.json"
CONFIG = ROOT / "telegram_config.json"
IST = timezone(timedelta(hours=5, minutes=30))
TOP_N = 5

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
    """Return (token, [chat_ids]). chat_id may be a comma-separated list (you, family group/channel)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id) and CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
    if not token or not chat_id or str(token).startswith("PASTE_"):
        return None, []
    return str(token), [c.strip() for c in str(chat_id).split(",") if c.strip()]


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


def load_held():
    """Held equity positions (matches the dashboard's default 'Stocks' view)."""
    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    return [(tk, s) for tk, s in prices.items()
            if not tk.startswith("_") and isinstance(s, dict)
            and (s.get("quantity") or 0) > 0
            and (s.get("holding_type") or "Stocks") == "Stocks"]


def daily_movers(held):
    """Return (today_rows, yesterday_rows, yesterday_date) for held stocks."""
    today, yest, ydate = [], [], None
    for tk, s in held:
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
    now = datetime.now(IST)
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


def _pct(v):
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "\u2014"


def reversal_message(held):
    # Same rule as the dashboard's 🔎 Reversal action (deep below ATH but jumping).
    rows = [(tk, s["ret_1m"], s["ath_pct"]) for tk, s in held
            if isinstance(s.get("ath_pct"), (int, float)) and s["ath_pct"] < -40
            and isinstance(s.get("ret_1m"), (int, float)) and s["ret_1m"] > 15]
    rows.sort(key=lambda r: -r[1])
    now = datetime.now(IST)
    lines = [f"\U0001f50e Reversal Watch \u2014 {now:%a %d %b} \u2014 {len(rows)}",
             "More than 40% below all-time high but up over 15% in a month.",
             "Research signal only \u2014 check for a real fundamental shift.", ""]
    if not rows:
        lines.append("  No reversal names today.")
    for tk, r1m, ath in rows:
        lines.append(f"{tk}   1M {_pct(r1m)} \u00b7 {ath:.0f}% from ATH")
    return "\n".join(lines), len(rows), [r[0] for r in rows]


def _top(held, field, n=TOP_N):
    vals = [(tk, s[field]) for tk, s in held if isinstance(s.get(field), (int, float))]
    gainers = sorted([v for v in vals if v[1] > 0], key=lambda v: -v[1])[:n]
    losers = sorted([v for v in vals if v[1] < 0], key=lambda v: v[1])[:n]
    return gainers, losers


def gainers_losers_message(held):
    now = datetime.now(IST)
    lines = [f"\U0001f3c1 Top Gainers & Losers \u2014 {now:%a %d %b}", ""]
    for label, field in (("DAILY", "ret_1d"), ("WEEKLY", "ret_1w")):
        gainers, losers = _top(held, field)
        lines.append(label)
        lines.append("\u25b2 Gainers")
        lines += [f"  {tk}   {_pct(v)}" for tk, v in gainers] or ["  \u2014"]
        lines.append("\u25bc Losers")
        lines += [f"  {tk}   {_pct(v)}" for tk, v in losers] or ["  \u2014"]
        lines.append("")
    return "\n".join(lines).rstrip()


def current_slot():
    h = datetime.now(IST).hour
    return "morning" if h < 11 else "midday" if h < 14 else "close"


def _h(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _a(url, text):
    text = _h(text)
    return f'<a href="{_h(url)}">{text}</a>' if str(url or "").startswith("https://") else text


def news_message(tickers, days=2):
    """'Why they moved': exchange filings + headlines (tappable links) for the alerted tickers only."""
    from news_digest import collect
    data = collect(days, only=set(tickers))
    by_tk = {it["ticker"]: it for it in data["items"]}
    lines = ["\U0001f4f0 <b>Why they moved</b> — filings &amp; news (last 2 days)", ""]
    shown = 0
    for tk in tickers:
        it = by_tk.get(tk)
        if not it:
            continue
        shown += 1
        lines.append(f"<b>{_h(tk)}</b>")
        for f in it["filings"][:2]:
            lines.append(f"\U0001f3db {_a(f['url'], f['text'][:140])} ({f['dt'][8:10]}/{f['dt'][5:7]})")
        for n in it["news"][:2]:
            lines.append(f"\U0001f5de {_a(n['url'], n['title'][:140])} — {_h(n['source'])}")
        lines.append("")
    if not shown:
        lines.append("No filings or news found for today's alerted stocks.")
    lines.append("\U0001f3db = official NSE filing · \U0001f5de = news headline")
    return "\n".join(lines), shown


def send(token, chat_id, text, html=False):
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
        payload = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if html:
            payload["parse_mode"] = "HTML"
        resp = requests.post(url, json=payload, timeout=20)
        if not resp.ok:
            print(f"  Telegram error {resp.status_code}: {resp.text[:200]}")
            return False
    return True


def find_chat_id():
    """One-time setup: list chats the bot can see; save the newest group/channel (else newest private chat)."""
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
        # my_chat_member arrives when the bot is added to a group/channel.
        msg = (upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member")
               or upd.get("chat_member") or {})
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
            chats[chat["id"]] = (chat.get("type", "?"), name)
    if not chats:
        print("No chats found. Send a message to the bot (or post in the group/channel it was added to), then re-run.")
        return 1
    for cid, (ctype, name) in chats.items():
        print(f"  {ctype:<10} {cid}  {name}")
    if "--all" in sys.argv:
        # Add everyone who messaged the bot to the existing recipients (family members).
        existing = [c.strip() for c in str(cfg.get("chat_id") or "").split(",") if c.strip()]
        merged = existing + [str(c) for c in chats if str(c) not in existing]
        cfg["chat_id"] = ",".join(merged)
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print(f"Recipients now ({len(merged)}): {cfg['chat_id']}")
        return 0
    shared = [cid for cid, (ctype, _) in chats.items() if ctype in ("group", "supergroup", "channel")]
    chat_id = shared[-1] if shared else list(chats)[-1]
    cfg["chat_id"] = str(chat_id)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"Saved chat id {chat_id} ({chats[chat_id][1]}) to telegram_config.json.")
    return 0


def main():
    if "--get-chat-id" in sys.argv:
        return find_chat_id()
    slot = sys.argv[sys.argv.index("--slot") + 1] if "--slot" in sys.argv else current_slot()
    dry = "--dry-run" in sys.argv

    held = load_held()
    today, yest, ydate = daily_movers(held)
    messages = [(format_message(today, yest, ydate), False)]
    summary = [f"{len(today)} today, {len(yest)} yesterday"]
    alerted = [r["ticker"] for r in today + yest]
    if slot in ("morning", "all"):
        msg, n, rev = reversal_message(held)
        messages.append((msg, False))
        summary.append(f"{n} reversal")
        alerted += rev
    if slot in ("close", "all"):
        messages.append((gainers_losers_message(held), False))
        summary.append("gainers/losers")
    alerted = list(dict.fromkeys(alerted))
    # News goes out once a day (morning) to keep the chat quiet.
    if slot in ("morning", "all") and alerted and "--no-news" not in sys.argv:
        msg, n = news_message(alerted)
        messages.append((msg, True))
        summary.append(f"news for {n}/{len(alerted)}")

    if dry:
        print("\n\n==========\n\n".join(m for m, _ in messages))
        return 0

    token, chat_ids = load_config()
    if not token or not chat_ids:
        print("Telegram alert skipped: no credentials.")
        print("  Create telegram_config.json in the Dashboard folder with:")
        print('    { "bot_token": "<from @BotFather>", "chat_id": "<your id>" }')
        return 0  # don't fail the morning refresh

    # Send to every chat even if one fails.
    results = [send(token, cid, m, html) for cid in chat_ids for m, html in messages]
    ok = all(results)
    print(f"Telegram alert [{slot}] {'sent' if ok else 'FAILED'} to {len(chat_ids)} chat(s): {', '.join(summary)}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
