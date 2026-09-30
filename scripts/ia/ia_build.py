"""IA Call Tracker builder — VERBATIM extraction from the advisor's WhatsApp chat exports.
Run by scripts/ia/ia_sync.py (GitHub Actions). All inputs are injected as globals (see IA_* below);
nothing is read from or written to the repo except stocks.json / prices.json. Chat text never
touches the repo or the logs — it only goes to the Google Sheet.
"""
import pandas as pd, numpy as np, json, os, re, sys, yfinance as yf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from yahoo_symbols import yahoo_symbol_candidates

_G = globals()
ROOT = _G.get("IA_ROOT", os.getcwd())
CHAT_FILES = _G.get("IA_CHAT_FILES", [])      # [(path, is_one_to_one_chat)]
ADVISOR = _G.get("IA_ADVISOR", "")            # sender kept from the 1:1 chat (from a secret)
STRIP_NAMES = _G.get("IA_STRIP_NAMES", [])     # personal names removed from quotes (from a secret)
STORE_ROWS = _G.get("IA_STORE", [])           # existing "IA All Calls" rows = the ledger
BLOG_LINKS = _G.get("IA_BLOG_LINKS", {})      # ticker -> blog URL (from the existing "IA Stock Calls" tab)
FULL_REBUILD = _G.get("IA_FULL_REBUILD", False)
sj = json.load(open(os.path.join(ROOT, "stocks.json"), encoding="utf-8"))
try: PRICES = json.load(open(os.path.join(ROOT, "prices.json"), encoding="utf-8"))
except Exception: PRICES = {}
def cmp_of(tk):
    p = PRICES.get(tk)
    return (p.get("ltp") if isinstance(p, dict) else None)
def vs_cmp(px, tk):
    c = cmp_of(tk)
    if px in ("", None) or not c: return ""
    try: return round((float(c) / float(px) - 1) * 100, 1)
    except: return ""

# ── ticker phrase matcher ──
def norm(s): return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()
def base_name(n):
    n = norm(n)
    for w in [" limited", " ltd", " (india)", " india", " corporation", " company", " industries", " enterprises"]:
        n = n.replace(w, " ")
    return re.sub(r"\s+", " ", n).strip()
tickset = {x["ticker"] for x in sj if x.get("ticker")}
nse2t = {x.get("nse_symbol"): x["ticker"] for x in sj if x.get("nse_symbol") and x.get("ticker")}
def norm_t(t):
    t = str(t).strip()
    return t if t in tickset else nse2t.get(t, t)
compmap = {x["ticker"]: x.get("name") for x in sj if x.get("ticker")}
ticker_nse = {x["ticker"]: (x.get("nse_symbol") or x["ticker"]) for x in sj if x.get("ticker")}
phrases = []
_bns = {base_name(x.get("name", "")) for x in sj if x.get("ticker")}
GENERIC_TAIL = {"analytics", "technologies", "technology", "tech", "solutions", "systems", "engineering", "engineers",
    "infra", "infrastructure", "industries", "enterprises", "services", "products", "pharmaceuticals", "pharma",
    "healthcare", "hospitals", "hospital", "international", "holdings", "finance", "financial", "capital", "ventures",
    "labs", "laboratories", "chemicals", "global", "corp", "group"}
for x in sj:
    tk = x.get("ticker")
    if not tk or tk == "Cash": continue
    bn = base_name(x.get("name", ""))
    if len(bn) >= 4: phrases.append((bn, tk))
    if len(bn) >= 8 and bn.endswith("s") and not bn.endswith("ss"): phrases.append((bn[:-1], tk))  # "castings" -> "casting"
    w = bn.split()
    if len(w) >= 3 and w[-1] in GENERIC_TAIL:  # "latent view analytics" -> "latent view", if no other company starts with it
        v = " ".join(w[:-1])
        if not any(o != bn and o.startswith(v) for o in _bns): phrases.append((v, tk))
    ns = norm(x.get("nse_symbol") or "")
    if len(ns) >= 4 and ns != bn: phrases.append((ns, tk))
# distinctive first word as a short name ("scoda" for Scoda Tubes) when no other company shares it
COMMON_FIRST = {"indian", "global", "national", "bharat", "hindustan", "united", "universal", "precision", "prime",
    "royal", "super", "golden", "happy", "shree", "great", "power", "steel", "metal", "green", "future", "modern",
    "standard", "general", "central", "eastern", "western", "southern", "northern", "orient", "oriental", "asian",
    "premier", "supreme", "capital", "quality", "welcome", "advanced", "natural", "better", "credit", "castings",
    # generic words / names shared by several listed companies or fund houses
    "investment", "healthcare", "hindustan", "century", "nippon", "invesco", "edelweiss", "motilal", "mahindra",
    "marine", "landmark", "synergy", "keystone", "lakshmi", "cholamandalam", "glenmark", "welspun", "hitachi",
    "black", "clean", "force", "happy", "multi", "power", "south", "birla", "icici", "indus", "anant", "astra", "laxmi"}
_first = {}
for bn in _bns:
    if bn: _first[bn.split()[0]] = _first.get(bn.split()[0], 0) + 1
_have = {p for p, _ in phrases}
for x in sj:
    tk = x.get("ticker")
    if not tk or tk == "Cash": continue
    bn = base_name(x.get("name", ""))
    fw = bn.split()[0] if bn else ""
    if len(bn.split()) >= 2 and len(fw) >= 5 and _first.get(fw) == 1 and fw not in COMMON_FIRST and fw not in _have:
        phrases.append((fw, tk))
phrases.sort(key=lambda p: -len(p[0]))

def mentions(text, minlen=4):
    """Non-overlapping stock mentions in norm(text), longest name first ("cyient dlm" beats "cyient").
    A name directly preceded by "not" (e.g. "(Not Cyient DLM)") is an explicit exclusion."""
    ns = norm(text); taken = []; out = []
    for ph, tk in phrases:
        if len(ph) < minlen: continue
        for m in re.finditer(r"\b" + re.escape(ph) + r"\b", ns):
            a, b = m.span()
            if any(a < y and x < b for x, y in taken): continue
            taken.append((a, b))
            if not re.search(r"\bnot\s*$", ns[max(0, a - 5):a]):
                out.append((a, b, tk))
    return sorted(out), ns

def title_tickers(text):
    ms, ns = mentions(text)
    first_len = min(90, len(norm(text.split("\n")[0])))
    p = re.match(r"(dear all|dear members|dear)?[, ]*", ns[:130]).end()
    hits = []
    for a, b, tk in ms:
        if (a < first_len or p <= a < p + 70) and tk not in hits: hits.append(tk)
    return hits[:2]

# ── message parsing (both files, per-file sender rule) ──
MSGPAT = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+\d{1,2}:\d{2}\s*[ap]m\s+-\s+([^:]+):\s?(.*)$")
def parse(fp, keep_senders):
    lines = open(fp, encoding="utf-8", errors="ignore").read().splitlines()
    out = []; i = 0
    while i < len(lines):
        m = MSGPAT.match(lines[i])
        if m:
            body = [m.group(5)]; j = i + 1
            while j < len(lines) and not MSGPAT.match(lines[j]): body.append(lines[j]); j += 1
            dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if yy < 100: yy += 2000
            iso = f"{yy:04d}-{mm:02d}-{dd:02d}"
            sender = m.group(4).strip()
            if keep_senders is None or sender in keep_senders:
                out.append((iso, sender, "\n".join(body).strip()))
            i = j
        else: i += 1
    return out

msgs = []
for f, one_to_one in CHAT_FILES:
    keep = {ADVISOR} if one_to_one else None  # broadcasts: keep all
    src = "WA-chat" if one_to_one else "WA-broadcast"
    for iso, snd, txt in parse(f, keep):
        msgs.append((iso, src, txt))
# dedupe identical text
seen = set(); uniq = []
for iso, src, t in msgs:
    k = re.sub(r"\s+", " ", t)[:140]
    if k in seen or len(t) < 20: continue
    seen.add(k); uniq.append((iso, src, t))

# ── per-message: action, stated price, mustbuy, clean text ──
MUSTBUY_KW = ["all account", "in all account", "buy in all", "must buy", "must have", "must own", "multibagger",
    "multi bagger", "will double", "double soon", "can double", "doubler", "load up", "back the truck", "sure shot",
    "buy big", "buy heavily", "dont miss", "don't miss", "do not miss", "very good chance", "huge chance",
    "everybody should buy", "everyone should buy", "invest big", "buy aggressively", "big time"]
BULLISH_KW = ["buy more", "add more", "increase", "accumulate", "very cheap", "undervalued", "ready for jump",
    "ready to jump", "re-rate", "rerate", "rerating", "strong buy", "stunning", "a gem", "conviction", "lacs",
    "lakh", "golden opportunity", "huge potential", "buy 30% more", "150%", "picking these"]
def classify(t):
    q = " " + t.lower() + " "
    # MUSTBUY: only when explicitly "must buy" OR a call to buy in ALL accounts
    if "must buy" in q or "must have" in q or "in all account" in q or re.search(r"(buy|add|in|for)\s+all\s+(the\s+)?accounts?", q):
        return "MUSTBUY"
    # BULLISH: only strongly optimistic language (NOT a plain buy/add)
    STRONG = ["multibagger", "multi bagger", "will double", "double soon", "can double", "doubler",
        "10 bagger", "20 bagger", " bagger", "stunning", " a gem", "golden opportunity", "huge potential",
        "load up", "back the truck", "sure shot", "very good chance", "huge chance", "high conviction",
        "invest big", "buy big", "buy heavily", "buy aggressively"]
    if any(k in q for k in STRONG):
        return "BULLISH"
    return ""
# ── BUY / SELL / WATCH, decided PER STOCK from the nearest instruction in the same clause ──
# All matching runs on norm() text (lower-case, punctuation -> space) so cue and name positions line up.
BUY_RE = re.compile(r"\b(buy|buying|add|adding|accumulat\w*|top ?up|initiat\w*|invest(?:ing)? big|more qty"
                    r"|increase (?:the )?(?:qty|quantity|allocation|position|holding)|pick (?:it|this|these|some|them))\b")
SELL_RE = re.compile(r"\b(sell|selling|exit|exiting|book(?:ing)? (?:partial )?profits?|square off|reduce|reducing"
                     r"|trim|trimming|get out)\b")
STRONG_DIRECT = re.compile(r"\b(pl[sz]|please|pls|kindly)\s*$")
SOFT_DIRECT = re.compile(r"\b(so|now|hence|must|should|need to|can|will|lets|let us|start|urgently|pl[sz]|please|pls|kindly)\s*$")
# "no funds / not having / dont have" describe who should act, not a negated instruction
NEG = re.compile(r"\b(not|no|don t|do not|dont|never|no need to|avoid|stop|nothing to|not to|instead of)\s+(?!funds?\b|having\b|have\b|holding\b)(?:\w+\s+){0,3}$")
PAST = re.compile(r"\b(did|had|was|were|got|made|have been|already|earlier|previously|in the past|wanted|wished)\b.{0,25}$")
TENTATIVE = re.compile(r"\b(may|might|could|would|plan|planning|thinking|review|once)\b(?:\s+\w+){0,3}\s*$")
THIRD = re.compile(r"\b(promoters?|fiis?|diis?|mutual funds?|mfs|insiders?|investors?|market|members|people|someone"
                   r"|others|traders|operators|hnis?|they|company|management|board|asked me to|asking me to"
                   r"|offered to|offer to|deal to|agreed to|agreement to|entered into|plans to)\s+(?:\w+\s+){0,3}$")
PROGRESSIVE = re.compile(r"\b(start|started|continue|keep|are|be)\s*$")
COND_AFTER = re.compile(r"^(?:\s+\S+){0,5}?\s+(?:at|on)\s+(?:lower|every|any|dips?|falls?|corrections?|declines?)\b")
PAST_AFTER = re.compile(r"^.{0,30}\b(in the past|last (?:year|month|week)|ago)\b")
NOUN_CALL = re.compile(r"^\s+calls?\b")
NONTRADE_AFTER = re.compile(r"^\s+(?:its |the |their |our )?(?:debt|costs?|interest|loss(?:es)?|pledge|borrowings?|working capital|impact|value of|stake|shares in)\b"
                            r"|^\s+(?:some |more |a few )?(?:of )?(?:others|the rest)\b")
COND_BEFORE = re.compile(r"\b(if|when|once)\b.{0,40}\b(falls?|dips?|corrects?|comes? down|drops?|declines?|correction)\b.{0,45}$")
# a stock named after these words is a reference point ("qty equal to Scoda"), not the stock being traded
REFERENCE_BEFORE = re.compile(r"\b(invested in|equal to|same as|similar to|instead of|compared to|than|like)\s+$")

def cues(c):
    """Valid trade instructions in a normalised clause -> sorted [(pos, 'BUY'|'SELL')]."""
    out = []
    for kind, rx in (("BUY", BUY_RE), ("SELL", SELL_RE)):
        for m in rx.finditer(c):
            a, b = m.span(); pre, post = c[max(0, a - 45):a], c[b:b + 60]
            strong = bool(STRONG_DIRECT.search(pre))
            if re.search(r"(ing|ion)\b", m.group(1).split()[0]) and not (strong or PROGRESSIVE.search(pre)): continue
            if COND_AFTER.match(post) or NONTRADE_AFTER.match(post) or COND_BEFORE.search(c[max(0, a - 90):a]): continue
            if NOUN_CALL.match(post) and re.search(r"\b(earlier|previous|last|my|his)\s*$", pre): continue
            if not strong and (NEG.search(pre) or THIRD.search(pre) or TENTATIVE.search(pre)): continue
            if not SOFT_DIRECT.search(pre) and (PAST.search(pre) or PAST_AFTER.match(post)): continue
            out.append((a, kind))
    return sorted(out)

def clauses(t):
    return [c for c in re.split(r"(?<=[.!?\n])\s+|\.{2,}|\n", t) if c.strip()]

def action_for(tk, t, primary=False):
    """BUY / SELL / WATCH for one stock in a message (or sentence)."""
    found, orphan, first_clause, other_clauses = [], [], None, []
    for ci, cl in enumerate(clauses(t)):
        ms, c = mentions(cl)
        cs = cues(c)
        if not ms:
            # the pronoun must be what is being bought/sold ("buy this one", "sell it"), not just anywhere in the clause
            orphan += [(ci, k, bool(re.match(r"\s*(?:\w+\s+){0,2}(this one|this stock|this|it|them|these)\b", c[p + len(k):])))
                       for p, k in cs]
            continue
        if any(o != tk for _, _, o in ms): other_clauses.append(ci)
        acts = []
        for i, (a, b, mtk) in enumerate(ms):
            # names joined by "/", ",", "and", "or" ("Suzlon/Inox Wind") share one instruction
            if i and ms[i - 1][2] != mtk and re.fullmatch(r"\s*(?:and|or|each)?\s*(?:\d+\s*(?:of\s+)?)?(?:and|or)?\s*", c[ms[i - 1][1]:a]):
                acts.append(acts[-1])
            elif REFERENCE_BEFORE.search(c[max(0, a - 20):a]):
                acts.append(None)
            else:
                prev_other = max([y for x, y, o in ms[:i] if o != mtk], default=-1)
                before = [k for p, k in cs if prev_other < p < a]
                next_other = min([x for x, y, o in ms[i + 1:] if o != mtk], default=len(c) + 1)
                after = [k for p, k in cs if b <= p < next_other]
                acts.append(before[-1] if before else (after[0] if after else None))
            if mtk == tk:
                if first_clause is None: first_clause = ci
                if acts[-1]: found.append(acts[-1])
    if found:
        return found[0]
    # a list item ("buy more of: <newline> Borosil") takes the nearest instruction ABOVE it;
    # the message's subject otherwise takes the first instruction that follows
    above = [k for ci, k, _ in orphan if first_clause is not None and ci < first_clause]
    if above:
        return above[-1]
    if primary and orphan:
        # instructions refer back to the subject until another stock is named, unless they say "this one"/"it"
        start = first_clause if first_clause is not None else -1
        stop = min([ci for ci in other_clauses if ci > start], default=10**9)
        near = [k for ci, k, ref in orphan if ci > start and (ci < stop or ref)]
        if near:
            return near[0]
    return "WATCH"
def stated_price(t):
    m = re.search(r"cmp[\s:]*[a-z₹.]*\s*([0-9][0-9,]{1,7})(?:\.\d+)?", t, re.I)
    if m:
        try: return round(float(m.group(1).replace(",", "")), 2)
        except: pass
    return None
def clean_text(t):
    t = t.replace("*", "")
    t = re.sub(r"\bDear All[,:]?\s*", "", t, flags=re.I)
    t = re.sub(r"\bDear members[,:]?\s*", "", t, flags=re.I)
    for nm in STRIP_NAMES:
        t = re.sub(r"\b" + re.escape(nm) + r"\b", "", t, flags=re.I)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(" ,\n")

# ── yfinance backfill (in-memory; each ticker's history is fetched at most once per run) ──
PC = {}
_hist = {}
def _get_hist(tk, start):
    if tk in _hist: return _hist[tk]
    h = None
    for sym in yahoo_symbol_candidates(tk, ticker_nse.get(tk)):
        try:
            d = yf.download(sym, start=start, progress=False, auto_adjust=False)
            if d is not None and len(d):
                c = d["Close"]; c = c.iloc[:, 0] if hasattr(c, "columns") else c
                h = c.dropna()
                if len(h): break
        except Exception: pass
    _hist[tk] = h
    return h
def price_on(tk, iso):
    key = tk + "|" + iso
    if key in PC: return PC[key]
    h = _get_hist(tk, "2013-01-01"); val = None
    if h is not None and len(h):
        try:
            d = pd.to_datetime(iso); sub = h[h.index <= d]
            if len(sub): val = round(float(sub.iloc[-1]), 2)
        except Exception: pass
    PC[key] = val; return val

# ── build All Calls (verbatim) ──
# stocks_in: all stock mentions in a chunk (min length 5 to avoid false positives)
def stocks_in(s, minlen=5):
    found = []
    for a, b, tk in mentions(s, minlen)[0]:
        if tk not in found: found.append(tk)
    return found
COMMENT_RE = re.compile(r"\b(up \d|down \d|hold|holding|keep|doing well|doing great|good result|results are|buy|add|sell|book|profit|double|multibag|target|reduce|trim|exit|jump|rerat|re-rat|accumulat|pick|added|bought)\b", re.I)
LIST_RE = re.compile(r"\b(stocks like|names like|such as|preference list|list is|following stocks)\b", re.I)
# incremental ledger (= the sheet's "IA All Calls" tab): dates before CUTOFF are frozen, so corrections made
# in the sheet stick; only newer messages are parsed. FULL_REBUILD re-parses everything but keeps BLOG rows.
def _row(r):
    r = list(r) + [""] * (9 - len(r))
    return [str(x) if x is not None else "" for x in r[:9]]
_store = [_row(r) for r in STORE_ROWS if r and str(r[0]).strip()]
if FULL_REBUILD:
    _store = [r for r in _store if r[3] == "BLOG"]
# retry prices for stored calls that have none (e.g. an earlier Yahoo symbol miss)
for r in _store:
    if r[4] == "" and r[3] != "BLOG":
        _px = price_on(r[0], r[2])
        if _px is not None:
            r[4], r[8] = _px, vs_cmp(_px, r[0])
allcalls = list(_store)
_sdates = [r[2] for r in _store if r[3] != "BLOG" and re.match(r"\d{4}-\d{2}-\d{2}$", r[2])]
CUTOFF = max(_sdates) if _sdates else None
_seen = {(r[0], r[2], r[5]) for r in _store if len(r) > 5}
_bf = [0]
def add_call(tk, iso, src, action, quote, mb):
    if len(quote) < 15: return
    if (tk, iso, quote) in _seen: return  # already in the ledger (CUTOFF day is re-scanned)
    px = price_on(tk, iso)  # always use market close on the call date
    if px is None: px = stated_price(quote)  # fallback only when yfinance has no data
    _bf[0] += 1
    if _bf[0] % 60 == 0: print("  priced", _bf[0], flush=True)
    allcalls.append([tk, compmap.get(tk, tk), iso, action, (px if px is not None else ""), quote, src, mb, vs_cmp(px, tk)])
for iso, src, t in uniq:
    if len(t) < 20: continue
    if CUTOFF and iso < CUTOFF: continue  # incremental: older dates are frozen; CUTOFF day re-scanned for late messages
    used = set()
    # 1) primary/title stock -> the FULL message; action decided per stock ("sell X and buy Y")
    for tk in title_tickers(t):
        add_call(tk, iso, src, action_for(tk, t, primary=True), clean_text(t), classify(t)); used.add(tk)
    # 2) genuine one-liner comments about other stocks (keep HOLD updates); skip name-lists
    for sent in clauses(t):
        s = sent.strip()
        if len(s) < 15: continue
        tks = stocks_in(s)
        if not tks or len(tks) >= 3 or LIST_RE.search(s) or not COMMENT_RE.search(s): continue
        for tk in tks:
            if tk in used: continue
            add_call(tk, iso, src, action_for(tk, s), clean_text(s), classify(s)); used.add(tk)

# ── aggregate Stock Calls ──
RANK = {"MUSTBUY": 2, "BULLISH": 1, "": 0}
def bloglink(tk): return BLOG_LINKS.get(tk, "")

per = {}
for row in allcalls:
    per.setdefault(row[0], []).append(row)
calls = []
for tk, rows in per.items():
    rows_sorted = sorted(rows, key=lambda r: r[2])
    # BLOG rows are the advisor's published picks, so they count as buy calls
    buys = [r for r in rows_sorted if r[3] in ("BUY", "BLOG") and r[4] not in ("", None)]
    decisive = [r for r in rows_sorted if r[3] in ("BUY", "SELL", "BLOG")]
    status = ("BUY" if decisive[-1][3] == "BLOG" else decisive[-1][3]) if decisive else "WATCH"
    lastp = round(float(buys[-1][4]), 2) if buys else ""
    maxr = max(buys, key=lambda r: float(r[4])) if buys else None
    maxp = round(float(maxr[4]), 2) if maxr else ""
    max_reco_date = maxr[2] if maxr else ""
    last_buy_date = buys[-1][2] if buys else ""
    mb = {2: "MUSTBUY", 1: "BULLISH", 0: ""}[max((RANK.get(r[7], 0) for r in rows), default=0)]
    urgent = "Y" if any(re.search(r"urgent", r[5], re.I) for r in rows) else "N"
    dates = [r[2] for r in rows_sorted]
    ncalls = len([r for r in rows if r[3] != "BLOG"]) or len(rows)
    held = "Y" if (PRICES.get(tk) or {}).get("quantity") else "N"
    calls.append([tk, compmap.get(tk, tk), status, lastp, maxp,
        "", "", "", "", "", "", held, urgent, bloglink(tk), ncalls,
        dates[0], dates[-1], max_reco_date, mb, last_buy_date])

# sort newest first
def dkey(s):
    try: return pd.to_datetime(s)
    except: return pd.Timestamp("1900-01-01")
calls.sort(key=lambda c: dkey(c[16] or c[15] or ""), reverse=True)
allcalls.sort(key=lambda q: dkey(q[2]), reverse=True)

new_n = len(allcalls) - len(_store)
print("Stock Calls:", len(calls), "| All Calls:", len(allcalls), "| new this run:", new_n, "| cutoff:", CUTOFF)
