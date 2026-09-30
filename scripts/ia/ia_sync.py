"""IA call tracker sync — runs on GitHub Actions (daily) or locally.

1. Downloads the NEWEST WhatsApp export per chat from the shared Google Drive folder (zip -> txt, temp dir only).
2. Reads the Google Sheet's "IA All Calls" tab as the ledger and "IA Stock Calls" for blog links.
3. Runs ia_build.py (incremental: only messages newer than the ledger are parsed).
4. Writes both tabs back in place.

Nothing is written to the repo, and no chat text is printed (the repo and its Actions logs are public).
Secrets: GOOGLE_SA_KEY (service-account JSON) and IA_CONFIG, e.g.
  {"advisor": "<sender name in the 1:1 chat>", "one_to_one_keyword": "<text in that chat's file name>",
   "strip_names": ["<name>", ...]}
Flags: --full  re-classify every message (keeps BLOG rows); --dry-run  build but do not write the sheet.
"""
import io
import json
import os
import re
import runpy
import sys
import tempfile
import zipfile

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaIoBaseDownload

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHEET_ID = "1TSn6HIdcsux4p8cdpU0fx78zKibyxFKnwUUZTHFKfNI"
DRIVE_FOLDER = "1HSXvc6yiaYCdxYQ4WWzCnNhK1vOSAUOA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"]
SC_TAB, AC_TAB = "IA Stock Calls", "IA All Calls"
SC_HDR = ["Ticker", "Company", "Call status", "Last Buy price", "Max Buy price", "CMP", "CMP, % vs Last", "CMP % vs Max",
          "(Annualised) CAGR% vs Last", "CAGR% vs Max", "Signal", "Held?", "Urgent?", "Blog Link", "#Calls", "First Date",
          "Last Call date", "Max Buy date", "MustBuy", "Last Buy date"]
AC_HDR = ["Ticker", "Company", "Date", "Action", "IA price", "Quote (verbatim / blog summary)", "Source", "MustBuy", "vs CMP %"]


def _credentials():
    raw = os.environ.get("GOOGLE_SA_KEY", "").strip()
    if raw.startswith("{"):
        return Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    import glob
    for p in glob.glob(r"C:\Login\Zerodha\Python\*.json"):  # local fallback
        try:
            if json.load(open(p, encoding="utf-8")).get("type") == "service_account":
                return Credentials.from_service_account_file(p, scopes=SCOPES)
        except Exception:
            pass
    sys.exit("No service-account credentials (set GOOGLE_SA_KEY).")


def _config():
    raw = os.environ.get("IA_CONFIG", "").strip()
    if not raw:
        local = os.path.join(ROOT, "whatsapp_exports", "ia_config.json")  # gitignored local copy
        raw = open(local, encoding="utf-8").read() if os.path.exists(local) else ""
    if not raw:
        sys.exit("IA_CONFIG secret is missing.")
    cfg = json.loads(raw)
    for k in ("advisor", "one_to_one_keyword"):
        if not cfg.get(k):
            sys.exit(f"IA_CONFIG is missing '{k}'.")
    return cfg


def download_chats(creds, cfg, tmpdir):
    """Newest export per chat (Drive allows duplicate names such as '... (2)'). Returns [(txt_path, is_one_to_one)]."""
    svc = gbuild("drive", "v3", credentials=creds, cache_discovery=False)
    files = svc.files().list(q=f"'{DRIVE_FOLDER}' in parents and trashed=false",
                             fields="files(id,name,mimeType,createdTime)", supportsAllDrives=True,
                             includeItemsFromAllDrives=True).execute().get("files", [])
    kw = cfg["one_to_one_keyword"].lower()
    groups = {}
    for f in files:
        groups.setdefault(kw in f["name"].lower(), []).append(f)
    out = []
    for one_to_one, lst in groups.items():
        f = max(lst, key=lambda x: x.get("createdTime") or "")
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=f["id"]))
        done = False
        while not done:
            _, done = dl.next_chunk()
        data = buf.getvalue()
        if data[:2] == b"PK":  # WhatsApp exports arrive as a zip containing the chat .txt
            z = zipfile.ZipFile(io.BytesIO(data))
            txts = [n for n in z.namelist() if n.lower().endswith(".txt")]
            data = z.read(txts[0]) if txts else b""
        path = os.path.join(tmpdir, f"chat_{int(one_to_one)}.txt")
        open(path, "wb").write(data)
        out.append((path, one_to_one))
        print(f"  {'1:1 chat' if one_to_one else 'broadcast'}: newest of {len(lst)} export(s), uploaded {f.get('createdTime', '')[:16]}")
    return out


def _ws(sh, title, ncols):
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=10, cols=ncols)


def _cell(v):
    # values read back from the sheet are text; keep numbers numeric so the website's sheet reader sees one type per column
    if v is None:
        return ""
    if isinstance(v, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", v.strip()):
        return float(v) if "." in v else int(v)
    return v


def write_tab(ws, header, rows):
    """Overwrite a tab in place with a single values update (no delete/recreate, so a failure can't wipe it)."""
    values = [header] + [[_cell(v) for v in r] for r in rows]
    ws.resize(rows=max(len(values), 2), cols=len(header))
    ws.update(values=values, range_name="A1", value_input_option="RAW")


def main():
    full, dry = "--full" in sys.argv, "--dry-run" in sys.argv
    os.environ["PYTHONUTF8"] = "1"
    creds, cfg = _credentials(), _config()
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    ac_ws, sc_ws = _ws(sh, AC_TAB, len(AC_HDR)), _ws(sh, SC_TAB, len(SC_HDR))
    store = ac_ws.get_all_values()[1:]
    sc_old = sc_ws.get_all_values()[1:]
    blog_links = {r[0]: r[13] for r in sc_old if len(r) > 13 and r[13]}
    print(f"Ledger: {len(store)} calls in the sheet | mode: {'FULL rebuild' if full else 'incremental'}{' | DRY RUN' if dry else ''}")
    with tempfile.TemporaryDirectory() as tmp:
        chats = download_chats(creds, cfg, tmp)
        g = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ia_build.py"), init_globals={
            "IA_ROOT": ROOT, "IA_CHAT_FILES": chats, "IA_ADVISOR": cfg["advisor"],
            "IA_STRIP_NAMES": cfg.get("strip_names", []), "IA_STORE": store,
            "IA_BLOG_LINKS": blog_links, "IA_FULL_REBUILD": full})
    calls, quotes = g["calls"], g["allcalls"]
    if not quotes:
        sys.exit("Build produced no calls — refusing to overwrite the sheet.")
    if len(quotes) < len(store) and not full:
        sys.exit(f"Build has fewer calls ({len(quotes)}) than the sheet ({len(store)}) — refusing to overwrite.")
    if dry:
        print("Dry run — sheet not written.")
        return
    write_tab(ac_ws, AC_HDR, quotes)
    write_tab(sc_ws, SC_HDR, calls)
    print(f"Sheet updated: {len(calls)} stocks, {len(quotes)} calls ({len(quotes) - len(store):+d}).")


if __name__ == "__main__":
    main()
