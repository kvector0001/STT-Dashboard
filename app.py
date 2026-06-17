"""
Simple Flask server for Portfolio Dashboard
- Serves static files
- Provides /api/refresh endpoint to run fetch_prices.py
"""

from flask import Flask, jsonify, send_from_directory, request, Response, stream_with_context
import subprocess
import os
import json
from datetime import datetime

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """
    Endpoint to refresh portfolio data from Google Sheet
    Runs: python scripts/fetch_prices.py
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] POST /api/refresh - Refreshing portfolio data...")
        
        # Use system Python
        python_path = 'python'
        
        # Run the fetch_prices.py script
        result = subprocess.run(
            [python_path, 'scripts/fetch_prices.py'],
            capture_output=True,
            text=True,
            timeout=180,  # 3 minute timeout
            cwd=BASE_DIR
        )
        
        # Check if script succeeded
        if result.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SUCCESS: Refresh successful")
            
            # Read updated data to return to frontend
            try:
                with open(os.path.join(BASE_DIR, 'prices.json'), 'r', encoding='utf-8') as f:
                    prices = json.load(f)
                return jsonify({
                    'success': True,
                    'message': f'✅ Portfolio refreshed ({len(prices)} stocks)',
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Could not read prices.json: {str(e)}")
                return jsonify({
                    'success': True,
                    'message': '✅ Portfolio refreshed',
                    'timestamp': datetime.now().isoformat()
                })
        else:
            # Script failed
            error_msg = result.stderr or result.stdout or "Unknown error"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Refresh failed (returncode={result.returncode})")
            print(f"stderr: {result.stderr[:200]}")
            print(f"stdout: {result.stdout[:200]}")
            return jsonify({
                'success': False,
                'message': f'❌ Refresh failed: Script returned {result.returncode}',
                'timestamp': datetime.now().isoformat()
            }), 500
            
    except subprocess.TimeoutExpired:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Refresh timeout (script took too long)")
        return jsonify({
            'success': False,
            'message': '❌ Refresh timeout (took too long)',
            'timestamp': datetime.now().isoformat()
        }), 500
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'❌ Error: {str(e)[:100]}',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/refresh-stream')
def refresh_stream():
    """
    Server-Sent Events endpoint — streams fetch_prices.py stdout line-by-line
    so the browser can show live progress during refresh.
    """
    def generate():
        try:
            proc = subprocess.Popen(
                ['python', '-u', 'scripts/fetch_prices.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BASE_DIR
            )
            for line in proc.stdout:
                line = line.rstrip('\n')
                if line:
                    yield f"data: {json.dumps({'line': line})}\n\n"
            proc.wait()
            if proc.returncode == 0:
                yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': f'Exit code {proc.returncode}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/save-analysis', methods=['POST'])
def save_analysis():
    """
    Receives updated stocks.json data from the browser after Claude analysis is pasted.
    Writes stocks.json then runs git add + commit + push.
    Only works when server is running locally.
    """
    try:
        data = request.get_json(force=True)
        if not data or not isinstance(data, list):
            return jsonify({'success': False, 'message': '❌ Expected a JSON array'}), 400

        stocks_path = os.path.join(BASE_DIR, 'stocks.json')

        # Write updated stocks.json
        with open(stocks_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        updated_tickers = [s.get('ticker', '?') for s in data if s.get('moat_class') not in (None, '', 'pending')]

        # Git commit and push
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        commit_msg = f'feat: update fundamental analysis {ts}'

        git_cmds = [
            ['git', 'add', 'stocks.json'],
            ['git', 'commit', '-m', commit_msg],
            # Pull any bot commits (e.g. prices refresh) first so push won't be rejected.
            # 'ours' keeps our stocks.json on conflict; prices.json etc. merge cleanly.
            ['git', 'pull', '--no-edit', '-X', 'ours', 'origin', 'main'],
            ['git', 'push', 'origin', 'main'],
        ]
        for cmd in git_cmds:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR, timeout=60)
            combined = (result.stdout or '') + (result.stderr or '')
            # 'nothing to commit' (commit step) and 'Already up to date' (pull step) are fine
            if result.returncode != 0 and 'nothing to commit' not in combined and 'up to date' not in combined.lower():
                return jsonify({
                    'success': False,
                    'message': f'❌ git error ({" ".join(cmd[1:2])}): {(result.stderr or result.stdout)[:200]}'
                }), 500

        return jsonify({
            'success': True,
            'message': f'✅ Saved & pushed stocks.json ({len(data)} stocks)',
            'timestamp': ts
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'❌ Error: {str(e)[:200]}'}), 500


@app.route('/')
def serve_index():
    """Serve the main dashboard"""
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve all other static files"""
    return send_from_directory(BASE_DIR, filename)

if __name__ == '__main__':
    print("Starting Portfolio Dashboard server...")
    print("Open: http://localhost:8000")
    print("Refresh endpoint: POST /api/refresh")
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
