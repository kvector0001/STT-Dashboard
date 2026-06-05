#!/usr/bin/env python3
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/test', methods=['GET', 'POST'])
def test():
    return jsonify({'success': True, 'message': 'Test endpoint works'})

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    print("REFRESH ENDPOINT CALLED!")
    return jsonify({'success': True, 'message': 'Refresh works'})

@app.route('/')
def home():
    return 'Home page'

if __name__ == '__main__':
    print("Starting test Flask server on port 8000...")
    app.run(host='0.0.0.0', port=8000, debug=False)
