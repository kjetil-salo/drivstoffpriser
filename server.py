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
from werkzeug.middleware.proxy_fix import ProxyFix

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
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
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


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https://cdnjs.cloudflare.com https://raw.githubusercontent.com "
    "https://*.openstreetmap.org https://www.google.com; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "worker-src 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.after_request
def security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(self), camera=(), microphone=()'
    response.headers['Content-Security-Policy'] = _CSP
    return response


@app.after_request
def cache_headers(response):
    path = request.path
    method = request.method

    # Service Worker: alltid revalidér
    if path == '/sw.js':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # Skriveoperasjoner: aldri cache
    if method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        response.headers['Cache-Control'] = 'no-store'
        return response

    # API-endepunkter
    if path.startswith('/api/'):
        if path.startswith('/api/stasjoner') or path in ('/api/meg', '/api/instance', '/api/share/prices'):
            # Priser er ferskvare – aldri cache
            response.headers['Cache-Control'] = 'no-store'
        elif path in ('/api/statistikk', '/api/totalt-med-pris'):
            response.headers['Cache-Control'] = 'public, max-age=300'
        elif path == '/api/toppliste':
            response.headers['Cache-Control'] = 'no-store'
        elif path == '/api/nyhet':
            response.headers['Cache-Control'] = 'public, max-age=3600'
        elif path.startswith('/api/stedssok'):
            response.headers['Cache-Control'] = 'public, max-age=86400'
        else:
            response.headers['Cache-Control'] = 'no-store'
        return response

    # HTML: revalidér alltid (bruker ETags/304)
    if response.content_type and 'html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache'
        return response

    # Ikoner og bilder: 30 dager
    if any(path.endswith(ext) for ext in ('.ico', '.png', '.svg', '.webp', '.jpg')):
        response.headers['Cache-Control'] = 'public, max-age=2592000, immutable'
        return response

    # JS og CSS: revalidér (ingen content-hashing, no-cache er tryggest)
    if any(path.endswith(ext) for ext in ('.js', '.css')):
        response.headers['Cache-Control'] = 'no-cache'
        return response

    return response


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/kart2')
def kart2():
    return app.send_static_file('kart2.html')


@app.route('/bidrag')
def bidrag():
    return app.send_static_file('bidrag.html')


@app.route('/blogg')
def blogg_redirect():
    return redirect('/blogg/', code=301)


@app.route('/blogg/')
def blogg():
    return app.send_static_file('blogg/index.html')


if __name__ == '__main__':
    init_db()
    _migrer_db()
    start_bakgrunnsoppdatering()
    port = int(os.environ.get('PORT', 7342))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
