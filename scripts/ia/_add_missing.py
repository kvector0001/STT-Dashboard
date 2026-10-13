"""One-off: add calls for given tickers that a full rebuild finds but the sheet ledger lacks, without re-dating others.
Usage: python _add_missing.py TICKER [TICKER ...] [--write]"""
import collections, os, runpy, sys, tempfile

import gspread

import ia_sync as s

tickers = {a for a in sys.argv[1:] if not a.startswith("--")}
write = "--write" in sys.argv
creds, cfg = s._credentials(), s._config()
sh = gspread.authorize(creds).open_by_key(s.SHEET_ID)
ac_ws, sc_ws = s._ws(sh, s.AC_TAB, len(s.AC_HDR)), s._ws(sh, s.SC_TAB, len(s.SC_HDR))
store = ac_ws.get_all_values()[1:]
blog = {r[0]: r[13] for r in sc_ws.get_all_values()[1:] if len(r) > 13 and r[13]}


def build(st, full, chats):
    return runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ia_build.py"), init_globals={
        "IA_ROOT": s.ROOT, "IA_CHAT_FILES": chats, "IA_ADVISOR": cfg["advisor"], "IA_STRIP_NAMES": cfg.get("strip_names", []),
        "IA_STORE": st, "IA_BLOG_LINKS": blog, "IA_FULL_REBUILD": full})


key = lambda r: (str(r[0]), str(r[2])[:10], str(r[3]))
with tempfile.TemporaryDirectory() as tmp:
    chats = s.download_chats(creds, cfg, tmp)
    have = collections.Counter(map(key, store))
    add = [r for r in build(store, True, chats)["allcalls"] if r[0] in tickers and not have[key(r)]]
    print("Adding:", [(r[0], r[2], r[3], r[4]) for r in add])
    if not add:
        sys.exit("Nothing to add.")
    g = build(store + add, False, chats)
calls, quotes = g["calls"], g["allcalls"]
print(f"Result: {len(calls)} stocks, {len(quotes)} calls (sheet had {len(store)})")
if len(quotes) < len(store) + len(add):
    sys.exit("Fewer calls than expected — not writing.")
if write:
    s.write_tab(ac_ws, s.AC_HDR, quotes)
    s.write_tab(sc_ws, s.SC_HDR, calls)
    print("Sheet updated.")
else:
    print("Dry run — add --write to update the sheet.")
