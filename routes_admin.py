"""Admin-ruter: brukeradministrasjon og prislogg."""

import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, session, redirect, jsonify

from db import (finn_bruker_id, hent_alle_brukere, slett_bruker,
                opprett_invitasjon, hent_siste_prisoppdateringer)

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
<nav><a href="/">← Appen</a> &nbsp;·&nbsp; <a href="/oversikt?key={os.environ.get("STATS_KEY","salo")}">Statistikk</a> &nbsp;·&nbsp; <a href="/admin/prislogg">Prislogg</a></nav>
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


@admin_bp.route('/admin/prislogg')
@krever_innlogging
@krever_admin
def prislogg():
    oppdateringer = hent_siste_prisoppdateringer(limit=200)
    rader = []
    for p in oppdateringer:
        def fmt(v):
            return f'{v:.2f}' if v is not None else '–'
        tidspunkt = p['tidspunkt'][:16].replace('T', ' ') if p['tidspunkt'] else '–'
        bruker = p['brukernavn'] or '<ukjent>'
        stasjon = p['navn'] + (f' ({p["kjede"]})' if p['kjede'] else '')
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
<nav><a href="/">← Appen</a> &nbsp;·&nbsp; <a href="/admin">Admin</a></nav>
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
    return redirect('/admin')
