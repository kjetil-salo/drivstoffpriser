"""Admin-ruter: brukeradministrasjon og prislogg."""

import os
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, session, redirect, jsonify

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from db import (finn_bruker_id, hent_alle_brukere, slett_bruker,
                opprett_invitasjon, hent_siste_prisoppdateringer,
                stasjoner_med_pris_koordinater, get_statistikk,
                antall_stasjoner_med_pris, antall_brukere,
                hent_brukerstasjoner, slett_stasjon,
                hent_innstilling, sett_innstilling,
                nye_brukere_per_time_48t, prisoppdateringer_per_time_48t,
                hent_rapporter, antall_ubehandlede_rapporter,
                deaktiver_stasjon, reaktiver_stasjon,
                slett_rapporter_for_stasjon, hent_deaktiverte_stasjoner,
                hent_rapportorer_epost, finn_stasjoner_by_osm_ids,
                lagre_pris, hent_eller_opprett_partner, hent_toppliste,
                sett_kjede_for_stasjon, finn_naer_stasjon, opprett_stasjon,
                hent_blogg_stats)

admin_bp = Blueprint('admin', __name__)


def _send_takk_for_rapport(eposter: list[str], stasjonsnavn: str):
    """Send takke-e-post til brukere som rapporterte en nedlagt stasjon."""
    if not eposter:
        return
    import resend
    import logging
    for epost in eposter:
        try:
            resend.Emails.send({
                'from': 'Drivstoffpriser <noreply@ksalo.no>',
                'to': epost,
                'subject': 'Takk for rapporten!',
                'html': f'<p>Hei!</p>'
                        f'<p>Takk for at du meldte inn at <strong>{stasjonsnavn}</strong> er nedlagt. '
                        f'Vi har nå fjernet stasjonen fra kartet.</p>'
                        f'<p>Slike tilbakemeldinger hjelper oss med å holde dataene oppdaterte for alle brukere. '
                        f'Vi setter stor pris på bidraget ditt!</p>'
                        f'<p>Mvh,<br>Drivstoffpriser</p>',
            })
        except Exception as e:
            logging.getLogger('drivstoff').error(f'Takke-epost til {epost} feilet: {e}')


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
    rapporter_antall = antall_ubehandlede_rapporter()
    deaktiverte_antall = len(hent_deaktiverte_stasjoner())
    reg_stoppet = hent_innstilling('registrering_stoppet') == '1'
    reg_status = 'STOPPET' if reg_stoppet else 'Åpen'
    reg_farge = '#ef4444' if reg_stoppet else '#22c55e'
    reg_knapp = 'Stopp registrering' if not reg_stoppet else 'Åpne registrering'
    reg_verdi = '0' if reg_stoppet else '1'
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
  .admin-panel{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:1.25rem;margin-bottom:1.5rem}}
  .admin-panel h2{{font-size:0.95rem;margin-bottom:0.75rem;color:#f1f5f9}}
  .admin-rad{{display:flex;align-items:center;justify-content:space-between;gap:1rem}}
  .admin-status{{font-size:0.85rem;font-weight:600}}
  .admin-btn{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
              font-size:0.82rem;padding:8px 14px;cursor:pointer;transition:background 0.15s}}
  .admin-btn:hover{{background:#374151}}
  .admin-btn.fare{{border-color:#ef4444;color:#ef4444}}
  .admin-btn.fare:hover{{background:rgba(239,68,68,0.15)}}
  .admin-btn.ok{{border-color:#22c55e;color:#22c55e}}
  .admin-btn.ok:hover{{background:rgba(34,197,94,0.15)}}
</style></head><body><div class="container">
<nav><a href="/">&#8592; Appen</a></nav>
<h1>Admin</h1>

<div class="tiles">
  <a href="/admin/oversikt" class="tile">
    <div class="tile-ikon">&#128202;</div>
    <div class="tile-tittel">Statistikk</div>
    <div class="tile-info">Visninger og trender</div>
  </a>
  <a href="/admin/prislogg" class="tile">
    <div class="tile-ikon">&#128176;</div>
    <div class="tile-tittel">Prislogg</div>
    <div class="tile-info">Siste prisoppdateringer</div>
  </a>
  <a href="/admin/kart" class="tile">
    <div class="tile-ikon">&#128506;&#65039;</div>
    <div class="tile-tittel">Kart</div>
    <div class="tile-info">{stasjoner_antall} stasjoner med pris</div>
  </a>
  <a href="/admin/import" class="tile">
    <div class="tile-ikon">&#128229;</div>
    <div class="tile-tittel">Import</div>
    <div class="tile-info">Partnerdata</div>
  </a>
  <a href="/admin/steder" class="tile">
    <div class="tile-ikon">&#128205;</div>
    <div class="tile-tittel">Steder</div>
    <div class="tile-info">Bruker-opprettede stasjoner</div>
  </a>
  <a href="/admin/brukere" class="tile">
    <div class="tile-ikon">&#128101;</div>
    <div class="tile-tittel">Brukere</div>
    <div class="tile-info">{brukere_antall} registrerte</div>
  </a>
  <a href="/admin/rapporter" class="tile" {('style="border-color:#f59e0b"' if rapporter_antall else '')}>
    <div class="tile-ikon">&#9888;&#65039;</div>
    <div class="tile-tittel">Rapporter</div>
    <div class="tile-info">{rapporter_antall} ubehandlede</div>
  </a>
  <a href="/admin/deaktiverte" class="tile">
    <div class="tile-ikon">&#128683;</div>
    <div class="tile-tittel">Deaktiverte</div>
    <div class="tile-info">{deaktiverte_antall} stasjoner</div>
  </a>
  <a href="/admin/nyhet" class="tile">
    <div class="tile-ikon">&#128227;</div>
    <div class="tile-tittel">Nyhet</div>
    <div class="tile-info">Splash-melding</div>
  </a>
  <a href="/admin/toppliste" class="tile">
    <div class="tile-ikon">&#127942;</div>
    <div class="tile-tittel">Toppliste</div>
    <div class="tile-info">Prisregistreringer</div>
  </a>
</div>

<div class="admin-panel" style="margin-top:1.5rem">
  <h2>Registrering</h2>
  <div class="admin-rad">
    <span class="admin-status" style="color:{reg_farge}">&#9679; {reg_status}</span>
    <form method="post" action="/admin/toggle-registrering" style="margin:0">
      <input type="hidden" name="verdi" value="{reg_verdi}">
      <button class="admin-btn {'ok' if reg_stoppet else 'fare'}">{reg_knapp}</button>
    </form>
  </div>
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


@admin_bp.route('/admin/toggle-registrering', methods=['POST'])
@krever_innlogging
@krever_admin
def toggle_registrering():
    verdi = request.form.get('verdi', '0')
    sett_innstilling('registrering_stoppet', '1' if verdi == '1' else '0')
    return redirect('/admin')


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


@admin_bp.route('/admin/rapporter')
@krever_innlogging
@krever_admin
def admin_rapporter():
    rapporter = hent_rapporter()
    rader = []
    for r in rapporter:
        navn = r['navn'] + (f' ({r["kjede"]})' if r['kjede'] else '')
        kart_url = f'https://www.google.com/maps?q={r["lat"]},{r["lon"]}'
        dato = r['tidspunkt'][:10] if r['tidspunkt'] else '–'
        rader.append(
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{navn}</a></td>'
            f'<td style="text-align:center;color:#f59e0b;font-weight:600">{r["antall"]}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{r["brukernavn"] or "–"}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{dato}</td>'
            f'<td style="white-space:nowrap">'
            f'<form method="post" action="/admin/deaktiver-stasjon" style="display:inline;margin:0"'
            f' onsubmit="return confirm(\'Deaktivere {r["navn"]}? Stasjonen skjules fra brukere.\')">'
            f'<input type="hidden" name="stasjon_id" value="{r["stasjon_id"]}">'
            f'<button style="background:transparent;border:1px solid #ef4444;color:#ef4444;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer;margin-right:4px">'
            f'Deaktiver</button></form>'
            f'<form method="post" action="/admin/avvis-rapport" style="display:inline;margin:0">'
            f'<input type="hidden" name="stasjon_id" value="{r["stasjon_id"]}">'
            f'<button style="background:transparent;border:1px solid #94a3b8;color:#94a3b8;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer">'
            f'Avvis</button></form>'
            f'</td></tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="5" style="color:#94a3b8">Ingen rapporter</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapporter – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:800px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  p.info{{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Meldte stasjoner</h1>
<p class="info">Stasjoner som brukere har meldt som nedlagt. Klikk stasjonsnavnet for å sjekke i Google Maps.</p>
<div class="kort">
  <table><tr><th>Stasjon</th><th style="text-align:center">Antall</th><th>Sist meldt av</th><th>Dato</th><th></th></tr>{rader_html}</table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/deaktiverte')
@krever_innlogging
@krever_admin
def admin_deaktiverte():
    stasjoner = hent_deaktiverte_stasjoner()
    rader = []
    for s in stasjoner:
        navn = s['navn'] + (f' ({s["kjede"]})' if s['kjede'] else '')
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        dato = s['sist_oppdatert'][:10] if s['sist_oppdatert'] else '–'
        rader.append(
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{navn}</a></td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{dato}</td>'
            f'<td><form method="post" action="/admin/reaktiver-stasjon" style="margin:0"'
            f' onsubmit="return confirm(\'Reaktivere {s["navn"]}?\')">'
            f'<input type="hidden" name="stasjon_id" value="{s["id"]}">'
            f'<button style="background:transparent;border:1px solid #22c55e;color:#22c55e;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer">'
            f'Reaktiver</button></form></td>'
            f'</tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="3" style="color:#94a3b8">Ingen deaktiverte stasjoner</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deaktiverte – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  p.info{{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Deaktiverte stasjoner</h1>
<p class="info">Disse stasjonene er skjult for brukere. Reaktiver hvis de likevel er i drift.</p>
<div class="kort">
  <table><tr><th>Stasjon</th><th>Deaktivert</th><th></th></tr>{rader_html}</table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/deaktiver-stasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_deaktiver_stasjon():
    stasjon_id = request.form.get('stasjon_id', type=int)
    if stasjon_id:
        stasjonsnavn, eposter = hent_rapportorer_epost(stasjon_id)
        deaktiver_stasjon(stasjon_id)
        slett_rapporter_for_stasjon(stasjon_id)
        _send_takk_for_rapport(eposter, stasjonsnavn)
    return redirect('/admin/rapporter')


@admin_bp.route('/admin/reaktiver-stasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_reaktiver_stasjon():
    stasjon_id = request.form.get('stasjon_id', type=int)
    if stasjon_id:
        reaktiver_stasjon(stasjon_id)
    return redirect('/admin/deaktiverte')


@admin_bp.route('/admin/sett-kjede', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_sett_kjede():
    data = request.get_json()
    stasjon_id = data.get('stasjon_id') if data else None
    kjede = data.get('kjede', '') if data else ''
    if not stasjon_id:
        return {'error': 'Mangler stasjon_id'}, 400
    sett_kjede_for_stasjon(int(stasjon_id), kjede)
    return {'ok': True}


@admin_bp.route('/admin/avvis-rapport', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_avvis_rapport():
    stasjon_id = request.form.get('stasjon_id', type=int)
    if stasjon_id:
        slett_rapporter_for_stasjon(stasjon_id)
    return redirect('/admin/rapporter')


@admin_bp.route('/admin/nyhet', methods=['GET', 'POST'])
@krever_innlogging
@krever_admin
def admin_nyhet():
    if request.method == 'POST':
        action = request.form.get('action', 'lagre')
        if action == 'fjern':
            sett_innstilling('nyhet_tekst', '')
            sett_innstilling('nyhet_utloper', '')
        else:
            tekst = request.form.get('tekst', '').strip()
            utloper = request.form.get('utloper', '').strip()
            if tekst and utloper:
                sett_innstilling('nyhet_tekst', tekst)
                sett_innstilling('nyhet_utloper', utloper)
        return redirect('/admin/nyhet')

    tekst = hent_innstilling('nyhet_tekst', '')
    utloper = hent_innstilling('nyhet_utloper', '')

    aktiv = False
    gjenstaar = ''
    if tekst and utloper:
        try:
            utloper_dt = datetime.fromisoformat(utloper)
            if datetime.now() < utloper_dt:
                aktiv = True
                delta = utloper_dt - datetime.now()
                timer = int(delta.total_seconds() // 3600)
                minutter = int((delta.total_seconds() % 3600) // 60)
                gjenstaar = f'{timer}t {minutter}m'
        except ValueError:
            pass

    aktiv_html = ''
    if aktiv:
        aktiv_html = f'''
    <div class="kort" style="border-color:#22c55e">
      <h2 style="color:#22c55e">Aktiv nyhet</h2>
      <div style="background:rgba(148,163,184,0.07);border:1px solid #1f2937;border-radius:6px;padding:12px;margin-bottom:12px;white-space:pre-line;font-size:0.9rem;line-height:1.6">{tekst}</div>
      <p style="font-size:0.82rem;color:#94a3b8;margin-bottom:12px">Utløper: {utloper} (om {gjenstaar})</p>
      <form method="post" style="margin:0">
        <input type="hidden" name="action" value="fjern">
        <button class="admin-btn fare">Fjern nyhet</button>
      </form>
    </div>'''

    default_utloper = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nyhet – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  h2{{font-size:1rem;color:#94a3b8;margin-bottom:0.75rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  label{{display:block;font-size:0.85rem;color:#94a3b8;margin-bottom:4px}}
  textarea{{width:100%;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.3);
            border-radius:6px;color:#e5e7eb;font-size:0.92rem;padding:10px 14px;resize:vertical;
            min-height:100px;font-family:inherit;outline:none}}
  textarea:focus{{border-color:#3b82f6}}
  input[type="datetime-local"]{{background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.3);
            border-radius:6px;color:#e5e7eb;font-size:0.92rem;padding:10px 14px;width:100%;outline:none}}
  input[type="datetime-local"]:focus{{border-color:#3b82f6}}
  .gruppe{{margin-bottom:1rem}}
  .btn{{background:#3b82f6;border:none;border-radius:6px;color:white;font-size:0.9rem;
        font-weight:600;padding:12px 20px;cursor:pointer;width:100%}}
  .btn:hover{{background:#2563eb}}
  .admin-btn{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
              font-size:0.82rem;padding:8px 14px;cursor:pointer}}
  .admin-btn.fare{{border-color:#ef4444;color:#ef4444}}
  .admin-btn.fare:hover{{background:rgba(239,68,68,0.15)}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .preview{{background:rgba(148,163,184,0.07);border:1px solid #1f2937;border-radius:6px;
            padding:12px;margin-top:8px;white-space:pre-line;font-size:0.9rem;line-height:1.6;
            min-height:2rem;color:#94a3b8}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Nyhetsmelding</h1>
{aktiv_html}
<div class="kort">
  <h2>Publiser nyhet</h2>
  <p style="font-size:0.82rem;color:#94a3b8;margin-bottom:1rem">Meldingen vises som en splash screen for alle besøkende. Hver bruker ser den kun én gang.</p>
  <form method="post">
    <div class="gruppe">
      <label for="nyhet-tekst">Meldingstekst</label>
      <textarea id="nyhet-tekst" name="tekst" placeholder="Skriv en kort melding til brukerne …">{tekst if aktiv else ''}</textarea>
    </div>
    <div class="gruppe">
      <label for="nyhet-utloper">Utløpsdato</label>
      <input type="datetime-local" id="nyhet-utloper" name="utloper" value="{default_utloper}">
    </div>
    <div class="gruppe">
      <label>Forhåndsvisning</label>
      <div class="preview" id="preview"></div>
    </div>
    <button class="btn" type="submit">Publiser nyhet</button>
  </form>
</div>
</div>
<script>
const ta = document.getElementById('nyhet-tekst');
const pre = document.getElementById('preview');
function oppdater() {{
  pre.textContent = ta.value || '(tom)';
  pre.style.color = ta.value ? '#e5e7eb' : '#94a3b8';
}}
ta.addEventListener('input', oppdater);
oppdater();
</script>
</body></html>'''


@admin_bp.route('/admin/oversikt')
@krever_innlogging
@krever_admin
def oversikt():
    stats = get_statistikk()
    med_pris = antall_stasjoner_med_pris()
    brukere = antall_brukere()
    blogg_stats = hent_blogg_stats()
    blogg_totalt = sum(r['antall'] for r in blogg_stats)
    labels = [d for d, _ in stats['trend_30d']]
    values = [c for _, c in stats['trend_30d']]
    _oslo = ZoneInfo('Europe/Oslo')
    time_labels = []
    time_values = []
    for ts, cnt in stats['besok_per_time']:
        lokal = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(_oslo)
        time_labels.append(lokal.strftime('%H:%M'))
        time_values.append(cnt)
    # Nye brukere per time siste 48t
    bruker_48t = nye_brukere_per_time_48t()
    bruker_48_labels = []
    bruker_48_values = []
    for ts, cnt in bruker_48t:
        lokal = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(_oslo)
        bruker_48_labels.append(lokal.strftime('%d.%m %H:00'))
        bruker_48_values.append(cnt)
    # Prisoppdateringer per time siste 48t
    pris_48t = prisoppdateringer_per_time_48t()
    pris_48_labels = []
    pris_48_values = []
    for ts, cnt in pris_48t:
        lokal = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(_oslo)
        pris_48_labels.append(lokal.strftime('%d.%m %H:00'))
        pris_48_values.append(cnt)
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
    <div class="kort"><div class="kort-tal">{blogg_totalt}</div><div class="kort-label">Bloggvisninger totalt</div></div>
  </div>
  <div class="seksjon">
    <h2>Sidevisninger siste 30 dager</h2>
    <canvas id="graf" style="width:100%;max-height:240px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Besøk siste 24 timer</h2>
    <canvas id="timegraf" style="width:100%;max-height:200px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Nye brukere per time – siste 48 timer</h2>
    <canvas id="brukergraf48" style="width:100%;max-height:220px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Prisoppdateringer per time – siste 48 timer</h2>
    <canvas id="prisgraf48" style="width:100%;max-height:220px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Bloggvisninger per artikkel</h2>
    <table>
      <thead><tr><th>Slug</th><th>Visninger</th></tr></thead>
      <tbody>
        {''.join(f'<tr><td>{r["slug"]}</td><td>{r["antall"]}</td></tr>' for r in blogg_stats) or '<tr><td colspan="2" style="color:#94a3b8">Ingen data ennå</td></tr>'}
      </tbody>
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
new Chart(document.getElementById('brukergraf48'), {{
  type: 'bar',
  data: {{
    labels: {bruker_48_labels},
    datasets: [{{ label: 'Nye brukere', data: {bruker_48_values},
      backgroundColor: 'rgba(168,85,247,0.6)',
      borderColor: 'rgba(168,85,247,1)', borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 60, color: '#94a3b8', font: {{ size: 9 }}, autoSkip: true, maxTicksLimit: 16 }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ stepSize: 1, color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
    }}
  }}
}});
new Chart(document.getElementById('prisgraf48'), {{
  type: 'bar',
  data: {{
    labels: {pris_48_labels},
    datasets: [{{ label: 'Prisoppdateringer', data: {pris_48_values},
      backgroundColor: 'rgba(251,146,60,0.6)',
      borderColor: 'rgba(251,146,60,1)', borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 60, color: '#94a3b8', font: {{ size: 9 }}, autoSkip: true, maxTicksLimit: 16 }}, grid: {{ color: '#1f2937' }} }},
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
<div class="legend"><span><span class="dot" style="background:#22c55e"></span>&lt; 8 timer</span><span><span class="dot" style="background:#f59e0b"></span>8–48 timer</span><span><span class="dot" style="background:#3b82f6"></span>2–7 dager</span><span><span class="dot" style="background:#6b7280"></span>&gt; 7 dager</span></div>
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
  if (timer < 48) return '#f59e0b';
  if (timer < 168) return '#3b82f6';
  return '#6b7280';
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


@admin_bp.route('/admin/kart2')
@krever_innlogging
@krever_admin
def admin_kart2():
    import json
    stasjoner = stasjoner_med_pris_koordinater()
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Priskart grønn – Admin</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb}}
  nav{{padding:1rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  h1{{font-size:1.3rem;padding:0 1rem 1rem;color:#f1f5f9}}
  #map{{height:calc(100vh - 80px);width:100%;border-radius:10px;margin:0 auto;max-width:1200px}}
  .info{{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:0.75rem 1rem;
         margin:0 1rem 1rem;font-size:0.85rem;color:#94a3b8;display:inline-block}}
</style></head><body>
<nav><a href="/admin">← Admin</a></nav>
<h1>Stasjoner med registrerte priser</h1>
<div class="info">{len(stasjoner)} stasjoner</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const stasjoner = {json.dumps(stasjoner, ensure_ascii=False)};
const map = L.map('map').setView([63.4, 10.4], 5);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_nolabels/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  maxZoom: 19
}}).addTo(map);
stasjoner.forEach(s => {{
  L.circleMarker([s.lat, s.lon], {{
    radius: 5, fillColor: '#22c55e', color: '#22c55e', weight: 0, fillOpacity: 0.85
  }}).addTo(map);
}});
if (stasjoner.length) {{
  const bounds = L.latLngBounds(stasjoner.map(s => [s.lat, s.lon]));
  map.fitBounds(bounds, {{ padding: [30, 30] }});
}}
</script></body></html>'''


@admin_bp.route('/admin/import')
@krever_innlogging
@krever_admin
def admin_import():
    return '''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Import – Admin</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}
  .container{max-width:900px;margin:0 auto}
  h1{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}
  p.info{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}
  nav{margin-bottom:1.5rem;font-size:0.85rem}
  nav a{color:#94a3b8}
  .kort{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;overflow-x:auto}
  .btn{border:none;border-radius:6px;font-size:0.9rem;font-weight:600;padding:10px 18px;cursor:pointer}
  .btn-hent{background:#3b82f6;color:white}
  .btn-hent:hover{background:#2563eb}
  .btn-hent:disabled{opacity:0.5;cursor:not-allowed}
  .bulk-bar{display:flex;gap:0.75rem;margin-bottom:1rem;flex-wrap:wrap;align-items:center}
  .btn-godkjenn{background:transparent;border:1px solid #22c55e;color:#22c55e;font-size:0.82rem;padding:6px 14px;border-radius:6px;cursor:pointer}
  .btn-godkjenn:hover{background:rgba(34,197,94,0.15)}
  .btn-underkjenn{background:transparent;border:1px solid #ef4444;color:#ef4444;font-size:0.82rem;padding:6px 14px;border-radius:6px;cursor:pointer}
  .btn-underkjenn:hover{background:rgba(239,68,68,0.15)}
  table{width:100%;border-collapse:collapse;font-size:0.85rem}
  td,th{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}
  th{color:#94a3b8;font-weight:500}
  tr.godkjent{opacity:0.4}
  tr.underkjent{opacity:0.3;text-decoration:line-through}
  .status-ikon{font-size:1rem;margin-right:4px}
  .melding{padding:12px 16px;border-radius:8px;font-size:0.88rem;margin-bottom:1rem}
  .melding-ok{background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.3);color:#22c55e}
  .melding-feil{background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:#ef4444}
  .melding-info{background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.3);color:#93c5fd}
  .spinner{display:inline-block;width:16px;height:16px;border:2px solid #3b82f6;border-top-color:transparent;border-radius:50%;animation:spin 0.6s linear infinite;margin-right:8px;vertical-align:middle}
  @keyframes spin{to{transform:rotate(360deg)}}
  .teller{font-size:0.85rem;color:#94a3b8;margin-left:auto}
</style></head><body><div class="container">
<nav><a href="/admin">&larr; Admin</a></nav>
<h1>Partnerimport</h1>
<p class="info">Hent prisdata fra partner-API. Data grupperes per stasjon (OSM-id). Gjennomgå og godkjenn enkeltvis eller samlet.</p>

<div class="kort">
  <div style="display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap">
    <button class="btn btn-hent" id="hent-btn" onclick="hentData()">Hent data</button>
    <label style="font-size:0.85rem;color:#94a3b8">
      <input type="number" id="dager-tilbake" value="1" min="1" max="30" style="width:60px;background:#1f2937;border:1px solid #374151;border-radius:4px;color:#e5e7eb;padding:4px 8px;text-align:center">
      dager tilbake
    </label>
    <span id="status-tekst" style="font-size:0.85rem;color:#94a3b8"></span>
  </div>
</div>

<div id="resultat"></div>

</div>
<script>
let importData = [];

async function hentData() {
  const btn = document.getElementById('hent-btn');
  const statusEl = document.getElementById('status-tekst');
  const resultatEl = document.getElementById('resultat');
  const dager = parseInt(document.getElementById('dager-tilbake').value) || 5;
  const from = Date.now() - dager * 86400000;

  btn.disabled = true;
  statusEl.innerHTML = '<span class="spinner"></span>Henter data ...';
  resultatEl.innerHTML = '';

  try {
    const resp = await fetch('/admin/import/hent', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({from: from})
    });
    const data = await resp.json();
    if (!resp.ok) {
      statusEl.textContent = '';
      resultatEl.innerHTML = '<div class="melding melding-feil">' + (data.error || 'Feil ved henting') + '</div>';
      btn.disabled = false;
      return;
    }
    importData = data.stasjoner || [];
    const forkastet = data.forkastet || 0;
    let info = importData.length + ' stasjoner hentet';
    if (forkastet > 0) info += ' (' + forkastet + ' rader forkastet – mangler id og koordinater)';
    statusEl.textContent = info;
    visTabell();
  } catch(e) {
    statusEl.textContent = '';
    resultatEl.innerHTML = '<div class="melding melding-feil">Nettverksfeil: ' + e.message + '</div>';
  }
  btn.disabled = false;
}

function visTabell() {
  const el = document.getElementById('resultat');
  if (importData.length === 0) {
    el.innerHTML = '<div class="melding melding-ok">Ingen nye priser fra partner.</div>';
    return;
  }

  const ventende = importData.filter(p => !p._status).length;
  let html = '<div class="kort">';
  html += '<div class="bulk-bar">';
  html += '<button class="btn-godkjenn" onclick="godkjennAlle()">Godkjenn alle</button>';
  html += '<button class="btn-underkjenn" onclick="underkjennAlle()">Underkjenn alle</button>';
  html += '<span class="teller" id="ventende-teller">' + ventende + ' ventende</span>';
  html += '</div>';
  html += '<table><tr><th>OSM-id</th><th>Vår stasjon</th><th style="text-align:right">95</th><th style="text-align:right">98</th><th style="text-align:right">Diesel</th><th style="text-align:right">Siste oppdatering</th><th></th></tr>';

  importData.forEach((s, i) => {
    const cls = s._status === 'godkjent' ? ' class="godkjent"' : s._status === 'underkjent' ? ' class="underkjent"' : '';
    const statusIkon = s._status === 'godkjent' ? '<span class="status-ikon">&#9989;</span>' :
                       s._status === 'underkjent' ? '<span class="status-ikon">&#10060;</span>' : '';
    const fmt = v => v != null ? parseFloat(v).toFixed(2) : '&#8211;';
    let matchNavn;
    if (s.match) {
      matchNavn = s.match.navn + (s.match.kjede ? ' (' + s.match.kjede + ')' : '');
    } else if (s.ukjent) {
      matchNavn = '<span style="color:#f59e0b">' + s.station_name + '</span>'
               + '<br><span style="font-size:0.75rem;color:#6b7280">'
               + s.lat.toFixed(4) + ', ' + s.lon.toFixed(4) + ' – fra partner</span>';
    } else {
      matchNavn = '<span style="color:#f59e0b">Ikke i vår DB</span>';
    }
    const osmVis = s.osm_id || '&#8211;';
    const tidKort = s.updated ? s.updated.replace('T', ' ').substring(0, 16) : '&#8211;';

    html += '<tr' + cls + '>';
    html += '<td style="font-family:monospace;font-size:0.78rem;color:#94a3b8">' + statusIkon + osmVis + '</td>';
    html += '<td>' + matchNavn + '</td>';
    html += '<td style="text-align:right">' + fmt(s.bensin) + '</td>';
    html += '<td style="text-align:right">' + fmt(s.bensin98) + '</td>';
    html += '<td style="text-align:right">' + fmt(s.diesel) + '</td>';
    html += '<td style="text-align:right;color:#94a3b8;font-size:0.78rem">' + tidKort + '</td>';
    html += '<td style="white-space:nowrap">';
    if (!s._status) {
      if (s.ukjent) {
        html += '<button class="btn-godkjenn" style="border-color:#a78bfa;color:#a78bfa" onclick="importerStasjon(' + i + ')">Importer stasjon</button> ';
      } else {
        html += '<button class="btn-godkjenn" onclick="godkjenn(' + i + ')" ' + (s.match ? '' : 'disabled title="Ikke i vår DB"') + '>Godkjenn</button> ';
      }
      html += '<button class="btn-underkjenn" onclick="underkjenn(' + i + ')">Underkjenn</button>';
    }
    html += '</td></tr>';
  });
  html += '</table></div>';
  el.innerHTML = html;
}

async function godkjenn(idx) {
  const s = importData[idx];
  if (!s.match) return;
  try {
    const resp = await fetch('/admin/import/godkjenn', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        stasjon_id: s.match.id,
        bensin: s.bensin,
        diesel: s.diesel,
        bensin98: s.bensin98
      })
    });
    if (resp.ok) {
      s._status = 'godkjent';
      visTabell();
    }
  } catch(e) { console.error(e); }
}

function underkjenn(idx) {
  importData[idx]._status = 'underkjent';
  visTabell();
}

async function godkjennAlle() {
  for (let i = 0; i < importData.length; i++) {
    const s = importData[i];
    if (s._status || !s.match) continue;
    try {
      const resp = await fetch('/admin/import/godkjenn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          stasjon_id: s.match.id,
          bensin: s.bensin,
          diesel: s.diesel,
          bensin98: s.bensin98
        })
      });
      if (resp.ok) s._status = 'godkjent';
    } catch(e) { console.error(e); }
  }
  visTabell();
}

function underkjennAlle() {
  importData.forEach(s => { if (!s._status) s._status = 'underkjent'; });
  visTabell();
}

async function importerStasjon(idx) {
  const s = importData[idx];
  try {
    const resp = await fetch('/admin/import/opprett-stasjon', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({navn: s.station_name, lat: s.lat, lon: s.lon})
    });
    const data = await resp.json();
    if (resp.ok) {
      s.match = {id: data.stasjon_id, navn: data.navn};
      s.ukjent = false;
      visTabell();
    }
  } catch(e) { console.error(e); }
}
</script>
</body></html>'''


@admin_bp.route('/admin/import/hent', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_import_hent():
    import urllib.request
    import json as json_mod

    api_url = os.environ.get('PARTNER_API_URL', 'https://api-lev4nsfo5q-uc.a.run.app/')
    api_key = os.environ.get('PARTNER_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'PARTNER_API_KEY ikke konfigurert'}), 500

    body = request.get_json(silent=True) or {}
    from_ts = body.get('from')

    url = api_url
    if from_ts:
        url += f'?from={int(from_ts)}'

    req = urllib.request.Request(url, headers={'X-API-Key': api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json_mod.loads(resp.read())
    except Exception as e:
        log = logging.getLogger('drivstoff')
        log.error(f'Partner-import feilet: {e}')
        return jsonify({'error': f'Feil ved henting fra partner: {e}'}), 502

    rader = data.get('prices', [])

    # Grupper per stasjon — bruk siste pris per drivstofftype
    ugyldige = {'ukjent_id', 'undefined', ''}
    forkastet = 0
    per_stasjon = {}
    for r in rader:
        sid = r.get('station_id') or None
        navn = (r.get('station_name') or '').strip()
        lat = r.get('lat')
        lon = r.get('lon')

        if sid is None:
            # Null ID: krever navn + koordinater for å håndteres
            if not navn or lat is None or lon is None:
                forkastet += 1
                continue
            key = f'coords:{round(float(lat), 4)}:{round(float(lon), 4)}'
            if key not in per_stasjon:
                per_stasjon[key] = {'osm_id': None, 'station_name': navn,
                                    'lat': float(lat), 'lon': float(lon),
                                    'bensin': None, 'bensin98': None,
                                    'diesel': None, 'updated': None}
        else:
            if sid in ugyldige:
                forkastet += 1
                continue
            key = sid
            if key not in per_stasjon:
                per_stasjon[key] = {'osm_id': sid, 'bensin': None, 'bensin98': None,
                                    'diesel': None, 'updated': None}

        fuel = r.get('fuel_type', '')
        pris = r.get('price')
        oppdatert = r.get('updated', '')
        if fuel == 'bensin95':
            per_stasjon[key]['bensin'] = pris
        elif fuel == 'bensin98':
            per_stasjon[key]['bensin98'] = pris
        elif fuel == 'diesel':
            per_stasjon[key]['diesel'] = pris
        if oppdatert and (not per_stasjon[key]['updated'] or oppdatert > per_stasjon[key]['updated']):
            per_stasjon[key]['updated'] = oppdatert

    # Slå opp OSM-id-er mot vår database
    osm_ids = [s['osm_id'] for s in per_stasjon.values() if s['osm_id']]
    match_map = finn_stasjoner_by_osm_ids(osm_ids)

    stasjoner = []
    for s in per_stasjon.values():
        if s['osm_id'] and s['osm_id'] in match_map:
            s['match'] = match_map[s['osm_id']]
        elif s['osm_id'] is None:
            # Prøv koordinat-matching med 150m radius
            naer = finn_naer_stasjon(s['lat'], s['lon'], maks_avstand_m=150)
            if naer:
                s['match'] = naer
            else:
                s['ukjent'] = True
        stasjoner.append(s)

    # Sorter: matchede nyeste først, ukjente sist
    stasjoner.sort(key=lambda s: (0 if s.get('match') else 1, s.get('updated') or ''), reverse=True)

    return jsonify({'stasjoner': stasjoner, 'forkastet': forkastet})


@admin_bp.route('/admin/import/godkjenn', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_import_godkjenn():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')
    bensin = data.get('bensin')
    diesel = data.get('diesel')
    bensin98 = data.get('bensin98')

    if not stasjon_id:
        return jsonify({'error': 'Mangler stasjon_id'}), 400

    if bensin is None and diesel is None and bensin98 is None:
        return jsonify({'error': 'Ingen priser å lagre'}), 400

    partner_id = hent_eller_opprett_partner('drivstoffnorge')
    lagre_pris(stasjon_id, bensin, diesel, bensin98, partner_id)
    return jsonify({'ok': True})


@admin_bp.route('/admin/import/opprett-stasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_import_opprett_stasjon():
    data = request.get_json(silent=True) or {}
    navn = (data.get('navn') or '').strip()
    kjede = (data.get('kjede') or '').strip() or None
    lat = data.get('lat')
    lon = data.get('lon')

    if not navn or lat is None or lon is None:
        return jsonify({'error': 'Mangler navn, lat eller lon'}), 400

    partner_id = hent_eller_opprett_partner('partner-import')
    stasjon_id, duplikat = opprett_stasjon(navn, kjede, float(lat), float(lon), partner_id)
    if duplikat:
        return jsonify({'stasjon_id': duplikat['id'], 'navn': duplikat['navn'], 'eksisterer': True})
    return jsonify({'stasjon_id': stasjon_id, 'navn': navn})


@admin_bp.route('/admin/toppliste')
@krever_innlogging
@krever_admin
def admin_toppliste():
    liste = hent_toppliste(limit=20)
    medaljer = ['&#127947;', '&#129352;', '&#129353;']
    rader = []
    for i, rad in enumerate(liste):
        plass = medaljer[i] if i < 3 else str(i + 1) + '.'
        if rad['kallenavn']:
            visningsnavn = rad['kallenavn']
            navn_stil = ''
        else:
            visningsnavn = f'Bruker #{rad["id"]}'
            navn_stil = ' style="color:#94a3b8;font-style:italic"'
        rader.append(
            f'<tr>'
            f'<td style="text-align:center;font-size:{"1.2rem" if i < 3 else "0.88rem"};width:2.5rem">{plass}</td>'
            f'<td{navn_stil}>{visningsnavn}</td>'
            f'<td style="text-align:right;font-weight:600;color:#3b82f6">{rad["antall"]}</td>'
            f'</tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="3" style="color:#94a3b8;text-align:center">Ingen registreringer ennå</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toppliste – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:480px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  p.info{{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
  td{{padding:10px 8px;border-bottom:1px solid #1f2937}}
  tr:last-child td{{border-bottom:none}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Toppliste</h1>
<p class="info">Alle brukere. Uten kallenavn vises som Bruker #id. Partnere ekskludert.</p>
<div class="kort">
  <table>{rader_html}</table>
</div>
</div></body></html>'''
