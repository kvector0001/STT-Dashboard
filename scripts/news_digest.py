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
                   r"notice of (the )?(\d+\w+ )?annual general meeting|agm proceedings|^shareholders meeting$|"
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
FOREIGN = re.compile(r"\b(?:nyse|nasdaq|xetra|otc|asx|tsx|han)\s*:|\binc\.?(?=[\s,)]|$)|\boyj\b|\bplc\b|€|\beur\b|\bsek\b|\bgmbh\b", re.I)
# Names shared with a global parent or a common word: keep only headlines with Indian-market context.
AMBIGUOUS = {"INGERRAND", "SIEMENS", "ENRIN", "SKFINDUS", "REDINGTON", "GRAPHITE", "POWERINDIA",
             "KENNAMET", "WENDT", "IONEXCHANG", "INCAP", "BBOX", "DLINKINDIA", "HONAUT",
             "SCHNEIDER", "INOXINDIA", "CESC", "MUKANDLTD", "RAYMOND", "EIHOTEL", "NLCINDIA",
             "JNKINDIA", "RKSWAMY", "WHIRLPOOL", "TRIVENIPT"}
INDIA_CTX = re.compile(r"\b(?:ltd|limited|nse|bse|sensex|nifty|india|indian|crores?|lakhs?|shares|fy\d\d|q[1-4]|sebi|rbi|nclt|"
                       r"mumbai|delhi|bengaluru|bangalore|pune|chennai|hyderabad|kolkata|ahmedabad|noida|gurugram|thane|"
                       r"gujarat|maharashtra|andhra|telangana|karnataka|tamil nadu|rajasthan|odisha|kerala|punjab|haryana|"
                       r"kotak|motilal|icici|hdfc|axis|nuvama|emkay|ambit|sharekhan|anand rathi|jm financial|prabhudas|"
                       r"bombay|share price)\b"
                       r"|₹|\brs\.?\s?\d", re.I)
# Well-known namesakes that share a holding's name.
NAMESAKES = {"RAYMOND": re.compile(r"raymond james|st\.? raymond|raymond weil|raymond chandler|raymond stauffer", re.I)}
_STOP = {"the", "and", "for", "with", "from", "after", "shares", "share", "stock", "stocks", "price",
         "limited", "india", "crore", "order", "orders", "company", "today", "news", "into", "over"}
# Date/scheduling announcements (next earnings call, record date, board-meeting dates...) - not news.
SCHEDULE = re.compile(r"(?:schedules?|to (?:hold|host)|hosts?|sets?)\b[^.]{0,40}\b(?:earnings|conference|con\.?) call|"
                      r"(?:earnings|conference) call (?:on|at|scheduled|for)\b|"
                      r"analysts?/institutional investor meet|schedule of (?:analyst|meet)|"
                      r"(?:to |scheduled to )?meet(?:s|ing)? (?:with )?analysts|"
                      r"analysts? (?:and investors? )?meet|investors? meets?\b|investor conference|"
                      r"record date|ex[- ]?dividend|ex[- ]date|last (?:day|chance) to buy|dividend history|payment date|"
                      r"board meeting intimation|intimation of board meeting|prior intimation|"
                      r"board (?:meeting )?to (?:meet|consider)|to (?:announce|declare|consider)\b[^.]{0,40}\bresults|"
                      r"results? date|e-voting schedule", re.I)
MAX_NEWS_PER_DAY = 3
# Structural, business-changing events (used for the Telegram "key news" digest).
KEY_NEWS = re.compile(r"\b(?:orders?|order book|order inflow|contracts?|tenders?|l1|lo[ai]|letter of (?:award|intent)|"
                      r"bags?|secures?|wins?|won|awarded|acqui\w*|stake|merger|amalgamat\w*|demerg\w*|takeover|"
                      r"open offer|divest\w*|slump sale|results?|earnings|net profit|profit|loss|revenue|ebitda|"
                      r"margins?|guidance|buyback|bonus|split|fund ?rais\w*|qip|rights issue|preferential|ipo|"
                      r"offer for sale|ofs|block deal|bulk deal|pledg\w*|court|tribunal|nclt|nclat|sebi|cci|"
                      r"penalt\w*|fine[ds]?|raids?|probe|investigat\w*|fraud|show[- ]cause|gst|tax demand|"
                      r"income tax|litigation|arbitra\w*|lawsuit|insolven\w*|default\w*|usfda|fda|warning letter|"
                      r"form 483|eir|licen[cs]e\w*|patent|plant|facility|factor(?:y|ies)|capacity|expan\w*|"
                      r"capex|commission\w*|greenfield|brownfield|shutdown|fire|strike|accident|joint venture|jv|"
                      r"mou|partner\w*|agreement|tie-?up|collaborat\w*|ceo|cfo|coo|managing director|chairman|"
                      r"auditor|resign\w*|steps? down|credit rating|crisil|icra|care ratings|launch\w*|"
                      r"sales|bookings|pre-?sales|volumes?|q[1-4]|fy\d\d|cto|dispos\w*|subsidiar\w*|"
                      r"price (?:hike|increase|cut)s?|"
                      r"invest(?:s|ed|ing|ment)?)\b", re.I)
# Market commentary that mentions a business word but doesn't report an event.
COMMENTARY = re.compile(r"why is (?:the )?stock|should (?:you|investors)|buy,? sell or hold|target price|"
                        r"price target|\bupside\b|\bdownside\b|sector stocks|stocks? (?:today|in focus|to watch)|"
                        r"ahead of|multibagger|buying opportunity|nse sought clarification|\?\s*$", re.I)
# Routine people/payout events - not key news (unless they also carry a resignation or a corporate action).
NOT_KEY = re.compile(r"\b(?:re-?)?appoint\w*|\bnamed (?:as )?(?:the )?(?:new )?(?:ceo|cfo|coo|cto|md|chairman|director|auditor)|"
                     r"\bdividend\w*|\bgovernor\b", re.I)
KEEP_ANYWAY = re.compile(r"resign\w*|steps? down|quits?\b|bonus|buyback|split|demerg\w*", re.I)


def is_key_news(text):
    """Structural news (orders, deals, results, legal/regulatory, capacity, resignations) - not price chatter,
    appointments or dividends."""
    t = text or ""
    if NOT_KEY.search(t) and not KEEP_ANYWAY.search(t):
        return False
    if t.count(",") >= 4 or re.search(r"\btargets\b|\bpreview\b|transcript", t, re.I):  # multi-stock lists, previews
        return False
    return bool(KEY_NEWS.search(t)) and not COMMENTARY.search(t)


def is_schedule(text):
    """Date/scheduling announcement. Kept if it also carries real news (transcript, demerger, buyback...)."""
    return bool(SCHEDULE.search(text or "")) and not re.search(
        r"transcript|demerg|merger|amalgamat|buyback|acqui|bonus issue|stock split", text or "", re.I)


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
    m = re.search(r"significant (movement in price|increase in volume)", t, re.I)
    if m:
        responded = re.search(r"submitted (?:their|its) (?:response|reply)", t, re.I)
        what = "Price movement" if "price" in m.group(1).lower() else "Spurt in volume"
        return f"{what} — NSE sought clarification; " + ("company has responded" if responded else "response awaited")
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
        if NOISE.search(desc) or NOISE.search(text) or is_schedule(f"{desc} {text}"):
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


def _key_words(name):
    return [w for w in re.findall(r"[A-Za-z]+", _clean_name(name)) if len(w) > 2][:2]


_BOILER_WORDS = {"industries", "industry", "press", "release", "titled", "hereby", "submit", "submitted", "exchange",
                 "general", "update", "outcome", "meeting", "board", "directors", "regulation", "disclosure",
                 "intimation", "pursuant", "held", "informed", "respect", "attached", "herewith", "listing"}


def _event_key(text, name):
    """Like _story_key but ignores the company's own name, filing boilerplate and plural endings."""
    nums, words = _story_key(text)
    own = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", name or "")}
    stem = lambda w: w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
    return nums, {stem(w) for w in words if w not in own} - _BOILER_WORDS


def _same_event(a, b):
    (na, wa), (nb, wb) = a, b
    # A shared distinctive figure (3+ digits or a decimal, e.g. 202 crore / 92.95) marks the same event.
    if any(len(n) >= 3 or "." in n for n in na & nb):
        return True
    return len(wa) >= 3 and len(wb) >= 3 and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def mark_duplicates(name, filings, news, days=2):
    """Group a company's filings + headlines that report the same event (within `days`); set dup=True on all
    but one per group. The visible item is the most informative one (most distinct words; a filing wins ties)."""
    items = [("f", f, f["text"]) for f in filings] + [("n", n, n["title"]) for n in news]
    keys = [_event_key(t, name) for _, _, t in items]
    parent = list(range(len(items)))
    find = lambda i: i if parent[i] == i else find(parent[i])
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _days_apart(items[i][1]["dt"], items[j][1]["dt"]) <= days and _same_event(keys[i], keys[j]):
                parent[find(j)] = find(i)
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    for idx in groups.values():
        main = max(idx, key=lambda i: (len(keys[i][1]) + len(keys[i][0]), items[i][0] == "f"))
        for i in idx:
            items[i][1]["dup"] = i != main


_SIBLINGS = {}


def _longer_siblings(name):
    """Clean names of other holdings that start with this holding's name plus more words."""
    base = _clean_name(name).lower()
    if base not in _SIBLINGS:
        try:
            names = {_clean_name(n).lower() for _, _, n in held_stocks()}
        except Exception:
            names = set()
        _SIBLINGS[base] = [n for n in names if n != base and n.startswith(base + " ")]
    return _SIBLINGS[base]


def keep_headline(ticker, name, body, source=""):
    """All headline filters in one place (also re-applied to the stored archive)."""
    title = f"{body} - {source}"
    if not body or PRICE_ONLY.search(title) or FOREIGN.search(title) or LOW_IMPACT.search(body):
        return False
    if is_schedule(body):
        return False
    if not MATERIAL.search(body) or source.lower() in FILLER_SOURCES:
        return False
    kw = _key_words(name)
    # The company's name must appear in the headline.
    if kw and not all(w.lower() in body.lower() for w in kw):
        return False
    if ticker in NAMESAKES and NAMESAKES[ticker].search(body):
        return False
    # "Cyient" must not pick up "Cyient DLM" (another holding whose name extends this one).
    if any(s in body.lower() for s in _longer_siblings(name)):
        return False
    # Names that collide with unrelated companies/people/places: need Indian-market context.
    if ticker in AMBIGUOUS and not INDIA_CTX.search(body):
        return False
    return True


def headlines(ticker, name, days, max_n=3):
    clean = _clean_name(name)
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
        if not keep_headline(ticker, name, body, source):
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
        cur["filings"] = sorted((f for f in cur["filings"] if (f["dt"] or "") >= cutoff
                                 and not is_schedule(f["text"]) and not NOISE.search(f["text"])),
                                key=lambda x: x["dt"], reverse=True)
        for f in cur["filings"]:
            f["key"] = is_key_news(f["text"])
        # Re-check stored headlines so filter improvements also clean older entries.
        news = sorted((n for n in cur["news"] if (n["dt"] or "") >= cutoff
                       and keep_headline(cur["ticker"], cur.get("name", ""), n["title"], n.get("source", ""))),
                      key=lambda x: x["dt"], reverse=True)
        per_day = {}
        cur["news"] = []
        for n in news:
            d = n["dt"][:10]
            if per_day.get(d, 0) < MAX_NEWS_PER_DAY:
                per_day[d] = per_day.get(d, 0) + 1
                n["key"] = is_key_news(n["title"])
                cur["news"].append(n)
        mark_duplicates(cur.get("name", ""), cur["filings"], cur["news"])
        if cur["filings"] or cur["news"]:
            items.append(cur)
    return {"generated": new["generated"], "keep_days": KEEP_DAYS, "backfilled": sorted(backfilled), "items": items}


def main():
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 2
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    backfill = "--backfill" in sys.argv
    only, done = None, ()
    if "--refilter" in sys.argv:
        # Clean the stored archive with the current filters, without fetching anything.
        old = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        arch = merge_archive({"generated": old.get("generated"), "items": []})
        ARCHIVE.write_text(json.dumps(arch, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"refilter: {sum(len(i['filings']) for i in old['items'])} -> {sum(len(i['filings']) for i in arch['items'])} filings, "
              f"{sum(len(i['news']) for i in old['items'])} -> {sum(len(i['news']) for i in arch['items'])} headlines")
        return
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
