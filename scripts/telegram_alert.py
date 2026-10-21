#!/usr/bin/env python3
"""Send portfolio alerts to a Telegram chat (percentages only - no rupee values).

What is sent depends on the IST time of the run (or --slot):
  morning / midday / close (9:30, 12:30, 2:30) : two messages, each with unsent key news per stock
      1. Price moves ±5% (any volume)   2. Price + volume moves (today or yesterday)
  after   (>=15:00)   : nothing (post-close price/action-log refresh only)
  --weekend           : top 5 gainers/losers of the week and month + the news behind them
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
        ret = _pct(r["ret"])
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
    # Telegram has no font colours, so a coloured dot marks direction.
    if not isinstance(v, (int, float)):
        return "\u2014"
    dot = "\U0001f7e2" if v >= 0 else "\U0001f534"
    return f"{dot} {v:+.1f}%"


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
BIG_MOVE = 5.0   # "price only" message: any holding moving this much today, whatever the volume


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


def _collect(tickers, days, max_news=3):
    from news_digest import collect, mark_duplicates
    data = collect(days, only=set(tickers), max_news=max_news)
    for it in data["items"]:
        mark_duplicates(it.get("name", ""), it["filings"], it["news"])
    return {it["ticker"]: it for it in data["items"]}


def _pick(it, tk, sent, since):
    """Up to ITEMS_PER_STOCK unsent key items dated >= since -> (message lines, new sent-entries)."""
    from news_digest import is_key_news, summarize_pdf
    today = datetime.now(IST).strftime("%Y-%m-%d")
    items = [("\U0001f3db", f["url"], f["text"], f"({f['dt'][8:10]}/{f['dt'][5:7]})", f["dt"]) for f in it["filings"] if not f.get("dup")]
    items += [("\U0001f5de", n["url"], n["title"], f"\u2014 {_h(n['source'])}", n["dt"]) for n in it["news"] if not n.get("dup")]
    lines, new = [], []
    for icon, url, text, tail, dt in items:
        if len(new) == ITEMS_PER_STOCK:
            break
        if (dt or "")[:10] < since or not is_key_news(text) or _was_sent(sent + new, tk, url, text):
            continue
        lines.append(f"{icon} {_a(url, text[:140])} {tail}")
        if icon == "\U0001f3db" and url.endswith(".pdf"):
            summary = summarize_pdf(url, text)
            if summary:
                lines.append(f"     <i>{_h(summary)}</i>")
        new.append({"tk": tk, "u": url, "t": text, "d": today})
    return lines, new


def moves_message(title, note, rows, by_tk, sent, empty):
    """One weekday message: each stock's line, then its unsent key news (today/yesterday, up to 3).
    rows = [(ticker, header line)] in display order. Returns (text, new sent-entries)."""
    yday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    lines, new = [f"<b>{title}</b>", f"<i>{note}</i>", ""], []
    if not rows:
        lines.append(empty)
        return "\n".join(lines), new
    for tk, head in rows:
        picked = []
        if by_tk is not None:
            try:
                picked, got = _pick(by_tk.get(tk) or {"filings": [], "news": []}, tk, sent + new, yday)
                new += got
            except Exception as e:  # a news problem must never stop the price lines
                print(f"  news for {tk} failed ({type(e).__name__}: {e})")
        lines.append(head)
        if picked:
            lines += picked + [""]
    if new:
        lines += ["", "\U0001f3db = official NSE filing \u00b7 \U0001f5de = news headline"]
    return "\n".join(lines).rstrip(), new


def weekday_messages(held, sent, with_news=True):
    """The two weekday messages (9:30, 12:30, 2:30): price-only moves, then price + volume moves, each with news."""
    now = datetime.now(IST)
    big = sorted(((tk, s["ret_1d"]) for tk, s in held
                  if isinstance(s.get("ret_1d"), (int, float)) and abs(s["ret_1d"]) >= BIG_MOVE), key=lambda x: -abs(x[1]))
    vp = sorted(vp_movers(held).items(), key=lambda kv: -max(abs(r) for _, r, _ in kv[1]))
    by_tk = None
    if with_news:
        try:
            by_tk = _collect({tk for tk, _ in big} | {tk for tk, _ in vp}, 2)
        except Exception as e:
            print(f"  news fetch failed ({type(e).__name__}: {e}) - sending prices only")
    tags = dict(held)
    msg1, new1 = moves_message(
        f"\u26a1 Price moves \u00b1{BIG_MOVE:.0f}% \u2014 {now:%a %d %b, %H:%M}", "Any holding moving 5%+ today, whatever the volume",
        [(tk, f"<b>{_h(tk)}</b>  {_pct(r)}") for tk, r in big], by_tk, sent, "No holding has moved \u00b15% today.")
    vp_rows = []
    for tk, hits in vp:
        tag = tags[tk].get("movers")
        head = " \u00b7 ".join(f"{lbl} {_pct(r)} on {v:.1f}\u00d7 vol" for lbl, r, v in hits)
        vp_rows.append((tk, f"<b>{_h(tk)}</b>  {head}" + (f"  {_h(tag)}" if tag not in BLANK else "")))
    msg2, new2 = moves_message(
        f"\U0001f4ca Price + volume moves \u2014 {now:%a %d %b, %H:%M}",
        "5%+ on 1.5\u00d7 normal volume, or 3%+ on 3\u00d7 \u2014 today or yesterday",
        vp_rows, by_tk, sent + new1, "No price + volume movers.")
    return [msg1, msg2], new1 + new2


def weekend_message(held, sent):
    """Weekend: top-5 gainers AND losers of the week (1W) and month (1M) + the key news behind them (never repeated).
    News window: last 7 days for the weekly lists, last 30 days for the monthly lists."""
    wk_up, wk_dn = _top(held, "ret_1w")
    mo_up, mo_dn = _top(held, "ret_1m")
    by_tk = _collect({tk for tk, _ in wk_up + wk_dn + mo_up + mo_dn}, 30, max_news=8)
    now = datetime.now(IST)
    lines, new, shown = [f"\U0001f3c6 <b>Weekend \u2014 top gainers &amp; losers and the news behind them</b> ({now:%a %d %b})", ""], [], set()
    groups = (("THIS WEEK \u2014 \u25b2 GAINERS", wk_up, 7), ("THIS WEEK \u2014 \u25bc LOSERS", wk_dn, 7),
              ("THIS MONTH \u2014 \u25b2 GAINERS", mo_up, 30), ("THIS MONTH \u2014 \u25bc LOSERS", mo_dn, 30))
    for label, rows, back in groups:
        lines.append(f"<b>{label}</b>")
        since = (now - timedelta(days=back)).strftime("%Y-%m-%d")
        for tk, v in rows:
            lines.append(f"<b>{_h(tk)}</b>  {_pct(v)}")
            if tk in shown:
                lines.append("   news above")
                continue
            shown.add(tk)
            picked, got = _pick(by_tk.get(tk) or {"filings": [], "news": []}, tk, sent + new, since)
            new += got
            lines += picked or ["   no new key news"]
        lines.append("")
    lines.append("\U0001f3db = official NSE filing \u00b7 \U0001f5de = news headline")
    # Prices don't move on weekends: after the first Saturday run, only send when there is new news.
    if not new and not (now.weekday() == 5 and now.hour < 14):
        return None, len(shown), []
    return "\n".join(lines), len(shown), new


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


def prices_are_live(held, max_age_min=45):
    """True when this run really fetched today's prices: most holdings were updated in the last `max_age_min`
    minutes and most show a non-zero 1D move (all-zero = market data not open yet / stale fallback)."""
    now = datetime.now(timezone.utc)
    fresh = moved = 0
    for _, s in held:
        try:
            upd = datetime.strptime(str(s.get("updated", ""))[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            fresh += (now - upd) <= timedelta(minutes=max_age_min)
        except ValueError:
            pass
        moved += isinstance(s.get("ret_1d"), (int, float)) and s["ret_1d"] != 0
    n = max(len(held), 1)
    return fresh / n >= 0.8 and moved / n >= 0.5, fresh, moved


def _gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in kv.items())


def main():
    if "--get-chat-id" in sys.argv:
        return find_chat_id()
    slot = sys.argv[sys.argv.index("--slot") + 1] if "--slot" in sys.argv else current_slot()
    if "--weekend" in sys.argv:
        slot = "weekend"
    dry = "--dry-run" in sys.argv
    retry = "--retry" in sys.argv
    if slot == "after":
        print("Telegram alert: post-close refresh - nothing sent.")
        return 0

    held = load_held()
    if slot != "weekend" and not dry and "--skip-live-check" not in sys.argv:
        live, fresh, moved = prices_are_live(held)
        if not live:
            print(f"Prices not live yet ({fresh}/{len(held)} updated recently, {moved} with a 1D move).")
            if not retry:
                _gh_output(stale="true", slot=slot)  # the workflow refreshes again in 30 min and re-runs this slot
                return 0
            token, chat_ids = load_config()
            warn = (f"\u26a0\ufe0f {datetime.now(IST):%a %d %b %H:%M} \u2014 live prices still not available after a retry. "
                    "Movers alert skipped; please check the dashboard.")
            for cid in chat_ids:
                send(token, cid, warn)
            return 0
    messages, summary = [], []
    new_sent = []
    if slot == "weekend":
        # No trading: top weekly/monthly gainers + the key news behind them.
        msg, n, new_sent = weekend_message(held, load_sent())
        if msg:
            messages.append((msg, True))
        summary.append(f"weekend gainers ({n} stocks)")
    else:
        msgs, new_sent = weekday_messages(held, load_sent(), "--no-news" not in sys.argv)
        messages += [(m, True) for m in msgs]
        summary.append("price moves + price/volume moves")

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
