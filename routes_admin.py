"""Admin-ruter: brukeradministrasjon og prislogg."""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, request, session, redirect, jsonify

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from db import (finn_bruker_id, hent_alle_brukere, slett_bruker, har_rolle, sett_roller_bruker,
                opprett_invitasjon, hent_siste_prisoppdateringer,
                stasjoner_med_pris_koordinater, get_statistikk,
                antall_stasjoner_med_pris, antall_brukere,
                hent_brukerstasjoner, slett_stasjon,
                hent_innstilling, sett_innstilling,
                nye_brukere_per_time_48t, prisoppdateringer_per_time_48t,
                prisoppdateringer_rullende_24t_uke,
                hent_rapporter, antall_ubehandlede_rapporter,
                deaktiver_stasjon, reaktiver_stasjon,
                slett_rapporter_for_stasjon, hent_deaktiverte_stasjoner,
                hent_rapportorer_epost, finn_stasjoner_by_osm_ids,
                lagre_pris, hent_eller_opprett_partner, hent_toppliste, hent_toppliste_admin,
                sett_kjede_for_stasjon, finn_naer_stasjon, opprett_stasjon,
                hent_blogg_stats, finn_stasjoner_by_navn, endre_navn_stasjon,
                hent_endringsforslag, slett_endringsforslag, antall_ubehandlede_endringsforslag,
                hent_ventende_stasjoner, antall_ventende_stasjoner, godkjenn_stasjon,
                unike_enheter_per_dag)

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
        if not bruker or not har_rolle(bruker, 'admin'):
            return 'Ikke tilgang', 403
        return f(*args, **kwargs)
    return wrapper


def krever_moderator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        bruker = finn_bruker_id(session.get('bruker_id', 0))
        if not bruker or not (har_rolle(bruker, 'admin') or har_rolle(bruker, 'moderator')):
            return 'Ikke tilgang', 403
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route('/admin')
@krever_innlogging
@krever_moderator
def admin():
    bruker = finn_bruker_id(session.get('bruker_id', 0))
    er_admin = har_rolle(bruker, 'admin')
    rapporter_antall = antall_ubehandlede_rapporter()
    endringsforslag_antall = antall_ubehandlede_endringsforslag()
    deaktiverte_antall = len(hent_deaktiverte_stasjoner())
    ventende_antall = antall_ventende_stasjoner()
    if er_admin:
        brukere_antall = antall_brukere()
        stasjoner_antall = antall_stasjoner_med_pris()
        reg_stoppet = hent_innstilling('registrering_stoppet') == '1'
        reg_status = 'STOPPET' if reg_stoppet else 'Åpen'
        reg_farge = '#ef4444' if reg_stoppet else '#22c55e'
        reg_knapp = 'Stopp registrering' if not reg_stoppet else 'Åpne registrering'
        reg_verdi = '0' if reg_stoppet else '1'
        admin_tiles = f'''
  <a href="/admin/oversikt" class="tile">
    <div class="tile-ikon">&#128202;</div>
    <div class="tile-tittel">Statistikk</div>
    <div class="tile-info">Visninger og trender</div>
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
  <a href="/admin/brukere" class="tile">
    <div class="tile-ikon">&#128101;</div>
    <div class="tile-tittel">Brukere</div>
    <div class="tile-info">{brukere_antall} registrerte</div>
  </a>
  <a href="/admin/nyhet" class="tile">
    <div class="tile-ikon">&#128227;</div>
    <div class="tile-tittel">Nyhet</div>
    <div class="tile-info">Splash-melding</div>
  </a>
  <a href="/admin/endre-stasjon" class="tile">
    <div class="tile-ikon">&#9998;&#65039;</div>
    <div class="tile-tittel">Endre stasjon</div>
    <div class="tile-info">S&#248;k og endre navn</div>
  </a>'''
        reg_panel = f'''
<div class="admin-panel" style="margin-top:1.5rem">
  <h2>Registrering</h2>
  <div class="admin-rad">
    <span class="admin-status" style="color:{reg_farge}">&#9679; {reg_status}</span>
    <form method="post" action="/admin/toggle-registrering" style="margin:0">
      <input type="hidden" name="verdi" value="{reg_verdi}">
      <button class="admin-btn {'ok' if reg_stoppet else 'fare'}">{reg_knapp}</button>
    </form>
  </div>
</div>'''
    else:
        admin_tiles = ''
        reg_panel = ''
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
  <a href="/admin/prislogg" class="tile">
    <div class="tile-ikon">&#128176;</div>
    <div class="tile-tittel">Prislogg</div>
    <div class="tile-info">Siste prisoppdateringer</div>
  </a>
  <a href="/admin/steder" class="tile" {('style="border-color:#f59e0b"' if ventende_antall else '')}>
    <div class="tile-ikon">&#128205;</div>
    <div class="tile-tittel">Nye stasjoner</div>
    <div class="tile-info">{ventende_antall} venter godkjenning</div>
  </a>
  <a href="/admin/rapporter" class="tile" {('style="border-color:#f59e0b"' if rapporter_antall else '')}>
    <div class="tile-ikon">&#9888;&#65039;</div>
    <div class="tile-tittel">Rapporter</div>
    <div class="tile-info">{rapporter_antall} ubehandlede</div>
  </a>
  <a href="/admin/endringsforslag" class="tile" {('style="border-color:#f59e0b"' if endringsforslag_antall else '')}>
    <div class="tile-ikon">&#9999;&#65039;</div>
    <div class="tile-tittel">Endringsforslag</div>
    <div class="tile-info">{endringsforslag_antall} ubehandlede</div>
  </a>
  <a href="/admin/deaktiverte" class="tile">
    <div class="tile-ikon">&#128683;</div>
    <div class="tile-tittel">Deaktiverte</div>
    <div class="tile-info">{deaktiverte_antall} stasjoner</div>
  </a>
  <a href="/admin/toppliste" class="tile">
    <div class="tile-ikon">&#127942;</div>
    <div class="tile-tittel">Toppliste</div>
    <div class="tile-info">Topp 50 bidragsytere</div>
  </a>
{admin_tiles}
</div>
{reg_panel}
</div></body></html>'''


@admin_bp.route('/admin/brukere')
@krever_innlogging
@krever_admin
def admin_brukere():
    sok = request.args.get('sok', '').strip()
    side = request.args.get('side', 1, type=int)
    per_side = 50
    brukere, totalt = hent_alle_brukere(sok=sok, side=side, per_side=per_side)
    antall_sider = max(1, (totalt + per_side - 1) // per_side)
    side = max(1, min(side, antall_sider))

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

    # Paginering
    def side_url(s):
        if sok:
            return f'/admin/brukere?sok={sok}&side={s}'
        return f'/admin/brukere?side={s}'

    paginering = ''
    if antall_sider > 1:
        knapper = []
        if side > 1:
            knapper.append(f'<a href="{side_url(side-1)}" class="side-knapp">← Forrige</a>')
        for s in range(1, antall_sider + 1):
            if s == side:
                knapper.append(f'<span class="side-knapp aktiv">{s}</span>')
            elif abs(s - side) <= 2 or s == 1 or s == antall_sider:
                knapper.append(f'<a href="{side_url(s)}" class="side-knapp">{s}</a>')
            elif abs(s - side) == 3:
                knapper.append('<span style="color:#4b5563;padding:4px 2px">…</span>')
        if side < antall_sider:
            knapper.append(f'<a href="{side_url(side+1)}" class="side-knapp">Neste →</a>')
        paginering = f'<div class="paginering">{"".join(knapper)}</div>'

    sok_verdi = sok.replace('"', '&quot;')
    info = f'{totalt} bruker{"e" if totalt != 1 else ""}'
    if sok:
        info += f' for «{sok}»'

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brukere – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:1.5rem;color:#f1f5f9}}
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
  .sokfelt{{display:flex;gap:8px;margin-bottom:1rem}}
  .sokfelt input{{flex:1;background:#1f2937;border:1px solid #374151;border-radius:6px;
                  color:#e5e7eb;font-size:0.9rem;padding:8px 12px;outline:none}}
  .sokfelt input:focus{{border-color:#3b82f6}}
  .sokfelt button{{background:#374151;border:none;border-radius:6px;color:#e5e7eb;
                   font-size:0.9rem;padding:8px 14px;cursor:pointer}}
  .info-linje{{font-size:0.82rem;color:#6b7280;margin-bottom:0.75rem}}
  .paginering{{display:flex;gap:4px;flex-wrap:wrap;margin-top:1rem;align-items:center}}
  .side-knapp{{background:#1f2937;border:1px solid #374151;border-radius:5px;color:#94a3b8;
               font-size:0.82rem;padding:5px 10px;text-decoration:none;white-space:nowrap}}
  .side-knapp.aktiv{{background:#3b82f6;border-color:#3b82f6;color:white}}
  .side-knapp:hover:not(.aktiv){{background:#374151}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Brukere</h1>
<div class="kort">
  <form method="get" action="/admin/brukere" class="sokfelt">
    <input type="search" name="sok" value="{sok_verdi}" placeholder="Søk på brukernavn…" autofocus>
    <button type="submit">Søk</button>
  </form>
  <div class="info-linje">{info}</div>
  <table><tr><th>Brukernavn</th><th>Opprettet</th><th></th></tr>{bruker_rader}</table>
  {paginering}
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
@krever_moderator
def admin_steder():
    filter_valg = request.args.get('filter', 'idag')
    stasjoner = hent_ventende_stasjoner(filter_valg)
    ventende_totalt = antall_ventende_stasjoner()

    filter_tabs = ''
    for slug, label in [('idag', 'I dag'), ('alle', 'Alle')]:
        aktiv = 'color:#f1f5f9;border-color:#3b82f6' if filter_valg == slug else 'color:#94a3b8;border-color:transparent'
        filter_tabs += (
            f'<a href="/admin/steder?filter={slug}" '
            f'style="padding:6px 14px;border-bottom:2px solid;text-decoration:none;font-size:0.85rem;{aktiv}">'
            f'{label}</a>'
        )

    rader = []
    for s in stasjoner:
        bruker = s['kallenavn'] or s['brukernavn'] or '–'
        kjede = s['kjede'] or '–'
        tidspunkt = s['sist_oppdatert'][:16] if s['sist_oppdatert'] else '–'
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        godkjent = s['godkjent']
        status_badge = (
            '<span style="color:#22c55e;font-size:0.75rem">✓ godkjent</span>' if godkjent
            else '<span style="color:#f59e0b;font-size:0.75rem">⏳ venter</span>'
        )
        navn_escaped = s['navn'].replace("'", "\\'") if s['navn'] else ''

        rader.append(
            f'<tr>'
            f'<td>'
            f'  <a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none;font-weight:500">{s["navn"] or "?"}</a>'
            f'  <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px">{kjede} · {bruker} · {tidspunkt}</div>'
            f'</td>'
            f'<td style="white-space:nowrap">'
            f'  <form method="post" action="/admin/slett-stasjon" style="margin:0;display:inline"'
            f'    onsubmit="return confirm(\'Slette {navn_escaped}? Tilhørende priser slettes også.\')">'
            f'  <input type="hidden" name="stasjon_id" value="{s["id"]}">'
            f'  <input type="hidden" name="redirect" value="/admin/steder?filter={filter_valg}">'
            f'  <button class="btn-fare">Slett</button></form>'
            f'</td>'
            f'</tr>'
        )

    rader_html = ''.join(rader) or f'<tr><td colspan="3" style="color:#94a3b8;padding:1rem">Ingen stasjoner</td></tr>'

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Steder – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:800px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  .subtitle{{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}}
  .tabs{{display:flex;gap:0;border-bottom:1px solid #1f2937;margin-bottom:1.5rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;overflow:hidden}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:10px 12px;border-bottom:1px solid #1f2937;text-align:left;vertical-align:middle}}
  th{{color:#94a3b8;font-weight:500;font-size:0.8rem;background:#0f172a}}
  tr:last-child td{{border-bottom:none}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8;text-decoration:none}}
  .btn-ok{{background:transparent;border:1px solid #22c55e;color:#22c55e;font-size:0.75rem;padding:4px 10px;border-radius:4px;cursor:pointer}}
  .btn-ok:hover{{background:rgba(34,197,94,0.1)}}
  .btn-fare{{background:transparent;border:1px solid #ef4444;color:#ef4444;font-size:0.75rem;padding:4px 10px;border-radius:4px;cursor:pointer}}
  .btn-fare:hover{{background:rgba(239,68,68,0.1)}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Bruker-opprettede stasjoner</h1>
<p class="subtitle">{ventende_totalt} venter godkjenning</p>
<div class="tabs">{filter_tabs}</div>
<div class="kort">
  <table>
    <tr><th>Stasjon</th><th></th></tr>
    {rader_html}
  </table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/prislogg')
@krever_innlogging
@krever_moderator
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
    utloper = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
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
    tilbake = request.form.get('redirect', '/admin/steder')
    if stasjon_id:
        slett_stasjon(stasjon_id)
    return redirect(tilbake)


@admin_bp.route('/admin/godkjenn-stasjon', methods=['POST'])
@krever_innlogging
@krever_admin
def admin_godkjenn_stasjon():
    stasjon_id = request.form.get('stasjon_id', type=int)
    filter_valg = request.form.get('filter', 'ventende')
    if stasjon_id:
        godkjenn_stasjon(stasjon_id)
    return redirect(f'/admin/steder?filter={filter_valg}')


@admin_bp.route('/admin/endre-stasjon', methods=['GET', 'POST'])
@krever_innlogging
@krever_admin
def admin_endre_stasjon():
    melding = ''
    resultater = []
    sok = ''
    if request.method == 'POST':
        if 'sok' in request.form:
            sok = request.form.get('sok', '').strip()
            if sok:
                resultater = finn_stasjoner_by_navn(sok)
                if not resultater:
                    melding = f'Ingen stasjoner funnet for «{sok}».'
        elif 'stasjon_id' in request.form:
            stasjon_id = request.form.get('stasjon_id', type=int)
            nytt_navn = request.form.get('nytt_navn', '').strip()
            gammelt_navn = request.form.get('gammelt_navn', '').strip()
            sok = request.form.get('sok', '').strip()
            if stasjon_id and nytt_navn:
                ok = endre_navn_stasjon(stasjon_id, nytt_navn)
                if ok:
                    melding = f'✓ «{gammelt_navn}» ble omdøpt til «{nytt_navn}».'
                else:
                    melding = f'Feil: Fant ikke stasjon med id {stasjon_id}.'
            else:
                melding = 'Mangler stasjon-id eller nytt navn.'
            if sok:
                resultater = finn_stasjoner_by_navn(sok)

    resultat_rader = ''
    for s in resultater:
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        kjede_txt = f' ({s["kjede"]})' if s['kjede'] else ''
        resultat_rader += (
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">'
            f'{s["navn"]}{kjede_txt}</a></td>'
            f'<td>'
            f'<form method="post" style="display:flex;gap:6px;align-items:center;margin:0">'
            f'<input type="hidden" name="stasjon_id" value="{s["id"]}">'
            f'<input type="hidden" name="gammelt_navn" value="{s["navn"]}">'
            f'<input type="hidden" name="sok" value="{sok}">'
            f'<input type="text" name="nytt_navn" value="{s["navn"]}" required '
            f'style="background:#1f2937;border:1px solid #374151;border-radius:4px;'
            f'color:#e5e7eb;padding:4px 8px;font-size:0.82rem;flex:1;min-width:160px">'
            f'<button style="background:transparent;border:1px solid #3b82f6;color:#3b82f6;'
            f'font-size:0.75rem;padding:4px 10px;border-radius:4px;cursor:pointer;white-space:nowrap">'
            f'Lagre</button>'
            f'</form>'
            f'</td>'
            f'</tr>'
        )

    tabell_html = (
        f'<table><tr><th>Stasjon</th><th>Nytt navn</th></tr>{resultat_rader}</table>'
        if resultat_rader else ''
    )
    melding_html = (
        f'<p style="margin-bottom:1rem;color:{"#22c55e" if "✓" in melding else "#f59e0b"}">{melding}</p>'
        if melding else ''
    )

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Endre stasjon – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:700px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem;margin-top:1rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .sok-rad{{display:flex;gap:8px;align-items:center}}
  .sok-felt{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
             padding:8px 12px;font-size:0.9rem;flex:1}}
  .sok-btn{{background:transparent;border:1px solid #3b82f6;color:#3b82f6;
            font-size:0.85rem;padding:8px 16px;border-radius:6px;cursor:pointer;white-space:nowrap}}
</style></head><body><div class="container">
<nav><a href="/admin">&#8592; Admin</a></nav>
<h1>Endre stasjonsnavn</h1>
<div class="kort">
  <form method="post">
    <div class="sok-rad">
      <input class="sok-felt" type="text" name="sok" placeholder="S&#248;k etter stasjonsnavn..." value="{sok}" required>
      <button class="sok-btn" type="submit">S&#248;k</button>
    </div>
  </form>
  {melding_html}
  {tabell_html}
</div>
</div></body></html>'''


@admin_bp.route('/admin/rapporter')
@krever_innlogging
@krever_moderator
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


@admin_bp.route('/admin/endringsforslag')
@krever_innlogging
@krever_moderator
def admin_endringsforslag():
    forslag = hent_endringsforslag()
    rader = []
    for f in forslag:
        naavarende = f['navn'] + (f' ({f["kjede"]})' if f['kjede'] else '')
        kart_url = f'https://www.google.com/maps?q={f["lat"]},{f["lon"]}'
        dato = f['tidspunkt'][:10] if f['tidspunkt'] else '–'
        foreslatt_kjede = f['foreslatt_kjede'] or '–'
        foreslatt_navn = f['foreslatt_navn'] or '–'
        rader.append(
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{naavarende}</a></td>'
            f'<td style="color:#e5e7eb">{foreslatt_navn}</td>'
            f'<td style="color:#e5e7eb">{foreslatt_kjede}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{f["brukernavn"] or "–"}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{dato}</td>'
            f'<td style="display:flex;gap:6px;padding:6px 10px">'
            f'<form method="post" action="/admin/godkjenn-endringsforslag" style="margin:0">'
            f'<input type="hidden" name="forslag_id" value="{f["id"]}">'
            f'<input type="hidden" name="stasjon_id" value="{f["stasjon_id"]}">'
            f'<input type="hidden" name="foreslatt_navn" value="{f["foreslatt_navn"] or ""}">'
            f'<input type="hidden" name="foreslatt_kjede" value="{f["foreslatt_kjede"] or ""}">'
            f'<button style="background:transparent;border:1px solid #22c55e;color:#22c55e;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer">'
            f'Godkjenn</button></form>'
            f'<form method="post" action="/admin/avvis-endringsforslag" style="margin:0">'
            f'<input type="hidden" name="forslag_id" value="{f["id"]}">'
            f'<button style="background:transparent;border:1px solid #6b7280;color:#9ca3af;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer">'
            f'Avvis</button></form>'
            f'</td></tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="6" style="color:#94a3b8">Ingen endringsforslag</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Endringsforslag – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:900px;margin:0 auto}}
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
<h1>Endringsforslag fra brukere</h1>
<p class="info">Brukere har foreslått endringer i kjede eller navn. Godkjenn for å anvende, eller avvis for å slette.</p>
<div class="kort">
  <table><tr><th>Nåværende stasjon</th><th>Foreslått navn</th><th>Foreslått kjede</th><th>Bruker</th><th>Dato</th><th></th></tr>{rader_html}</table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/godkjenn-endringsforslag', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_godkjenn_endringsforslag():
    forslag_id = request.form.get('forslag_id', type=int)
    stasjon_id = request.form.get('stasjon_id', type=int)
    foreslatt_navn = request.form.get('foreslatt_navn', '').strip()
    foreslatt_kjede = request.form.get('foreslatt_kjede', '').strip()
    if stasjon_id:
        if foreslatt_navn:
            endre_navn_stasjon(stasjon_id, foreslatt_navn)
        if foreslatt_kjede:
            sett_kjede_for_stasjon(stasjon_id, foreslatt_kjede)
    if forslag_id:
        slett_endringsforslag(forslag_id)
    return redirect('/admin/endringsforslag')


@admin_bp.route('/admin/avvis-endringsforslag', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_avvis_endringsforslag():
    forslag_id = request.form.get('forslag_id', type=int)
    if forslag_id:
        slett_endringsforslag(forslag_id)
    return redirect('/admin/endringsforslag')


@admin_bp.route('/admin/deaktiverte')
@krever_innlogging
@krever_moderator
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
@krever_moderator
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
@krever_moderator
def admin_reaktiver_stasjon():
    stasjon_id = request.form.get('stasjon_id', type=int)
    if stasjon_id:
        reaktiver_stasjon(stasjon_id)
    return redirect('/admin/deaktiverte')


@admin_bp.route('/admin/sett-kjede', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_sett_kjede():
    data = request.get_json()
    stasjon_id = data.get('stasjon_id') if data else None
    kjede = data.get('kjede', '') if data else ''
    if not stasjon_id:
        return {'error': 'Mangler stasjon_id'}, 400
    sett_kjede_for_stasjon(int(stasjon_id), kjede)
    return {'ok': True}


@admin_bp.route('/admin/endre-navn', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_endre_navn():
    data = request.get_json()
    stasjon_id = data.get('stasjon_id') if data else None
    nytt_navn = (data.get('navn', '') if data else '').strip()
    if not stasjon_id or not nytt_navn:
        return {'error': 'Mangler stasjon_id eller navn'}, 400
    ok = endre_navn_stasjon(int(stasjon_id), nytt_navn)
    if not ok:
        return {'error': 'Stasjon ikke funnet'}, 404
    return {'ok': True, 'navn': nytt_navn}


@admin_bp.route('/admin/avvis-rapport', methods=['POST'])
@krever_innlogging
@krever_moderator
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


@admin_bp.route('/admin/api/priser-historikk')
@krever_innlogging
@krever_admin
def priser_historikk():
    from db import get_conn
    with get_conn() as conn:
        rader = conn.execute(
            "SELECT strftime('%Y-%m-%d', tidspunkt) as dato, COUNT(*) as antall "
            "FROM priser "
            "WHERE tidspunkt >= date('now', '-9 days') "
            "GROUP BY dato ORDER BY dato"
        ).fetchall()
    return jsonify([{'dato': r[0], 'antall': r[1]} for r in rader])


@admin_bp.route('/admin/oversikt')
@krever_innlogging
@krever_moderator
def oversikt():
    stats = get_statistikk()
    med_pris = antall_stasjoner_med_pris()
    brukere = antall_brukere()
    blogg_stats = hent_blogg_stats()
    blogg_totalt = sum(r['antall'] for r in blogg_stats)
    labels = [d for d, _ in stats['trend_30d']]
    values = [c for _, c in stats['trend_30d']]
    enheter_dag = unike_enheter_per_dag(30)
    enheter_labels = [r['dato'] for r in enheter_dag]
    enheter_values = [r['antall'] for r in enheter_dag]
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
    # Prisoppdateringer per time siste 24t
    # Rullende 24t-sum per time siste uke
    pris_uke = prisoppdateringer_rullende_24t_uke()
    pris_uke_labels = []
    pris_uke_values = []
    dag_navn = ['man', 'tir', 'ons', 'tor', 'fre', 'lør', 'søn']
    for ts, cnt in pris_uke:
        lokal = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(_oslo)
        if lokal.hour == 0:
            label = dag_navn[lokal.weekday()] + ' ' + lokal.strftime('%d.%m')
        else:
            label = ''
        pris_uke_labels.append(label)
        pris_uke_values.append(cnt)
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
    <h2>Unike enheter per dag – siste 30 dager</h2>
    <canvas id="enhetergraf" style="width:100%;max-height:240px"></canvas>
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
    <h2>Rullende 24t-sum – siste 10 dager</h2>
    <canvas id="prisukegraf" style="width:100%;max-height:220px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Prisoppdateringer per time – siste 48 timer</h2>
    <canvas id="prisgraf48" style="width:100%;max-height:220px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Prisregistreringer per dag – siste 10 dager <span id="historikk-oppdatert" style="font-size:0.75rem;color:#64748b;margin-left:0.5rem"></span></h2>
    <canvas id="historikkgraf" style="width:100%;max-height:220px"></canvas>
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
new Chart(document.getElementById('enhetergraf'), {{
  type: 'bar',
  data: {{
    labels: {enheter_labels},
    datasets: [{{ label: 'Unike enheter', data: {enheter_values},
      backgroundColor: 'rgba(20,184,166,0.6)',
      borderColor: 'rgba(20,184,166,1)', borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 45, color: '#94a3b8', font: {{ size: 10 }} }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
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
new Chart(document.getElementById('prisukegraf'), {{
  type: 'line',
  data: {{
    labels: {pris_uke_labels},
    datasets: [{{ label: 'Prisregistreringer (rullende 24t)', data: {pris_uke_values},
      borderColor: 'rgba(251,146,60,1)',
      backgroundColor: 'rgba(251,146,60,0.15)',
      borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 0, color: '#94a3b8', font: {{ size: 10 }}, autoSkip: false }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
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

// Prisregistreringer per dag – siste 10 dager (live)
const historikkChart = new Chart(document.getElementById('historikkgraf'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [{{ label: 'Registreringer', data: [],
    backgroundColor: 'rgba(251,146,60,0.6)',
    borderColor: 'rgba(251,146,60,1)', borderWidth: 1 }}] }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }}, grid: {{ color: '#1f2937' }} }},
      y: {{ beginAtZero: true, ticks: {{ stepSize: 1, color: '#94a3b8' }}, grid: {{ color: '#1f2937' }} }}
    }}
  }}
}});

function fyllInnDager(data, dager) {{
  const map = new Map(data.map(d => [d.dato, d.antall]));
  const result = [];
  for (let i = dager - 1; i >= 0; i--) {{
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - i);
    const dato = d.toISOString().slice(0, 10);
    result.push({{ dato, antall: map.get(dato) ?? 0 }});
  }}
  return result;
}}

async function oppdaterHistorikk() {{
  try {{
    const resp = await fetch('/admin/api/priser-historikk');
    if (!resp.ok) {{
      document.getElementById('historikk-oppdatert').textContent = `(HTTP ${{resp.status}})`;
      return;
    }}
    const raw = await resp.json();
    const data = fyllInnDager(raw, 10);
    historikkChart.data.labels = data.map(d => d.dato.slice(5).replace('-', '.'));
    historikkChart.data.datasets[0].data = data.map(d => d.antall);
    historikkChart.data.datasets[0].backgroundColor = data.map(d => {{
      return d.dato === new Date().toISOString().slice(0, 10)
        ? 'rgba(251,146,60,0.9)' : 'rgba(251,146,60,0.45)';
    }});
    historikkChart.update();
    const nå = new Date().toLocaleTimeString('no-NO', {{ hour: '2-digit', minute: '2-digit' }});
    document.getElementById('historikk-oppdatert').textContent = `(oppdatert ${{nå}})`;
  }} catch (e) {{
    document.getElementById('historikk-oppdatert').textContent = `(feil: ${{e.message}})`;
    console.warn('historikk-feil:', e);
  }}
}}

oppdaterHistorikk();
setInterval(oppdaterHistorikk, 60_000);
</script>
</body>
</html>'''


@admin_bp.route('/admin/kart')
@krever_innlogging
@krever_admin
def admin_kart():
    import json
    from datetime import datetime, timezone
    stasjoner = stasjoner_med_pris_koordinater()
    nå = datetime.now(timezone.utc)
    tell = {'fersk': 0, 'dagsgammel': 0, 'ny': 0, 'gammel': 0, 'gammel7': 0}
    for s in stasjoner:
        t = s.get('tidspunkt')
        if not t:
            tell['gammel7'] += 1
            continue
        try:
            ts = datetime.fromisoformat(t.replace(' ', 'T')).replace(tzinfo=timezone.utc)
            timer = (nå - ts).total_seconds() / 3600
        except Exception:
            tell['gammel7'] += 1
            continue
        if timer < 8:
            tell['fersk'] += 1
        elif timer < 24:
            tell['dagsgammel'] += 1
        elif timer < 48:
            tell['ny'] += 1
        elif timer < 168:
            tell['gammel'] += 1
        else:
            tell['gammel7'] += 1
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
  .legend span{{display:inline-flex;align-items:center;margin-right:1rem;cursor:pointer;user-select:none}}
  .legend span.inaktiv{{opacity:0.3;text-decoration:line-through}}
  .legend .dot{{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:0.4rem}}
</style></head><body>
<nav><a href="/admin">← Admin</a></nav>
<h1>Registrerte priser i Norge</h1>
<div class="info">{len(stasjoner)} stasjoner med pris</div>
<div class="legend">
  <span data-kat="fersk"><span class="dot" style="background:#22c55e"></span>&lt; 8 timer ({tell['fersk']})</span>
  <span data-kat="dagsgammel"><span class="dot" style="background:#a3e635"></span>8–24 timer ({tell['dagsgammel']})</span>
  <span data-kat="ny"><span class="dot" style="background:#facc15"></span>24–48 timer ({tell['ny']})</span>
  <span data-kat="gammel"><span class="dot" style="background:#4b5563"></span>2–7 dager ({tell['gammel']})</span>
  <span data-kat="gammel7"><span class="dot" style="background:#9ca3af"></span>&gt; 7 dager ({tell['gammel7']})</span>
</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const stasjoner = {json.dumps(stasjoner, ensure_ascii=False)};
const map = L.map('map').setView([63.4, 10.4], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap'
}}).addTo(map);
function prisFarge(tidspunkt) {{
  if (!tidspunkt) return '#9ca3af';
  const timer = (Date.now() - new Date(tidspunkt.replace(' ', 'T')).getTime()) / 3600000;
  if (timer < 8) return '#22c55e';
  if (timer < 24) return '#a3e635';
  if (timer < 48) return '#facc15';
  if (timer < 168) return '#4b5563';
  return '#9ca3af';
}}
function prisKat(tidspunkt) {{
  if (!tidspunkt) return 'gammel7';
  const timer = (Date.now() - new Date(tidspunkt.replace(' ', 'T')).getTime()) / 3600000;
  if (timer < 8) return 'fersk';
  if (timer < 24) return 'dagsgammel';
  if (timer < 48) return 'ny';
  if (timer < 168) return 'gammel';
  return 'gammel7';
}}
const markorer = {{}};
stasjoner.forEach(s => {{
  const priser = [
    s.bensin ? '95: ' + s.bensin.toFixed(2) : null,
    s.bensin98 ? '98: ' + s.bensin98.toFixed(2) : null,
    s.diesel ? 'Diesel: ' + s.diesel.toFixed(2) : null
  ].filter(Boolean).join('<br>');
  const dato = s.tidspunkt ? s.tidspunkt.slice(0, 10) : '';
  const farge = prisFarge(s.tidspunkt);
  const kat = prisKat(s.tidspunkt);
  const m = L.circleMarker([s.lat, s.lon], {{
    radius: 7, fillColor: farge, color: '#1e3a5f', weight: 1, fillOpacity: 0.8
  }}).bindPopup(
    '<b>' + s.navn + '</b>' + (s.kjede ? ' (' + s.kjede + ')' : '') +
    '<br>' + priser + '<br><span style="color:#888;font-size:0.8em">' + dato + '</span>'
  );
  if (kat === 'fersk') m.addTo(map);
  if (!markorer[kat]) markorer[kat] = [];
  markorer[kat].push(m);
}});
const ferskeBounds = (markorer['fersk'] || []).map(m => m.getLatLng());
if (ferskeBounds.length) {{
  map.fitBounds(L.latLngBounds(ferskeBounds), {{ padding: [30, 30] }});
}} else if (stasjoner.length) {{
  map.fitBounds(L.latLngBounds(stasjoner.map(s => [s.lat, s.lon])), {{ padding: [30, 30] }});
}}
document.querySelectorAll('.legend span[data-kat]').forEach(el => {{
  if (el.dataset.kat !== 'fersk') el.classList.add('inaktiv');
  el.addEventListener('click', () => {{
    const kat = el.dataset.kat;
    const aktiv = !el.classList.contains('inaktiv');
    el.classList.toggle('inaktiv', aktiv);
    (markorer[kat] || []).forEach(m => aktiv ? map.removeLayer(m) : map.addLayer(m));
  }});
}});
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
    liste = hent_toppliste_admin(limit=50)
    medaljer = ['&#127947;', '&#129352;', '&#129353;']
    rader = []
    for i, rad in enumerate(liste):
        plass = medaljer[i] if i < 3 else str(i + 1) + '.'
        brukernavn = rad['brukernavn'] or ''
        kallenavn = rad['kallenavn'] or ''
        navnlinje = f'<span style="font-size:0.78rem;color:#94a3b8">{brukernavn}</span>'
        kallenavnlinje = f'<br><span style="font-size:0.78rem;color:#64748b">@{kallenavn}</span>' if kallenavn else ''
        rader.append(
            f'<tr>'
            f'<td style="text-align:center;font-size:{"1.2rem" if i < 3 else "0.88rem"};width:2.5rem">{plass}</td>'
            f'<td>{navnlinje}{kallenavnlinje}</td>'
            f'<td style="text-align:right;font-weight:600;color:#3b82f6;white-space:nowrap">{rad["antall"]}</td>'
            f'</tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="3" style="color:#94a3b8;text-align:center">Ingen registreringer ennå</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toppliste – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:560px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  p.info{{font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
  td{{padding:10px 8px;border-bottom:1px solid #1f2937;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Toppliste</h1>
<p class="info">Topp 50 bidragsytere. Partnere ekskludert.</p>
<div class="kort">
  <table>{rader_html}</table>
</div>
</div></body></html>'''
