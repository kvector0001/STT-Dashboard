#!/usr/bin/env python3
"""
Claude Analysis Proxy  -  scripts/claude_proxy.py
=================================================
Runs a tiny HTTP server on port 8001. The dashboard calls it directly
and it forwards requests to the Anthropic API (no CORS issues).

Setup:
  1. Get a free API key at https://console.anthropic.com
  2. Set the environment variable OR create a .env file in the Dashboard folder:
       ANTHROPIC_API_KEY=sk-ant-...
  3. Run in a separate terminal:
       python scripts/claude_proxy.py

The dashboard detects this proxy automatically at http://localhost:8001
and enables one-click "Ask Claude" on every pending stock card.
"""

import os, json, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8001
CLAUDE_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-3-5-haiku-20241022"   # fast + cheap for this use-case

# ── Load API key ─────────────────────────────────────────────────────────────
def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    # Try .env file in the Dashboard folder (parent of scripts/)
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

# ── Build the analysis prompt ─────────────────────────────────────────────────
def build_prompt(stock):
    ticker   = stock.get("ticker", "?")
    name     = stock.get("name", "")
    sector   = stock.get("sector", "Unknown")
    ltp      = stock.get("ltp")
    buy_avg  = stock.get("buy_avg")
    pnl_pct  = stock.get("pnl_pct")

    lines = [f"Stock: {ticker}" + (f" ({name})" if name else ""),
             f"Sector: {sector}"]
    if ltp:      lines.append(f"LTP: \u20b9{ltp:.2f}")
    if buy_avg:  lines.append(f"Buy Avg: \u20b9{buy_avg:.2f}")
    if pnl_pct is not None:
        lines.append(f"P&L: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%")

    stock_info = "\n".join(lines)

    return f"""You are a fundamental analyst for Indian equities.
Analyse the stock below and return ONLY a valid JSON object — no explanation, no markdown, no code fences, nothing before or after the JSON.

{stock_info}

Return exactly this JSON schema (fill every field; be factual and concise):
{{
  "ticker": "{ticker}",
  "name": "Full official company name",
  "sector": "Sector name",
  "moat_type": "Wide | Narrow | None",
  "moat_class": "wide | narrow | none",
  "conviction": <integer 1-10>,
  "moat": "1-2 sentence description of the economic moat",
  "leadership": "Market position, market share, brand strength",
  "non_rep": "What competitors cannot easily replicate",
  "tailwinds": ["tailwind 1", "tailwind 2", "tailwind 3"],
  "risks": ["risk 1", "risk 2", "risk 3"],
  "track": ["KPI to track 1", "KPI to track 2"]
}}"""

# ── Call Anthropic API ────────────────────────────────────────────────────────
def call_claude(prompt, api_key):
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        CLAUDE_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            # Strip any accidental markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Anthropic API {e.code}: {body}")

# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suppress default access log noise; print only meaningful lines
        pass

    def _cors(self):
        # Allow requests from any localhost origin (port 8000 or others)
        origin = self.headers.get("Origin", "")
        if "localhost" in origin or "127.0.0.1" in origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://localhost:8000")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            api_key = load_api_key()
            status = {"ok": True, "model": MODEL, "key_set": bool(api_key)}
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/set-key":
            # Allow dashboard to send the API key directly
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            new_key = body.get("key", "").strip()
            if new_key:
                # Write to .env in Dashboard root
                env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
                lines = []
                written = False
                if os.path.exists(env_path):
                    with open(env_path) as f:
                        lines = f.readlines()
                new_lines = []
                for line in lines:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        new_lines.append(f"ANTHROPIC_API_KEY={new_key}\n")
                        written = True
                    else:
                        new_lines.append(line)
                if not written:
                    new_lines.append(f"ANTHROPIC_API_KEY={new_key}\n")
                with open(env_path, "w") as f:
                    f.writelines(new_lines)
                os.environ["ANTHROPIC_API_KEY"] = new_key
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            else:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No key provided"}).encode())
            return

        if self.path != "/analyze":
            self.send_response(404)
            self.end_headers()
            return

        api_key = load_api_key()
        if not api_key:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "NO_KEY", "message": "ANTHROPIC_API_KEY not set. Enter it in the dashboard settings."}).encode())
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            stock  = json.loads(self.rfile.read(length))
            prompt = build_prompt(stock)
            print(f"  -> Analysing {stock.get('ticker', '?')} with {MODEL}...")
            result = call_claude(prompt, api_key)
            print(f"  <- Done: {result.get('ticker','?')} moat={result.get('moat_class','?')} conviction={result.get('conviction','?')}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except json.JSONDecodeError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "PARSE_ERROR", "message": f"Claude returned non-JSON: {e}"}).encode())
        except RuntimeError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "API_ERROR", "message": str(e)}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "SERVER_ERROR", "message": str(e)}).encode())

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api_key = load_api_key()
    print("=" * 55)
    print("  Claude Analysis Proxy")
    print(f"  Listening on http://localhost:{PORT}")
    print(f"  Model: {MODEL}")
    if api_key:
        print(f"  API key: {api_key[:12]}...{api_key[-4:]}")
    else:
        print("  ⚠  ANTHROPIC_API_KEY not set")
        print("     Enter it in the dashboard or set env var:")
        print("     $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
    print("=" * 55)
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy stopped.")
