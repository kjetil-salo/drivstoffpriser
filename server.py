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
import os
import uuid
import httpx
from flask import Flask, request, jsonify, send_from_directory, make_response

from db import init_db, get_stasjoner_med_priser, lagre_pris, logg_visning, get_statistikk
from osm import hent_stasjoner_fra_osm

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('drivstoff')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path='')


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/stasjoner')
def stasjoner():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'lat og lon er påkrevd'}), 400

    try:
        hent_stasjoner_fra_osm(lat, lon)
    except Exception as e:
        logger.warning(f'OSM-henting feilet: {e}')

    data = get_stasjoner_med_priser(lat, lon)
    return jsonify({'stasjoner': data})


@app.route('/api/stedssok')
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


@app.route('/oversikt')
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
    labels = [d for d, _ in stats['trend_30d']]
    values = [c for _, c in stats['trend_30d']]
    siste_rader = ''.join(
        f'<tr><td>{r["ts"][:16]}</td><td>{r["ip"]}</td><td style="font-size:0.75rem;color:#94a3b8">{r["device_id"][:8]}…</td></tr>'
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


@app.route('/api/logview', methods=['POST'])
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


@app.route('/api/pris', methods=['POST'])
def oppdater_pris():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')

    if not stasjon_id:
        return jsonify({'error': 'stasjon_id er påkrevd'}), 400

    bensin_raw = data.get('bensin')
    diesel_raw = data.get('diesel')

    def til_float(v):
        if v is None or v == '':
            return None
        try:
            return float(str(v).replace(',', '.'))
        except ValueError:
            return None

    bensin = til_float(bensin_raw)
    diesel = til_float(diesel_raw)

    if bensin is None and diesel is None:
        return jsonify({'error': 'Minst én pris må oppgis'}), 400

    lagre_pris(stasjon_id, bensin, diesel)
    logger.info(f'Pris lagret: stasjon={stasjon_id} bensin={bensin} diesel={diesel}')
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 7342))
    app.run(host='0.0.0.0', port=port, debug=True)
