"""API-ruter: stasjoner, priser, stedssøk, statistikk."""

import logging
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from zoneinfo import ZoneInfo

import httpx
from flask import Blueprint, request, jsonify, make_response, session

from db import (get_stasjoner_med_priser, lagre_pris, logg_visning, get_statistikk,
                antall_stasjoner_med_pris, finn_bruker_id)
from osm import hent_stasjoner_fra_osm

logger = logging.getLogger('drivstoff')

api_bp = Blueprint('api', __name__)

NORGE_BBOX = {'lat_min': 57.0, 'lat_max': 71.5, 'lon_min': 4.0, 'lon_max': 31.5}


def er_i_norge(lat, lon):
    return (NORGE_BBOX['lat_min'] <= lat <= NORGE_BBOX['lat_max'] and
            NORGE_BBOX['lon_min'] <= lon <= NORGE_BBOX['lon_max'])


def krever_innlogging(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('bruker_id'):
            return jsonify({'error': 'Ikke innlogget'}), 401
        return f(*args, **kwargs)
    return wrapper


@api_bp.route('/api/meg')
def meg():
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return jsonify({'innlogget': False})
    bruker = finn_bruker_id(bruker_id)
    if not bruker:
        session.clear()
        return jsonify({'innlogget': False})
    return jsonify({'innlogget': True, 'brukernavn': bruker['brukernavn'], 'er_admin': bool(bruker['er_admin'])})


@api_bp.route('/api/stasjoner')
def stasjoner():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'lat og lon er påkrevd'}), 400
    if not er_i_norge(lat, lon):
        return jsonify({'error': 'Kun tilgjengelig i Norge', 'utenfor': True}), 400

    try:
        hent_stasjoner_fra_osm(lat, lon)
    except Exception as e:
        logger.warning(f'OSM-henting feilet: {e}')

    data = get_stasjoner_med_priser(lat, lon)
    return jsonify({'stasjoner': data})


@api_bp.route('/api/stedssok')
def stedssok():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        resp = httpx.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': q, 'format': 'json', 'limit': 5, 'countrycodes': 'no', 'accept-language': 'no'},
            headers={'User-Agent': 'drivstoffpriser/1.0 (hobby)'},
            timeout=8,
        )
        data = resp.json()
        return jsonify([
            {'navn': r['display_name'], 'lat': float(r['lat']), 'lon': float(r['lon'])}
            for r in data
        ])
    except Exception as e:
        logger.warning(f'Stedssøk feilet: {e}')
        return jsonify([])


@api_bp.route('/api/logview', methods=['POST'])
def logview():
    device_id = request.cookies.get('device_id', '')
    ny_enhet = not device_id
    if ny_enhet:
        device_id = str(uuid.uuid4())

    ip = request.headers.get('CF-Connecting-IP') or \
         request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or \
         request.remote_addr or ''
    ua = request.headers.get('User-Agent', '')

    try:
        logg_visning(ip, device_id, ua)
    except Exception as e:
        logger.warning(f'Logging feilet: {e}')

    resp = make_response(jsonify({'ok': True}))
    if ny_enhet:
        resp.set_cookie('device_id', device_id, max_age=63072000, samesite='Lax', path='/')
    return resp


@api_bp.route('/api/totalt-med-pris')
def totalt_med_pris():
    return jsonify({'totalt': antall_stasjoner_med_pris()})


@api_bp.route('/api/pris', methods=['POST'])
@krever_innlogging
def oppdater_pris():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')

    if not stasjon_id:
        return jsonify({'error': 'stasjon_id er påkrevd'}), 400

    bensin_raw = data.get('bensin')
    diesel_raw = data.get('diesel')
    bensin98_raw = data.get('bensin98')

    def til_float(v):
        if v is None or v == '':
            return None
        try:
            f = float(str(v).replace(',', '.'))
            return None if f == 0 else f
        except ValueError:
            return None

    bensin = til_float(bensin_raw)
    diesel = til_float(diesel_raw)
    bensin98 = til_float(bensin98_raw)

    bruker_id = session.get('bruker_id')
    lagre_pris(stasjon_id, bensin, diesel, bensin98, bruker_id=bruker_id)
    logger.info(f'Pris lagret: stasjon={stasjon_id} bensin={bensin} diesel={diesel} bensin98={bensin98} bruker={bruker_id}')
    return jsonify({'ok': True})


# ── Statistikk / oversikt ─────────────────────────

@api_bp.route('/oversikt')
def oversikt():
    stats_key = os.environ.get('STATS_KEY', 'salo')
    if request.args.get('key') != stats_key:
        return '''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<title>Oversikt</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#0f172a;color:#e5e7eb;}
form{background:#111827;padding:2rem;border-radius:10px;display:flex;flex-direction:column;gap:1rem;}
input{padding:10px;border-radius:6px;border:1px solid #374151;background:#1f2937;color:#e5e7eb;font-size:1rem;}
button{padding:10px;background:#3b82f6;color:white;border:none;border-radius:6px;font-size:1rem;cursor:pointer;}
</style></head><body>
<form method="get"><input name="key" type="password" placeholder="Nøkkel" autofocus>
<button>Vis statistikk</button></form></body></html>''', 401

    stats = get_statistikk()
    med_pris = antall_stasjoner_med_pris()
    labels = [d for d, _ in stats['trend_30d']]
    values = [c for _, c in stats['trend_30d']]
    _oslo = ZoneInfo('Europe/Oslo')
    def _lokal_tid(ts_str):
        return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc).astimezone(_oslo).strftime('%Y-%m-%d %H:%M')
    siste_rader = ''.join(
        f'<tr><td>{_lokal_tid(r["ts"])}</td><td><a href="https://ipinfo.io/{r["ip"]}" target="_blank" rel="noopener" style="color:#3b82f6">{r["ip"]}</a></td><td style="font-size:0.75rem;color:#94a3b8">{r["device_id"][:8]}…</td></tr>'
        for r in stats['siste_besok']
    )
    return f'''<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drivstoffpriser – oversikt</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e5e7eb; padding: 2rem 1rem; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 1.5rem; color: #f1f5f9; }}
  .kort-rad {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem; }}
  .kort {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px;
           padding: 1.2rem 1.5rem; flex: 1; min-width: 140px; }}
  .kort-tal {{ font-size: 2rem; font-weight: 700; color: #3b82f6; }}
  .kort-label {{ font-size: 0.78rem; color: #94a3b8; margin-top: 4px; }}
  .seksjon {{ margin-bottom: 2rem; }}
  .seksjon h2 {{ font-size: 1rem; color: #94a3b8; margin-bottom: 0.75rem; }}
  canvas {{ background: #111827; border-radius: 10px; padding: 1rem; border: 1px solid #1f2937; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid #1f2937; text-align: left; }}
  th {{ color: #94a3b8; font-weight: 500; }}
  .container {{ max-width: 860px; margin: 0 auto; }}
</style>
</head>
<body>
<div class="container">
  <h1>Drivstoffpriser – statistikk</h1>
  <div class="kort-rad">
    <div class="kort"><div class="kort-tal">{med_pris}</div><div class="kort-label">Stasjoner med pris</div></div>
    <div class="kort"><div class="kort-tal">{stats['prisendringer']}</div><div class="kort-label">Prisregistreringer totalt</div></div>
    <div class="kort"><div class="kort-tal">{stats['totalt']}</div><div class="kort-label">Sidevisninger totalt</div></div>
    <div class="kort"><div class="kort-tal">{stats['unike_enheter']}</div><div class="kort-label">Unike enheter</div></div>
    <div class="kort"><div class="kort-tal">{stats['unike_ips']}</div><div class="kort-label">Unike IP-adresser</div></div>
  </div>
  <div class="seksjon">
    <h2>Sidevisninger siste 30 dager</h2>
    <canvas id="graf" style="width:100%;max-height:240px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Siste 10 besøk</h2>
    <table>
      <tr><th>Tidspunkt</th><th>IP</th><th>Enhet</th></tr>
      {siste_rader}
    </table>
  </div>
</div>
<script>
new Chart(document.getElementById('graf'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [{{ label: 'Visninger', data: {values},
      backgroundColor: 'rgba(59,130,246,0.6)',
      borderColor: 'rgba(59,130,246,1)', borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 45, color: '#94a3b8', font: {{ size: 10 }} }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ stepSize: 1, color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
    }}
  }}
}});
</script>
</body>
</html>'''
