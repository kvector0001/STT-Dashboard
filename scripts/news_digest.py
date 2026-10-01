#!/usr/bin/env python3
"""News & exchange-filings digest for held stocks (tickers + headlines only, no holding values).

Sources: NSE corporate announcements (official filings) + Google News RSS headlines.
Usage: python scripts/news_digest.py [--days 2] [--limit N] [--json] [--backfill] [--fill-new]
  --json      merges the latest items (default: today + yesterday) into news.json, the rolling 6-month archive.
  --backfill  one-off: fills the archive with the last 6 months for every holding.
  --fill-new  nightly: 6-month backfill only for holdings not yet in the archive's backfilled list.
"""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
ARCHIVE = ROOT / "news.json"
KEEP_DAYS = 183
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

# Routine compliance filings that rarely move a stock.
NOISE = re.compile(r"trading window|newspaper|certificate under|loss of share|duplicate|"
                   r"investor complaint|scrutini[sz]er|closure of|record date|esop|esos|"
                   r"reg\.? ?74|74 ?\(5\)|compliances-certificate|book closure|"
                   r"proceedings of (the )?(\d+\w+ )?annual general meeting|voting results|"
                   r"copy of (the )?annual report|notice of (the )?agm", re.I)
# Headlines that only restate the price move.
PRICE_ONLY = re.compile(r"share price (today|live)|stock price today|shares? (rise|fall|gain|drop)s? \d|"
                        r"top (gainers|losers)|stocks to watch|buzzing stocks|trading window|"
                        r"share price and|valuation (view|check|review)|upper circuit|lower circuit|"
                        r"52[- ]week (high|low)|technical (momentum|signals)|share price(?:\s*-|\s*$)|"
                        r"live nse|live bse|price & chart|stock price, news|quote and history|"
                        r"balance sheet|revenue breakdown", re.I)
# Commentary with no direct price impact (interviews, tips, explainers).
LOW_IMPACT = re.compile(r"\bsays\b|interview|explain|\bvs\.?\b|who is winning|opinion|how to|what is|"
                        r"stocks? to (buy|watch)|stock picks|top \d+ stocks|trading guide|recommendations|"
                        r"bullish on|bearish on|should you buy|when should you|\bcsr\b|foundation|"
                        r"convocation|\bjobs?\b|hiring|webinar|award|do you hold", re.I)
# A headline is kept only if it reports a material event or a sharp move.
MATERIAL = re.compile(r"\b(?:orders?|contract|wins?|bags?|secures?|acqui\w*|stake|block deal|bulk deal|"
                      r"merger|amalgamat\w*|demerg\w*|results?|profit|revenue|ebitda|margin|q[1-4]|fy\d\d|"
                      r"dividend|buyback|bonus|split|pledg\w*|promoter|fund ?rais\w*|qip|ipo|rights issue|"
                      r"rating|upgrade\w*|downgrade\w*|target|coverage|\bbuy\b|\bsell\b|penalty|fine[ds]?|"
                      r"notice|raid|gst|tax|approv\w*|usfda|fda|plant|capacity|expan\w*|capex|jv|"
                      r"joint venture|mou|partner\w*|agreement|tie-up|appoint\w*|resign\w*|ceo|cfo|auditor|"
                      r"default|insolven\w*|nclt|court|sebi|launch\w*|allot\w*|invest\w*|jump\w*|surg\w*|"
                      r"soar\w*|plung\w*|slump\w*|crash\w*|rall\w*|zoom\w*|slip\w*|fall\w*|drop\w*|"
                      r"declin\w*|pressure|backlog)\b|₹|\brs\.?\s?\d|crore", re.I)
# Auto-generated / filler publishers.
FILLER_SOURCES = {"univest", "marketsmojo", "kalkine india", "simplywall.st", "equitymaster",
                  "investment guru india", "ad hoc news", "siam.in", "traders union",
                  "value research", "marketbeat", "yahoo finance singapore", "openpr.com",
                  "ein presswire", "issuewire.com"}
# Headlines about a same-named foreign company (US/EU listings, currencies, legal forms).
FOREIGN = re.compile(r"\b(?:nyse|nasdaq|xetra|otc|asx|tsx|han)\s*:|\binc\.?(?=[\s,)]|$)|\boyj\b|\bplc\b|€|\beur\b|\bgmbh\b", re.I)
# Names shared with a global parent or a common word: keep only headlines with Indian-market context.
AMBIGUOUS = {"INGERRAND", "SIEMENS", "ENRIN", "SKFINDUS", "REDINGTON", "GRAPHITE", "POWERINDIA",
             "KENNAMET", "WENDT", "IONEXCHANG", "INCAP", "BBOX", "DLINKINDIA", "HONAUT",
             "SCHNEIDER", "INOXINDIA", "CESC", "MUKANDLTD"}
INDIA_CTX = re.compile(r"\b(?:ltd|limited|nse|bse|sensex|nifty|india|indian|crore|lakh|shares?|stock|fy\d\d|q[1-4])\b|₹|\brs\.?\s?\d", re.I)
_STOP = {"the", "and", "for", "with", "from", "after", "shares", "share", "stock", "stocks", "price",
         "limited", "india", "crore", "order", "orders", "company", "today", "news", "into", "over"}


# Boilerplate wrapped around every NSE filing text; removed so only the crux remains.
_BOILER = [
    r"^.*?\bhas (?:informed|submitted|intimated)(?: to)? the exchange\s+(?:with\s+)?(?:a\s+)?(?:copy(?: of)?\s+)?(?:(?:about|regarding|that|on)\s+)?",
    r"(?:disclosure|intimation) under regulation \d+[^.]*?regulations?,?\s*(?:20\d\d)?\s*[-:,]?\s*",
    r"\s*(?:pursuant to|under) (?:regulation|reg\.)[^.]*",
    r"a press release dated [^,]+,\s*\d{4},?\s*titled\s*",
    r"update on (?:the )?disclosure dated [^,]*?\d{4}\s*(?:on|regarding)?\s*(?:the )?",
    r"^(?:the )?intimation (?:of|regarding|for)\s*",
    r"^(?:general updates|updates)\s*[-:]?\s*",
    r"the disclosure is attached herewith\.?",
    r"^the\s+",
]
_GENERIC_DESC = {"general updates", "updates", "press release", "general update"}


def crux(desc, text):
    """'Company has informed the Exchange about X' -> 'X' (prefixed with the category when it adds info)."""
    t = " ".join((text or "").split())
    if re.search(r"significant movement in price", t, re.I):
        responded = re.search(r"submitted (?:their|its) (?:response|reply)", t, re.I)
        return "Price movement — NSE sought clarification; " + ("company has responded" if responded else "response awaited")
    for pat in _BOILER:
        t = re.sub(pat, "", t, flags=re.I).strip(" .,:-'\"“”")
    if t:
        t = t[0].upper() + t[1:]
    d = (desc or "").strip()
    if not t or t.lower() in (d.lower(), "general updates"):
        return d
    if d.lower() in _GENERIC_DESC or d.lower() in t.lower():
        return t
    return f"{d} — {t}"


def held_stocks():
    prices = json.loads((ROOT / "prices.json").read_text(encoding="utf-8"))
    names = {}
    for s in json.loads((ROOT / "stocks.json").read_text(encoding="utf-8")):
        names[s.get("ticker")] = (s.get("nse_symbol") or s.get("ticker"), s.get("name") or s.get("ticker"))
    out = []
    for tk, s in prices.items():
        if tk.startswith("_") or not isinstance(s, dict) or (s.get("quantity") or 0) <= 0:
            continue
        if (s.get("holding_type") or "Stocks") != "Stocks":
            continue
        sym, name = names.get(tk, (tk, tk))
        out.append((tk, sym, name))
    return sorted(out)


def nse_session():
    s = requests.Session()
    s.headers.update(UA)
    try:
        s.get("https://www.nseindia.com/", timeout=20)
    except Exception:
        pass  # filings() then returns nothing; headlines still work
    return s


def filings(sess, symbol, since):
    try:
        r = sess.get(f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={quote(symbol)}",
                     headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"},
                     timeout=20)
        items = r.json() if r.ok else []
    except Exception:
        return []
    out = []
    for a in items:
        try:
            dt = datetime.strptime(a.get("an_dt", ""), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
        except ValueError:
            continue
        if dt < since:
            continue
        desc, text = a.get("desc") or "", a.get("attchmntText") or ""
        if NOISE.search(desc) or NOISE.search(text):
            continue
        c = crux(desc, text)
        # NSE returns newest first, so the first of a near-duplicate pair (e.g. query then response) wins.
        if any(c == o[1] or _same_story(_story_key(c), _story_key(o[1])) for o in out):
            continue
        out.append((dt, c, a.get("attchmntFile") or ""))
    return out


def _clean_name(name):
    return re.sub(r"\b(limited|ltd\.?|india|l)\b", "", name, flags=re.I).strip(" .,&-()") or name


def _story_key(text):
    """Distinctive numbers + significant words, used to spot the same story from different publishers."""
    nums = {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", text)}
    nums = {n for n in nums if n and not re.fullmatch(r"20\d\d", n) and float(n) >= 10
            and not (n.isdigit() and int(n) <= 31)}  # skip years and day-of-month numbers
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}
    return nums, words


def _same_story(a, b):
    (na, wa), (nb, wb) = a, b
    if na & nb:
        return True
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def headlines(ticker, name, days, max_n=3):
    clean = _clean_name(name)
    # First word(s) of the name must appear in the headline, to avoid same-name foreign companies' noise.
    key_words = [w for w in re.findall(r"[A-Za-z]+", clean) if len(w) > 2][:2]
    q = quote(f'"{clean}" when:{days}d')
    try:
        r = requests.get(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en",
                         headers=UA, timeout=20)
        root = ET.fromstring(r.content)
    except Exception:
        return []
    keys, out = [], []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        body, _, source = title.rpartition(" - ")
        body, source = (body or title).strip(), source.strip()
        if not body or PRICE_ONLY.search(title) or FOREIGN.search(title) or LOW_IMPACT.search(body):
            continue
        if not MATERIAL.search(body):
            continue
        if source.lower() in FILLER_SOURCES:
            continue
        if key_words and not all(w.lower() in body.lower() for w in key_words):
            continue
        if ticker in AMBIGUOUS and not INDIA_CTX.search(body):
            continue
        k = _story_key(body)
        if any(_same_story(k, o) for o in keys):
            continue
        keys.append(k)
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(IST)
        except Exception:
            dt = None
        out.append((dt, body, source, it.findtext("link") or ""))
    return out[:max_n]


def collect(days, limit=None, only=None, max_news=3):
    since = datetime.now(IST) - timedelta(days=days)
    stocks = [s for s in held_stocks() if only is None or s[0] in only][:limit]
    sess = nse_session()
    now_iso = datetime.now(IST).isoformat(timespec="minutes")
    items = []
    for i, (tk, sym, name) in enumerate(stocks, 1):
        f = sorted(filings(sess, sym, since), reverse=True)
        h = headlines(tk, name, days, max_news)
        if f or h:
            items.append({
                "ticker": tk, "name": name,
                "filings": [{"dt": dt.isoformat(), "text": c, "url": u} for dt, c, u in f],
                "news": [{"dt": dt.isoformat() if dt else now_iso, "title": t, "source": s, "url": u}
                         for dt, t, s, u in h],
            })
        time.sleep(0.35)
        if i % 25 == 0:
            print(f"  ...{i}/{len(stocks)}", file=sys.stderr)
    return {"generated": datetime.now(IST).isoformat(timespec="minutes"), "days": days,
            "checked": len(stocks), "items": items}


def _days_apart(a, b):
    try:
        return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).days)
    except (TypeError, ValueError):
        return 999


def merge_archive(new, backfilled_now=()):
    """Fold a fresh collect() result into the rolling archive; dedupe and drop items older than KEEP_DAYS."""
    old = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else {}
    held = {tk for tk, _, _ in held_stocks()}
    backfilled = (set(old.get("backfilled", [])) | set(backfilled_now)) & held
    by = {it["ticker"]: it for it in old.get("items", []) if it["ticker"] in held}
    for it in new["items"]:
        cur = by.setdefault(it["ticker"], {"ticker": it["ticker"], "filings": [], "news": []})
        cur["name"] = it["name"]
        for f in it["filings"]:
            if not any((f["url"] and f["url"] == o["url"]) or
                       (f["text"] == o["text"] and f["dt"][:10] == o["dt"][:10]) for o in cur["filings"]):
                cur["filings"].append(f)
        for n in it["news"]:
            k = _story_key(n["title"])
            # The same story often resurfaces from another publisher a day or two later.
            if any(n["title"] == o["title"] or
                   (_days_apart(n["dt"], o["dt"]) <= 3 and _same_story(k, _story_key(o["title"])))
                   for o in cur["news"]):
                continue
            cur["news"].append(n)
    cutoff = (datetime.now(IST) - timedelta(days=KEEP_DAYS)).isoformat()
    items = []
    for cur in by.values():
        cur["filings"] = sorted((f for f in cur["filings"] if (f["dt"] or "") >= cutoff), key=lambda x: x["dt"], reverse=True)
        cur["news"] = sorted((n for n in cur["news"] if (n["dt"] or "") >= cutoff), key=lambda x: x["dt"], reverse=True)
        if cur["filings"] or cur["news"]:
            items.append(cur)
    return {"generated": new["generated"], "keep_days": KEEP_DAYS, "backfilled": sorted(backfilled), "items": items}


def main():
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 2
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    backfill = "--backfill" in sys.argv
    only, done = None, ()
    if "--fill-new" in sys.argv:
        old = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else {}
        only = {tk for tk, _, _ in held_stocks()} - set(old.get("backfilled", []))
        if not only:
            print("fill-new: every holding already has its 6-month history - nothing to do.")
            return
        print(f"fill-new: backfilling 6 months for {len(only)} new holding(s): {', '.join(sorted(only))}")
        backfill = True
    if backfill:
        days = KEEP_DAYS
    data = collect(days, limit, only=only, max_news=25 if backfill else 3)
    if backfill:
        done = [it[0] for it in held_stocks() if only is None or it[0] in only][:limit]
    if "--json" in sys.argv or backfill:
        arch = merge_archive(data, done)
        ARCHIVE.write_text(json.dumps(arch, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n_f = sum(len(i["filings"]) for i in arch["items"])
        n_h = sum(len(i["news"]) for i in arch["items"])
        print(f"news.json archive: {len(arch['items'])} holdings, {n_f} filings, {n_h} headlines "
              f"(last {KEEP_DAYS} days, {ARCHIVE.stat().st_size // 1024} KB)")
        return
    items = data["items"]
    print(f"NEWS & FILINGS - last {days} days - {data['checked']} holdings checked, {len(items)} with news\n")
    for it in items:
        print(f"== {it['ticker']} ({it['name']})")
        for f in it["filings"]:
            print(f"  [FILING {f['dt'][5:16].replace('T', ' ')}] {f['text'][:200]}")
        for n in it["news"]:
            print(f"  [NEWS {(n['dt'] or '')[5:10]}] {n['title'][:170]} - {n['source']}")
        print()


if __name__ == "__main__":
    main()
