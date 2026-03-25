#!/usr/bin/env python3
"""
Flask-server for drivstoffpriser.
"""
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import logging
import logging.handlers
import os
from datetime import timedelta

import resend
from flask import Flask, request, redirect

from db import init_db, _migrer_db
from osm import start_bakgrunnsoppdatering
from routes_auth import auth_bp
from routes_admin import admin_bp
from routes_api import api_bp

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('drivstoff')
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Fil-logging: buffret i RAM, skrives til disk kun ved ERROR eller når bufferet er fullt (100 meldinger).
# Maks 500 KB × 2 filer = 1 MB totalt på SD-kortet.
_log_path = os.path.join(os.environ.get('DATA_DIR', '.'), 'app.log')
_fil_handler = logging.handlers.RotatingFileHandler(
    _log_path, maxBytes=500_000, backupCount=2, encoding='utf-8'
)
_fil_handler.setLevel(logging.WARNING)
_fil_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
_buffer_handler = logging.handlers.MemoryHandler(
    capacity=100, flushLevel=logging.ERROR, target=_fil_handler
)
logger.addHandler(_buffer_handler)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-nøkkel-bytt-i-prod')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
resend.api_key = os.environ.get('RESEND_API_KEY', '')

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)


@app.before_request
def tving_https():
    if request.headers.get('X-Forwarded-Proto') == 'http':
        return redirect(request.url.replace('http://', 'https://', 1), code=301)


@app.after_request
def cache_headers(response):
    if request.path == '/sw.js':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route('/')
def index():
    return app.send_static_file('index.html')


if __name__ == '__main__':
    init_db()
    _migrer_db()
    start_bakgrunnsoppdatering()
    port = int(os.environ.get('PORT', 7342))
    app.run(host='0.0.0.0', port=port, debug=True)
