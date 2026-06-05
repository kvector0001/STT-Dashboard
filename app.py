"""
Simple Flask server for Portfolio Dashboard
- Serves static files
- Provides /api/refresh endpoint to run fetch_prices.py
"""

from flask import Flask, jsonify
import subprocess
import os
import json
from datetime import datetime

app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/')
def serve_index():
    """Serve the main dashboard"""
    return app.send_static_file('index.html')

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """
    Endpoint to refresh portfolio data from Google Sheet
    Runs: python scripts/fetch_prices.py
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshing portfolio data...")
        
        # Run the fetch_prices.py script
        result = subprocess.run(
            ['python', 'scripts/fetch_prices.py'],
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )
        
        # Check if script succeeded
        if result.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Refresh successful")
            
            # Read updated data to return to frontend
            try:
                with open('prices.json', 'r', encoding='utf-8') as f:
                    prices = json.load(f)
                return jsonify({
                    'success': True,
                    'message': f'✅ Portfolio refreshed ({len(prices)} stocks)',
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({
                    'success': True,
                    'message': '✅ Portfolio refreshed',
                    'timestamp': datetime.now().isoformat()
                })
        else:
            # Script failed
            error_msg = result.stderr or result.stdout or "Unknown error"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Refresh failed: {error_msg[:100]}")
            return jsonify({
                'success': False,
                'message': f'❌ Refresh failed: {error_msg[:100]}',
                'timestamp': datetime.now().isoformat()
            }), 500
            
    except subprocess.TimeoutExpired:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Refresh timeout")
        return jsonify({
            'success': False,
            'message': '❌ Refresh timeout (took too long)',
            'timestamp': datetime.now().isoformat()
        }), 500
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'❌ Error: {str(e)[:100]}',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/<path:path>')
def serve_static(path):
    """Serve all other static files"""
    return app.send_static_file(path)

if __name__ == '__main__':
    print("🚀 Starting Portfolio Dashboard server...")
    print("📍 Open: http://localhost:8000")
    print("🔄 Refresh endpoint: POST /api/refresh")
    app.run(host='0.0.0.0', port=8000, debug=False)
