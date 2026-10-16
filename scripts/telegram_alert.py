#!/usr/bin/env python3
"""Send portfolio alerts to a Telegram chat (percentages only - no rupee values).

What is sent depends on the IST time of the run (or --slot):
  morning (<11:00)    : daily movers + reversal watch
  midday  (11-14:00)  : daily movers + key news for volume+price movers
  close   (14-15:00)  : daily movers + top gainers/losers + key news not sent at 12:30
  after   (>=15:00)   : nothing (post-close price/action-log refresh only)
News already sent (telegram_sent.json) is never sent again.
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
SENT = ROOT / "telegram_sent.json"
SENT_KEEP_DAYS = 14
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
    return "morning" if h < 11 else "midday" if h < 14 else "close" if h < 15 else "after"


def _h(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _a(url, text):
    text = _h(text)
    return f'<a href="{_h(url)}">{text}</a>' if str(url or "").startswith("https://") else text


ITEMS_PER_STOCK = 3


def is_vp_move(ret, vol):
    """Volume + price mover: >=5% move on >=1.5x the 30-day avg volume, or >=3% on >=3x.
    Same rule as the News page's Movers chip."""
    if not isinstance(ret, (int, float)) or not isinstance(vol, (int, float)):
        return False
    return (abs(ret) >= 5 and vol >= 1.5) or (abs(ret) >= 3 and vol >= 3)


def vp_movers(held):
    """{ticker: [(label, ret %, vol x), ...]} for held stocks that were volume+price movers today or yesterday."""
    out = {}
    for tk, s in held:
        y = s.get("mv_yest") or {}
        hits = [(lbl, r, v) for lbl, r, v in (("today", s.get("ret_1d"), s.get("vol_today_ratio")),
                                              ("yday", y.get("r"), y.get("v"))) if is_vp_move(r, v)]
        if hits:
            out[tk] = hits
    return out


def load_sent():
    try:
        return json.loads(SENT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_sent(entries):
    cutoff = (datetime.now(IST) - timedelta(days=SENT_KEEP_DAYS)).strftime("%Y-%m-%d")
    SENT.write_text(json.dumps([e for e in entries if e.get("d", "") >= cutoff], indent=1, ensure_ascii=False),
                    encoding="utf-8")


def _was_sent(sent, tk, url, text):
    from news_digest import _same_story, _story_key
    k = _story_key(text)
    return any((url and e.get("u") == url) or
               (e.get("tk") == tk and (e.get("t") == text or _same_story(k, _story_key(e.get("t", "")))))
               for e in sent)


def news_message(moves, sent, followup=False, days=2):
    """Key (structural) news for volume+price movers, up to 3 per stock, skipping anything sent before.
    Returns (text or None, stocks shown, new sent-entries)."""
    from news_digest import collect, is_key_news, mark_duplicates, summarize_pdf
    data = collect(days, only=set(moves))
    by_tk = {it["ticker"]: it for it in data["items"]}
    for it in data["items"]:
        mark_duplicates(it.get("name", ""), it["filings"], it["news"])
    order = sorted(moves, key=lambda tk: -max(abs(r) for _, r, _ in moves[tk]))
    today = datetime.now(IST).strftime("%Y-%m-%d")
    yday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    title = ("More key news since 12:30" if followup
             else "Key news (today &amp; yesterday) \u2014 volume + price movers")
    lines, quiet, new = [f"\U0001f4f0 <b>{title}</b>", ""], [], []
    for tk in order:
        it = by_tk.get(tk) or {"filings": [], "news": []}
        items = [("\U0001f3db", f["url"], f["text"], f"({f['dt'][8:10]}/{f['dt'][5:7]})", f["dt"]) for f in it["filings"] if not f.get("dup")]
        items += [("\U0001f5de", n["url"], n["title"], f"\u2014 {_h(n['source'])}", n["dt"]) for n in it["news"] if not n.get("dup")]
        picked = []
        for icon, url, text, tail, dt in items:
            if len(picked) == ITEMS_PER_STOCK:
                break
            if (dt or "")[:10] < yday or not is_key_news(text) or _was_sent(sent + new, tk, url, text):
                continue
            picked.append(f"{icon} {_a(url, text[:140])} {tail}")
            if icon == "\U0001f3db" and url.endswith(".pdf"):
                summary = summarize_pdf(url, text)
                if summary:
                    picked.append(f"     <i>{_h(summary)}</i>")
            new.append({"tk": tk, "u": url, "t": text, "d": today})
        if not picked:
            quiet.append(tk)
            continue
        mv = " \u00b7 ".join(f"{lbl} {_pct(r)} on {v:.1f}\u00d7 vol" for lbl, r, v in moves[tk])
        lines += [f"<b>{_h(tk)}</b>  ({mv})", *picked, ""]
    if not new:
        return None, 0, []
    if quiet and not followup:
        lines.append("No new key news: " + ", ".join(_h(t) for t in quiet))
    lines.append("\U0001f3db = official NSE filing \u00b7 \U0001f5de = news headline")
    return "\n".join(lines), len(order) - len(quiet), new


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
    if slot == "after":
        print("Telegram alert: post-close refresh - nothing sent.")
        return 0

    held = load_held()
    messages, summary = [], []
    today, yest, ydate = daily_movers(held)
    messages.append((format_message(today, yest, ydate), False))
    summary.append(f"{len(today)} today, {len(yest)} yesterday")
    if slot in ("morning", "all"):
        msg, n, _ = reversal_message(held)
        messages.append((msg, False))
        summary.append(f"{n} reversal")
    if slot in ("close", "all"):
        messages.append((gainers_losers_message(held), False))
        summary.append("gainers/losers")
    new_sent = []
    moves = vp_movers(held)
    if slot in ("midday", "close", "all") and moves and "--no-news" not in sys.argv:
        msg, n, new_sent = news_message(moves, load_sent(), followup=slot == "close")
        if msg:
            messages.append((msg, True))
        summary.append(f"key news for {n}/{len(moves)} volume+price movers")

    if not messages:
        print(f"Telegram alert [{slot}]: nothing new to send.")
        return 0
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
    if new_sent and any(results):
        save_sent(load_sent() + new_sent)
    print(f"Telegram alert [{slot}] {'sent' if ok else 'FAILED'} to {len(chat_ids)} chat(s): {', '.join(summary)}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
