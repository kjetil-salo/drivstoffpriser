"""Admin-ruter: brukeradministrasjon og prislogg."""

import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, session, redirect, jsonify

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from db import (finn_bruker_id, hent_alle_brukere, slett_bruker,
                opprett_invitasjon, hent_siste_prisoppdateringer,
                stasjoner_med_pris_koordinater, get_statistikk,
                antall_stasjoner_med_pris, antall_brukere,
                hent_brukerstasjoner, slett_stasjon)

admin_bp = Blueprint('admin', __name__)


def krever_innlogging(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('bruker_id'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Ikke innlogget'}), 401
            return redirect('/auth/logg-inn')
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


@admin_bp.route('/admin')
@krever_innlogging
@krever_admin
def admin():
    brukere_antall = antall_brukere()
    stasjoner_antall = antall_stasjoner_med_pris()
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:1rem}}
  .tile{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:1.5rem;
         text-decoration:none;color:#e5e7eb;transition:border-color 0.15s,transform 0.15s}}
  .tile:hover{{border-color:#3b82f6;transform:translateY(-2px)}}
  .tile-ikon{{font-size:1.8rem;margin-bottom:0.75rem}}
  .tile-tittel{{font-size:0.95rem;font-weight:600;margin-bottom:0.3rem}}
  .tile-info{{font-size:0.78rem;color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/">← Appen</a></nav>
<h1>Admin</h1>
<div class="tiles">
  <a href="/admin/brukere" class="tile">
    <div class="tile-ikon">👥</div>
    <div class="tile-tittel">Brukere</div>
    <div class="tile-info">{brukere_antall} registrerte</div>
  </a>
  <a href="/admin/steder" class="tile">
    <div class="tile-ikon">📍</div>
    <div class="tile-tittel">Steder</div>
    <div class="tile-info">Bruker-opprettede stasjoner</div>
  </a>
  <a href="/admin/oversikt" class="tile">
    <div class="tile-ikon">📊</div>
    <div class="tile-tittel">Statistikk</div>
    <div class="tile-info">Visninger og trender</div>
  </a>
  <a href="/admin/prislogg" class="tile">
    <div class="tile-ikon">💰</div>
    <div class="tile-tittel">Prislogg</div>
    <div class="tile-info">Siste prisoppdateringer</div>
  </a>
  <a href="/admin/kart" class="tile">
    <div class="tile-ikon">🗺️</div>
    <div class="tile-tittel">Kart</div>
    <div class="tile-info">{stasjoner_antall} stasjoner med pris</div>
  </a>
</div>
</div></body></html>'''


@admin_bp.route('/admin/brukere')
@krever_innlogging
@krever_admin
def admin_brukere():
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

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brukere – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  h2{{font-size:1rem;color:#94a3b8;margin-bottom:0.75rem}}
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
<nav><a href="/admin">← Admin</a></nav>
<h1>Brukere</h1>
<div class="kort">
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


@admin_bp.route('/admin/steder')
@krever_innlogging
@krever_admin
def admin_steder():
    brukerstasjoner = hent_brukerstasjoner()
    stasjon_rader = []
    for s in brukerstasjoner:
        dato = s['sist_oppdatert'][:10] if s['sist_oppdatert'] else '–'
        bruker = s['brukernavn'] or '–'
        navn = s['navn'] + (f' ({s["kjede"]})' if s['kjede'] else '')
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        stasjon_rader.append(
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{navn}</a></td>'
            f'<td style="color:#93c5fd;font-size:0.78rem">{bruker}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{dato}</td>'
            f'<td><form method="post" action="/admin/slett-stasjon" style="margin:0"'
            f' onsubmit="return confirm(\'Slette {s["navn"]}? Tilhørende priser slettes også.\')">'
            f'<input type="hidden" name="stasjon_id" value="{s["id"]}">'
            f'<button style="background:transparent;border:1px solid #ef4444;color:#ef4444;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer;width:auto">'
            f'Slett</button></form></td>'
            f'</tr>'
        )
    stasjon_rader_html = ''.join(stasjon_rader) or '<tr><td colspan="4" style="color:#94a3b8">Ingen bruker-opprettede stasjoner</td></tr>'

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Steder – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Bruker-opprettede stasjoner</h1>
<div class="kort">
  <table><tr><th>Stasjon</th><th>Lagt til av</th><th>Dato</th><th></th></tr>{stasjon_rader_html}</table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/prislogg')
@krever_innlogging
@krever_admin
def prislogg():
    oppdateringer = hent_siste_prisoppdateringer(limit=200)
    _oslo = ZoneInfo('Europe/Oslo')
    def _lokal(ts_str):
        if not ts_str:
            return '–'
        return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc).astimezone(_oslo).strftime('%Y-%m-%d %H:%M')
    rader = []
    for p in oppdateringer:
        def fmt(v):
            return f'{v:.2f}' if v is not None else '–'
        tidspunkt = _lokal(p['tidspunkt'])
        bruker = p['brukernavn'] or '<ukjent>'
        stasjon_tekst = p['navn'] + (f' ({p["kjede"]})' if p['kjede'] else '')
        if p.get('lat') and p.get('lon'):
            stasjon = f'<a href="https://www.google.com/maps?q={p["lat"]},{p["lon"]}" target="_blank" rel="noopener" style="color:#e5e7eb">{stasjon_tekst}</a>'
        else:
            stasjon = stasjon_tekst
        rader.append(
            f'<tr>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{tidspunkt}</td>'
            f'<td>{stasjon}</td>'
            f'<td style="color:#93c5fd">{bruker}</td>'
            f'<td style="text-align:right">{fmt(p["bensin"])}</td>'
            f'<td style="text-align:right">{fmt(p["bensin98"])}</td>'
            f'<td style="text-align:right">{fmt(p["diesel"])}</td>'
            f'</tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="6" style="color:#94a3b8;text-align:center">Ingen prisoppdateringer</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prislogg – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:900px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:0.85rem}}
  td,th{{padding:7px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Prislogg (siste 200)</h1>
<div class="kort">
  <table>
    <tr><th>Tidspunkt</th><th>Stasjon</th><th>Bruker</th><th style="text-align:right">95</th><th style="text-align:right">98</th><th style="text-align:right">Diesel</th></tr>
    {rader_html}
  </table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/invitasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def generer_invitasjon():
    token = secrets.token_urlsafe(32)
    utloper = (datetime.utcnow() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    opprett_invitasjon(token, utloper)
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    return jsonify({'url': f'{base_url}/invitasjon?token={token}'})


@admin_bp.route('/admin/slett-bruker', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_slett_bruker():
    bruker_id = request.form.get('bruker_id', type=int)
    if bruker_id:
        slett_bruker(bruker_id)
    return redirect('/admin/brukere')


@admin_bp.route('/admin/slett-stasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_slett_stasjon():
    stasjon_id = request.form.get('stasjon_id', type=int)
    if stasjon_id:
        slett_stasjon(stasjon_id)
    return redirect('/admin/steder')


@admin_bp.route('/admin/oversikt')
@krever_innlogging
@krever_admin
def oversikt():
    stats = get_statistikk()
    med_pris = antall_stasjoner_med_pris()
    brukere = antall_brukere()
    labels = [d for d, _ in stats['trend_30d']]
    values = [c for _, c in stats['trend_30d']]
    _oslo = ZoneInfo('Europe/Oslo')
    time_labels = []
    time_values = []
    for ts, cnt in stats['besok_per_time']:
        lokal = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(_oslo)
        time_labels.append(lokal.strftime('%H:%M'))
        time_values.append(cnt)
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
  nav {{ margin-bottom: 1.5rem; font-size: 0.85rem; }}
  nav a {{ color: #94a3b8; }}
</style>
</head>
<body>
<div class="container">
  <nav><a href="/admin">← Admin</a></nav>
  <h1>Drivstoffpriser – statistikk</h1>
  <div class="kort-rad">
    <div class="kort"><div class="kort-tal">{med_pris}</div><div class="kort-label">Stasjoner med pris</div></div>
    <div class="kort"><div class="kort-tal">{stats['prisendringer']}</div><div class="kort-label">Prisregistreringer totalt</div></div>
    <div class="kort"><div class="kort-tal">{stats['totalt']}</div><div class="kort-label">Sidevisninger totalt</div></div>
    <div class="kort"><div class="kort-tal">{stats['unike_enheter']}</div><div class="kort-label">Unike enheter</div></div>
    <div class="kort"><div class="kort-tal">{brukere}</div><div class="kort-label">Registrerte brukere</div></div>
  </div>
  <div class="seksjon">
    <h2>Sidevisninger siste 30 dager</h2>
    <canvas id="graf" style="width:100%;max-height:240px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Besøk siste 10 timer</h2>
    <canvas id="timegraf" style="width:100%;max-height:200px"></canvas>
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
new Chart(document.getElementById('timegraf'), {{
  type: 'bar',
  data: {{
    labels: {time_labels},
    datasets: [{{ label: 'Besøk', data: {time_values},
      backgroundColor: 'rgba(34,197,94,0.6)',
      borderColor: 'rgba(34,197,94,1)', borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ stepSize: 1, color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
    }}
  }}
}});
</script>
</body>
</html>'''


@admin_bp.route('/admin/kart')
@krever_innlogging
@krever_admin
def admin_kart():
    import json
    stasjoner = stasjoner_med_pris_koordinater()
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Priskart – Admin</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb}}
  nav{{padding:1rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  h1{{font-size:1.3rem;padding:0 1rem 1rem;color:#f1f5f9}}
  #map{{height:calc(100vh - 100px);width:100%;border-radius:10px;margin:0 auto;max-width:1200px}}
  .info{{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:0.75rem 1rem;
         margin:0 1rem 1rem;font-size:0.85rem;color:#94a3b8;display:inline-block}}
  .legend{{display:inline-block;margin-left:1rem;background:#111827;border:1px solid #1f2937;border-radius:8px;padding:0.75rem 1rem;font-size:0.85rem;color:#94a3b8}}
  .legend span{{display:inline-flex;align-items:center;margin-right:1rem}}
  .legend .dot{{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:0.4rem}}
</style></head><body>
<nav><a href="/admin">← Admin</a></nav>
<h1>Registrerte priser i Norge</h1>
<div class="info">{len(stasjoner)} stasjoner med pris</div>
<div class="legend"><span><span class="dot" style="background:#22c55e"></span>&lt; 8 timer</span><span><span class="dot" style="background:#f59e0b"></span>8–24 timer</span><span><span class="dot" style="background:#ef4444"></span>&gt; 24 timer</span><span><span class="dot" style="background:#6b7280"></span>Ukjent</span></div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const stasjoner = {json.dumps(stasjoner, ensure_ascii=False)};
const map = L.map('map').setView([63.4, 10.4], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap'
}}).addTo(map);
function prisFarge(tidspunkt) {{
  if (!tidspunkt) return '#6b7280';
  const timer = (Date.now() - new Date(tidspunkt.replace(' ', 'T')).getTime()) / 3600000;
  if (timer < 8) return '#22c55e';
  if (timer < 24) return '#f59e0b';
  return '#ef4444';
}}
stasjoner.forEach(s => {{
  const priser = [
    s.bensin ? '95: ' + s.bensin.toFixed(2) : null,
    s.bensin98 ? '98: ' + s.bensin98.toFixed(2) : null,
    s.diesel ? 'Diesel: ' + s.diesel.toFixed(2) : null
  ].filter(Boolean).join('<br>');
  const dato = s.tidspunkt ? s.tidspunkt.slice(0, 10) : '';
  const farge = prisFarge(s.tidspunkt);
  L.circleMarker([s.lat, s.lon], {{
    radius: 7, fillColor: farge, color: '#1e3a5f', weight: 1, fillOpacity: 0.8
  }}).addTo(map).bindPopup(
    '<b>' + s.navn + '</b>' + (s.kjede ? ' (' + s.kjede + ')' : '') +
    '<br>' + priser + '<br><span style="color:#888;font-size:0.8em">' + dato + '</span>'
  );
}});
if (stasjoner.length) {{
  const bounds = L.latLngBounds(stasjoner.map(s => [s.lat, s.lon]));
  map.fitBounds(bounds, {{ padding: [30, 30] }});
}}
</script></body></html>'''
