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
import uuid
import secrets
from datetime import datetime, timedelta
from functools import wraps
import httpx
from flask import Flask, request, jsonify, send_from_directory, make_response, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from db import (init_db, get_stasjoner_med_priser, lagre_pris, logg_visning, get_statistikk,
                antall_brukere, opprett_bruker, finn_bruker, finn_bruker_id,
                hent_alle_brukere, slett_bruker,
                opprett_invitasjon, hent_invitasjon, merk_invitasjon_brukt)
from osm import hent_stasjoner_fra_osm

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('drivstoff')

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


def _auth_side(tittel, innhold, feil=''):
    feil_html = f'<p class="feil">{feil}</p>' if feil else ''
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{tittel} – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;
       display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:12px;
         padding:2rem;width:100%;max-width:380px}}
  h1{{font-size:1.2rem;margin-bottom:1.5rem;color:#f1f5f9}}
  label{{display:block;font-size:0.78rem;color:#94a3b8;margin-bottom:4px}}
  input{{width:100%;background:#1f2937;border:1px solid #374151;border-radius:6px;
         color:#e5e7eb;font-size:1rem;padding:10px 12px;margin-bottom:1rem;outline:none}}
  input:focus{{border-color:#3b82f6}}
  button{{width:100%;background:#3b82f6;border:none;border-radius:6px;color:white;
          font-size:1rem;font-weight:600;padding:12px;cursor:pointer;margin-top:0.5rem}}
  button:hover{{background:#2563eb}}
  .feil{{color:#ef4444;font-size:0.85rem;margin-bottom:1rem}}
  a{{color:#94a3b8;font-size:0.82rem;display:block;text-align:center;margin-top:1rem}}
</style></head><body><div class="kort">
<h1>{tittel}</h1>{feil_html}{innhold}</div></body></html>'''


def krever_innlogging(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('bruker_id'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Ikke innlogget'}), 401
            return redirect(url_for('logg_inn'))
        return f(*args, **kwargs)
    return wrapper


def krever_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        bruker = finn_bruker_id(session.get('bruker_id', 0))
        if not bruker or not bruker['er_admin']:
            return 'Ikke tilgang', 403
        return f(*args, **kwargs)
    return wrapper


@app.route('/auth/logg-inn', methods=['GET', 'POST'])
def logg_inn():
    if session.get('bruker_id'):
        return redirect('/')

    # Første gang: ingen brukere → opprett admin
    ingen_brukere = antall_brukere() == 0

    if request.method == 'POST':
        brukernavn = request.form.get('brukernavn', '').strip()
        passord = request.form.get('passord', '').strip()

        if ingen_brukere:
            if not brukernavn or not passord:
                return _auth_side('Opprett admin', _admin_form(), 'Fyll inn brukernavn og passord.')
            opprett_bruker(brukernavn, generate_password_hash(passord), er_admin=True)
            bruker = finn_bruker(brukernavn)
            session['bruker_id'] = bruker['id']
            return redirect('/')

        bruker = finn_bruker(brukernavn)
        if not bruker or not check_password_hash(bruker['passord_hash'], passord):
            return _auth_side('Logg inn', _login_form(), 'Feil brukernavn eller passord.')
        session['bruker_id'] = bruker['id']
        return redirect('/')

    if ingen_brukere:
        return _auth_side('Opprett admin', _admin_form())
    return _auth_side('Logg inn', _login_form())


def _login_form():
    return '''<form method="post">
<label>Brukernavn</label><input name="brukernavn" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="current-password">
<button>Logg inn</button></form>'''


def _admin_form():
    return '''<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1rem">
Ingen brukere finnes. Opprett admin-konto.</p>
<form method="post">
<label>Brukernavn</label><input name="brukernavn" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="new-password">
<button>Opprett admin</button></form>'''


@app.route('/auth/logg-ut')
def logg_ut():
    session.clear()
    return redirect('/')


@app.route('/api/meg')
def meg():
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return jsonify({'innlogget': False})
    bruker = finn_bruker_id(bruker_id)
    if not bruker:
        session.clear()
        return jsonify({'innlogget': False})
    return jsonify({'innlogget': True, 'brukernavn': bruker['brukernavn'], 'er_admin': bool(bruker['er_admin'])})


@app.route('/invitasjon', methods=['GET', 'POST'])
def invitasjon():
    token = request.args.get('token') or request.form.get('token', '')
    inv = hent_invitasjon(token)
    if not inv:
        return _auth_side('Ugyldig lenke', '<p style="color:#94a3b8">Lenken er ugyldig eller utløpt.</p><a href="/">← Tilbake</a>')

    if request.method == 'POST':
        brukernavn = request.form.get('brukernavn', '').strip()
        passord = request.form.get('passord', '').strip()
        if not brukernavn or len(passord) < 6:
            return _auth_side('Opprett konto', _invitasjon_form(token), 'Brukernavn må fylles ut og passord må være minst 6 tegn.')
        if finn_bruker(brukernavn):
            return _auth_side('Opprett konto', _invitasjon_form(token), 'Brukernavnet er allerede i bruk.')
        opprett_bruker(brukernavn, generate_password_hash(passord))
        merk_invitasjon_brukt(token)
        bruker = finn_bruker(brukernavn)
        session['bruker_id'] = bruker['id']
        return redirect('/')

    return _auth_side('Opprett konto', _invitasjon_form(token))


def _invitasjon_form(token):
    return f'''<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1rem">
Du er invitert! Velg brukernavn og passord.</p>
<form method="post">
<input type="hidden" name="token" value="{token}">
<label>Brukernavn</label><input name="brukernavn" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="new-password">
<button>Opprett konto</button></form>'''


@app.route('/admin')
@krever_innlogging
@krever_admin
def admin():
    brukere = hent_alle_brukere()
    rader = []
    for b in brukere:
        navn = b['brukernavn'] + ('&nbsp;👑' if b['er_admin'] else '')
        dato = b['opprettet'][:10]
        if b['er_admin']:
            slett_td = '<td></td>'
        else:
            slett_td = (
                f'<td><form method="post" action="/admin/slett-bruker" style="margin:0">'
                f'<input type="hidden" name="bruker_id" value="{b["id"]}">'
                '<button style="background:transparent;border:1px solid #ef4444;color:#ef4444;'
                'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer;width:auto">'
                'Slett</button></form></td>'
            )
        rader.append(f'<tr><td>{navn}</td><td style="color:#94a3b8;font-size:0.78rem">{dato}</td>{slett_td}</tr>')
    bruker_rader = ''.join(rader)
    base_url = request.host_url.rstrip('/')
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  h2{{font-size:1rem;color:#94a3b8;margin-bottom:0.75rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  .btn{{background:#3b82f6;border:none;border-radius:6px;color:white;font-size:0.9rem;
        font-weight:600;padding:10px 18px;cursor:pointer}}
  .btn:hover{{background:#2563eb}}
  .lenke-boks{{background:#1f2937;border:1px solid #374151;border-radius:6px;padding:10px 12px;
               font-size:0.82rem;word-break:break-all;color:#93c5fd;margin-top:1rem}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/">← Appen</a> &nbsp;·&nbsp; <a href="/oversikt?key={os.environ.get("STATS_KEY","salo")}">Statistikk</a></nav>
<h1>Admin</h1>
<div class="kort">
  <h2>Brukere</h2>
  <table><tr><th>Brukernavn</th><th>Opprettet</th><th></th></tr>{bruker_rader}</table>
</div>
<div class="kort">
  <h2>Inviter ny bruker</h2>
  <form method="post" action="/admin/invitasjon">
    <button class="btn">Generer invitasjonslenke</button>
  </form>
  <div id="lenke-boks"></div>
</div>
</div>
<script>
document.querySelector('form[action="/admin/invitasjon"]').addEventListener('submit', async e => {{
  e.preventDefault();
  const resp = await fetch('/admin/invitasjon', {{method:'POST'}});
  const data = await resp.json();
  document.getElementById('lenke-boks').innerHTML =
    '<div class="lenke-boks">' + data.url + '</div>';
}});
</script>
</body></html>'''


@app.route('/admin/invitasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def generer_invitasjon():
    token = secrets.token_urlsafe(32)
    utloper = (datetime.utcnow() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    opprett_invitasjon(token, utloper)
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    return jsonify({'url': f'{base_url}/invitasjon?token={token}'})


@app.route('/admin/slett-bruker', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_slett_bruker():
    bruker_id = request.form.get('bruker_id', type=int)
    if bruker_id:
        slett_bruker(bruker_id)
    return redirect('/admin')


@app.route('/')
def index():
    return app.send_static_file('index.html')


NORGE_BBOX = {'lat_min': 57.0, 'lat_max': 71.5, 'lon_min': 4.0, 'lon_max': 31.5}

def er_i_norge(lat, lon):
    return (NORGE_BBOX['lat_min'] <= lat <= NORGE_BBOX['lat_max'] and
            NORGE_BBOX['lon_min'] <= lon <= NORGE_BBOX['lon_max'])

@app.route('/api/stasjoner')
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
        f'<tr><td>{r["ts"][:16]}</td><td><a href="https://ipinfo.io/{r["ip"]}" target="_blank" rel="noopener" style="color:#3b82f6">{r["ip"]}</a></td><td style="font-size:0.75rem;color:#94a3b8">{r["device_id"][:8]}…</td></tr>'
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
@krever_innlogging
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
