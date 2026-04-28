"""Admin-ruter: brukeradministrasjon og prislogg."""

import html
import json
import math
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import httpx
from flask import Blueprint, request, session, redirect, jsonify

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from db import (finn_bruker_id, hent_alle_brukere, slett_bruker, har_rolle, sett_roller_bruker,
                opprett_invitasjon, hent_siste_prisoppdateringer, slett_pris,
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
                unike_enheter_per_dag, sett_drivstofftyper)

admin_bp = Blueprint('admin', __name__)

# ── Regiondefinisjoner for analysekart ──────────────────────────────────────
REGIONER_RECT = [
    ("Bergen",              "#2196F3", 60.10, 60.88, 4.70, 5.75),
    ("Haugalandet",         "#9C27B0", 59.08, 59.65, 5.05, 5.60),
    ("Stavanger",           "#E91E63", 58.75, 59.15, 5.40, 6.05),
    ("Grenland",            "#FF5722", 58.95, 59.40, 9.35, 9.90),
    ("Kongsberg",           "#795548", 59.55, 59.80, 9.50, 9.85),
    ("Drammen",             "#607D8B", 59.55, 59.85, 10.00, 10.40),
    ("Oslo",                "#F44336", 59.75, 60.05, 10.35, 11.00),
    ("Romerike/Akershus",   "#FF9800", 59.85, 60.20, 10.80, 11.20),
    ("Fredrikstad/Østfold", "#4CAF50", 59.05, 59.45, 10.80, 11.35),
    ("Vestfold",            "#00BCD4", 59.10, 59.55, 10.15, 10.55),
    ("Kristiansand",        "#8BC34A", 57.95, 58.25, 7.75, 8.20),
    ("Trondheim",           "#3F51B5", 63.25, 63.55, 10.10, 10.70),
    ("Bodø/Nordland",       "#009688", 67.10, 67.45, 14.25, 14.70),
    ("Tromsø/Troms",        "#673AB7", 69.45, 69.80, 18.70, 19.30),
]

MORE_POLYGON = [
    [62.05, 5.05], [62.20, 5.20], [62.47, 5.55], [62.60, 6.00],
    [62.85, 6.60], [63.08, 7.75], [63.12, 8.05], [63.20, 8.80],
    [63.00, 9.10], [62.75, 9.40], [62.45, 9.20], [62.20, 9.00],
    [62.00, 8.40], [62.00, 7.20], [61.90, 6.50], [61.95, 5.80],
    [62.05, 5.05],
]


def _punkt_i_polygon(lat, lon, polygon):
    """Ray casting – avgjør om (lat, lon) er innenfor polygon [[lat,lon],...]."""
    n = len(polygon)
    inni = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inni = not inni
        j = i
    return inni


def _region_for(lat, lon):
    if lat is None or lon is None:
        return "Ukjent"
    for navn, _, lat_min, lat_max, lon_min, lon_max in REGIONER_RECT:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return navn
    if _punkt_i_polygon(lat, lon, MORE_POLYGON):
        return "Møre og Romsdal"
    return "Annet"


def _send_forslag_svar(epost: str, brukernavn: str, stasjonsnavn: str, godkjent: bool, ekstra: str = ''):
    """Send svar til bruker om endringsforslag er godkjent eller avvist."""
    if not epost:
        return
    import resend
    import logging
    if godkjent:
        overskrift = 'Forslaget ditt er godkjent!'
        ingress = (f'Vi har oppdatert <strong>{stasjonsnavn}</strong> basert på forslaget ditt. '
                   f'Takk for at du hjelper oss med å holde dataene nøyaktige!')
    else:
        overskrift = 'Forslaget ditt er gjennomgått'
        ingress = (f'Vi har sett på forslaget ditt for <strong>{stasjonsnavn}</strong>, '
                   f'men valgte ikke å gjøre endringer denne gangen.')
    ekstra_html = f'<p>{ekstra}</p>' if ekstra else ''
    try:
        resend.Emails.send({
            'from': 'Drivstoffpriser <noreply@ksalo.no>',
            'to': epost,
            'subject': overskrift,
            'html': (f'<p>Hei{(" " + brukernavn) if brukernavn else ""}!</p>'
                     f'<p>{ingress}</p>'
                     f'{ekstra_html}'
                     f'<p>Mvh,<br>Drivstoffpriser</p>'),
        })
    except Exception as e:
        logging.getLogger('drivstoff').error(f'Forslag-svar til {epost} feilet: {e}')


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


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _punkt_til_segment_m(lat, lon, a, b):
    """Omtrentlig avstand fra punkt til rutesegment, god nok for admin-prototype."""
    lat0 = math.radians((lat + a[0] + b[0]) / 3)
    meter_per_lat = 111_320
    meter_per_lon = 111_320 * max(math.cos(lat0), 0.01)
    px, py = lon * meter_per_lon, lat * meter_per_lat
    ax, ay = a[1] * meter_per_lon, a[0] * meter_per_lat
    bx, by = b[1] * meter_per_lon, b[0] * meter_per_lat
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    nx, ny = ax + t * dx, ay + t * dy
    return math.hypot(px - nx, py - ny)


def _geokod_sted(q: str):
    if q.startswith('pos:'):
        deler = q[4:].split(',')
        if len(deler) == 2:
            try:
                lat, lon = float(deler[0]), float(deler[1])
                if 57 <= lat <= 72 and 4 <= lon <= 32:
                    return {'navn': 'Min posisjon', 'lat': lat, 'lon': lon}
            except ValueError:
                pass

    resp = httpx.get(
        'https://photon.komoot.io/api/',
        params={'q': q, 'limit': 1, 'bbox': '4.0,57.0,31.5,71.5'},
        headers={'User-Agent': 'drivstoffpriser/1.0 admin-rutepris'},
        timeout=8,
    )
    resp.raise_for_status()
    for f in resp.json().get('features', []):
        props = f.get('properties', {})
        if props.get('countrycode', '').upper() != 'NO':
            continue
        coords = f.get('geometry', {}).get('coordinates', [])
        if len(coords) >= 2:
            deler = [props.get(k) for k in ('name', 'county', 'state') if props.get(k)]
            return {'navn': ', '.join(dict.fromkeys(deler)) or q, 'lat': float(coords[1]), 'lon': float(coords[0])}
    return None


def _hent_osrm_rute(fra, til):
    resp = httpx.get(
        f'https://router.project-osrm.org/route/v1/driving/{fra["lon"]},{fra["lat"]};{til["lon"]},{til["lat"]}',
        params={'overview': 'full', 'geometries': 'geojson', 'alternatives': 'false', 'steps': 'false'},
        headers={'User-Agent': 'drivstoffpriser/1.0 admin-rutepris'},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    routes = data.get('routes') or []
    if not routes:
        return None
    coords = routes[0].get('geometry', {}).get('coordinates', [])
    punkter = [(float(lat), float(lon)) for lon, lat in coords]
    return {'punkter': punkter, 'km': routes[0].get('distance', 0) / 1000, 'min': routes[0].get('duration', 0) / 60}


def _finn_billige_langs_rute(rute, drivstoff: str, maks_avvik_km: float, limit: int = 25):
    stasjoner = stasjoner_med_pris_koordinater()
    punkter = rute['punkter']
    if len(punkter) < 2:
        return []
    margin = maks_avvik_km / 111
    min_lat = min(p[0] for p in punkter) - margin
    max_lat = max(p[0] for p in punkter) + margin
    min_lon = min(p[1] for p in punkter) - margin
    max_lon = max(p[1] for p in punkter) + margin
    kandidater = []
    for s in stasjoner:
        pris = s.get(drivstoff)
        if pris is None or pris <= 0:
            continue
        if not (min_lat <= s['lat'] <= max_lat and min_lon <= s['lon'] <= max_lon):
            continue
        avstand = min(_punkt_til_segment_m(s['lat'], s['lon'], punkter[i], punkter[i + 1]) for i in range(len(punkter) - 1))
        if avstand <= maks_avvik_km * 1000:
            kandidater.append({**s, 'pris': pris, 'avvik_m': round(avstand)})
    kandidater.sort(key=lambda s: (s['pris'], s['avvik_m']))
    return kandidater[:limit]


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
  <a href="/admin/rutepris" class="tile">
    <div class="tile-ikon">&#128663;</div>
    <div class="tile-tittel">Billigst p&#229; vei</div>
    <div class="tile-info">Finn pris langs rute</div>
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

  <a href="/admin/innstillinger" class="tile">
    <div class="tile-ikon">&#9881;&#65039;</div>
    <div class="tile-tittel">Innstillinger</div>
    <div class="tile-info">Toggles og funksjoner</div>
  </a>'''
    else:
        admin_tiles = ''
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
  <a href="/admin/drivstofftyper" class="tile">
    <div class="tile-ikon">&#9981;</div>
    <div class="tile-tittel">Drivstofftyper</div>
    <div class="tile-info">Aktiver/deaktiver per stasjon</div>
  </a>
  <a href="/admin/ocr-bilder" class="tile">
    <div class="tile-ikon">&#128247;</div>
    <div class="tile-tittel">OCR-bilder</div>
    <div class="tile-info">Bilder, AI-resultat og fasit</div>
  </a>
{admin_tiles}
</div>
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
            stasjon = f'<a href="https://www.openstreetmap.org/?mlat={p["lat"]}&mlon={p["lon"]}&zoom=17" target="_blank" rel="noopener" style="color:#e5e7eb">{stasjon_tekst}</a>'
        else:
            stasjon = stasjon_tekst
        rader.append(
            f'<tr id="rad-{p["id"]}">'
            f'<td style="color:#94a3b8;font-size:0.78rem">{tidspunkt}</td>'
            f'<td>{stasjon}</td>'
            f'<td style="color:#93c5fd">{bruker}</td>'
            f'<td style="text-align:right">{fmt(p["bensin"])}</td>'
            f'<td style="text-align:right">{fmt(p["bensin98"])}</td>'
            f'<td style="text-align:right">{fmt(p["diesel"])}</td>'
            f'<td style="text-align:center">'
            f'<button class="slett-btn" data-id="{p["id"]}" aria-label="Slett rad">✕</button>'
            f'</td>'
            f'</tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="7" style="color:#94a3b8;text-align:center">Ingen prisoppdateringer</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prislogg – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:960px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:0.85rem}}
  td,th{{padding:7px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .slett-btn{{background:none;border:none;color:#6b7280;cursor:pointer;font-size:0.9rem;padding:2px 6px;border-radius:4px}}
  .slett-btn:hover{{color:#ef4444;background:rgba(239,68,68,0.1)}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Prislogg (siste 200)</h1>
<div class="kort">
  <table>
    <tr><th>Tidspunkt</th><th>Stasjon</th><th>Bruker</th><th style="text-align:right">95</th><th style="text-align:right">98</th><th style="text-align:right">Diesel</th><th></th></tr>
    {rader_html}
  </table>
</div>
</div>
<script>
document.querySelectorAll('.slett-btn').forEach(btn => {{
  btn.addEventListener('click', async () => {{
    const id = btn.dataset.id;
    if (!confirm('Slett denne prisoppdateringen?')) return;
    const resp = await fetch(`/admin/prislogg/${{id}}`, {{ method: 'DELETE' }});
    if (resp.ok) {{
      document.getElementById(`rad-${{id}}`).remove();
    }} else {{
      alert('Sletting feilet');
    }}
  }});
}});
</script>
</body></html>'''


@admin_bp.route('/admin/prislogg/<int:pris_id>', methods=['DELETE'])
@krever_innlogging
@krever_moderator
def slett_prislogg_rad(pris_id):
    if slett_pris(pris_id):
        return '', 204
    return jsonify({'error': 'Ikke funnet'}), 404


@admin_bp.route('/admin/toggle-registrering', methods=['POST'])
@krever_innlogging
@krever_admin
def toggle_registrering():
    verdi = request.form.get('verdi', '0')
    sett_innstilling('registrering_stoppet', '1' if verdi == '1' else '0')
    return redirect('/admin/innstillinger')


@admin_bp.route('/admin/toggle', methods=['POST'])
@krever_innlogging
@krever_admin
def toggle_innstilling():
    noekkel = request.form.get('noekkel', '').strip()
    verdi = request.form.get('verdi', '0')
    _tillatte = {'registrering_stoppet', 'anonym_innlegging'}
    if noekkel not in _tillatte:
        return jsonify({'error': 'Ukjent innstilling'}), 400
    sett_innstilling(noekkel, '1' if verdi == '1' else '0')
    return redirect('/admin/innstillinger')


@admin_bp.route('/admin/innstillinger')
@krever_innlogging
@krever_admin
def admin_innstillinger():
    def toggle_panel(noekkel, tittel, beskrivelse, aktiv_tekst, inaktiv_tekst, fare_ved_aktiv=False):
        pa = hent_innstilling(noekkel) == '1'
        status_tekst = aktiv_tekst if pa else inaktiv_tekst
        status_farge = '#ef4444' if (pa and fare_ved_aktiv) else ('#22c55e' if pa else '#94a3b8')
        knapp_tekst = f'Deaktiver' if pa else 'Aktiver'
        knapp_klasse = 'fare' if pa else 'ok'
        ny_verdi = '0' if pa else '1'
        return f'''
<div class="innst-panel">
  <div class="innst-hode">
    <div>
      <div class="innst-tittel">{tittel}</div>
      <div class="innst-besk">{beskrivelse}</div>
    </div>
    <div class="innst-hoeyre">
      <span class="admin-status" style="color:{status_farge}">&#9679; {status_tekst}</span>
      <form method="post" action="/admin/toggle" style="margin:0">
        <input type="hidden" name="noekkel" value="{noekkel}">
        <input type="hidden" name="verdi" value="{ny_verdi}">
        <button class="admin-btn {knapp_klasse}">{knapp_tekst}</button>
      </form>
    </div>
  </div>
</div>'''

    paneler = ''
    paneler += toggle_panel(
        'registrering_stoppet',
        'Brukerregistrering',
        'Tillat nye brukere &#229; registrere seg p&#229; drivstoffprisene.no.',
        'STOPPET', '&#197;pen', fare_ved_aktiv=True
    )
    paneler += toggle_panel(
        'anonym_innlegging',
        'Anonym prisinnlegging',
        'La ikke-innloggede brukere legge inn priser. Maks 10 per time per IP-adresse.',
        'P&#229;', 'Av', fare_ved_aktiv=False
    )

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Innstillinger – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:640px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:2rem;color:#f1f5f9}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .innst-panel{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:1.25rem;margin-bottom:1rem}}
  .innst-hode{{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem}}
  .innst-tittel{{font-size:0.95rem;font-weight:600;color:#f1f5f9;margin-bottom:0.25rem}}
  .innst-besk{{font-size:0.8rem;color:#94a3b8;max-width:340px}}
  .innst-hoeyre{{display:flex;align-items:center;gap:0.75rem;flex-shrink:0}}
  .admin-status{{font-size:0.85rem;font-weight:600;white-space:nowrap}}
  .admin-btn{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
              font-size:0.82rem;padding:8px 14px;cursor:pointer;transition:background 0.15s;white-space:nowrap}}
  .admin-btn:hover{{background:#374151}}
  .admin-btn.fare{{border-color:#ef4444;color:#ef4444}}
  .admin-btn.fare:hover{{background:rgba(239,68,68,0.15)}}
  .admin-btn.ok{{border-color:#22c55e;color:#22c55e}}
  .admin-btn.ok:hover{{background:rgba(34,197,94,0.15)}}
</style></head><body><div class="container">
<nav><a href="/admin">&#8592; Admin</a></nav>
<h1>Innstillinger</h1>
{paneler}
</div></body></html>'''


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


@admin_bp.route('/admin/drivstofftyper', methods=['GET', 'POST'])
@krever_innlogging
@krever_moderator
def admin_drivstofftyper():
    melding = ''
    resultater = []
    sok = ''
    stasjon = None

    if request.method == 'POST':
        if 'stasjon_id' in request.form and 'lagre' in request.form:
            stasjon_id = request.form.get('stasjon_id', type=int)
            sok = request.form.get('sok', '').strip()
            har_bensin = 'har_bensin' in request.form
            har_bensin98 = 'har_bensin98' in request.form
            har_diesel = 'har_diesel' in request.form
            har_diesel_avgiftsfri = 'har_diesel_avgiftsfri' in request.form
            sett_drivstofftyper(stasjon_id, har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri)
            melding = f'✓ Drivstofftyper oppdatert for stasjon {stasjon_id}.'
            if sok:
                resultater = finn_stasjoner_by_navn(sok)
        elif 'sok' in request.form:
            sok = request.form.get('sok', '').strip()
            if sok:
                resultater = finn_stasjoner_by_navn(sok)
                if not resultater:
                    melding = f'Ingen stasjoner funnet for «{sok}».'

    def checked(v):
        return 'checked' if v else ''

    resultat_rader = ''
    for s in resultater:
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        kjede_txt = f' ({s["kjede"]})' if s.get('kjede') else ''
        har_b   = s.get('har_bensin', 1)
        har_b98 = s.get('har_bensin98', 1)
        har_d   = s.get('har_diesel', 1)
        har_daf = s.get('har_diesel_avgiftsfri', 1)
        resultat_rader += f'''
<tr>
  <td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{s["navn"]}{kjede_txt}</a></td>
  <td>
    <form method="post" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:0">
      <input type="hidden" name="stasjon_id" value="{s['id']}">
      <input type="hidden" name="lagre" value="1">
      <input type="hidden" name="sok" value="{sok}">
      <label style="display:flex;gap:4px;align-items:center;font-size:0.82rem">
        <input type="checkbox" name="har_bensin" {checked(har_b)}> 95
      </label>
      <label style="display:flex;gap:4px;align-items:center;font-size:0.82rem">
        <input type="checkbox" name="har_bensin98" {checked(har_b98)}> 98
      </label>
      <label style="display:flex;gap:4px;align-items:center;font-size:0.82rem">
        <input type="checkbox" name="har_diesel" {checked(har_d)}> Diesel
      </label>
      <label style="display:flex;gap:4px;align-items:center;font-size:0.82rem">
        <input type="checkbox" name="har_diesel_avgiftsfri" {checked(har_daf)}> Avg.fri
      </label>
      <button style="background:transparent;border:1px solid #3b82f6;color:#3b82f6;
        font-size:0.75rem;padding:4px 10px;border-radius:4px;cursor:pointer">Lagre</button>
    </form>
  </td>
</tr>'''

    tabell_html = (
        f'<table><tr><th>Stasjon</th><th>Drivstofftyper</th></tr>{resultat_rader}</table>'
        if resultat_rader else ''
    )
    melding_html = (
        f'<p style="margin-bottom:1rem;color:{"#22c55e" if "✓" in melding else "#f59e0b"}">{melding}</p>'
        if melding else ''
    )

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drivstofftyper – Admin</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:800px;margin:0 auto}}
  h1{{font-size:1.3rem;margin-bottom:0.5rem;color:#f1f5f9}}
  p.ingress{{color:#94a3b8;font-size:0.85rem;margin-bottom:2rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem;margin-top:1rem}}
  td,th{{padding:8px 10px;border-bottom:1px solid #1f2937;text-align:left;vertical-align:middle}}
  th{{color:#94a3b8;font-weight:500}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a{{color:#94a3b8}}
  .sok-rad{{display:flex;gap:8px;align-items:center}}
  .sok-felt{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
             padding:8px 12px;font-size:0.9rem;flex:1}}
  .sok-btn{{background:transparent;border:1px solid #3b82f6;color:#3b82f6;
            font-size:0.85rem;padding:8px 16px;border-radius:6px;cursor:pointer;white-space:nowrap}}
  input[type=checkbox]{{width:16px;height:16px;cursor:pointer}}
</style></head><body><div class="container">
<nav><a href="/admin">&#8592; Admin</a></nav>
<h1>Drivstofftyper per stasjon</h1>
<p class="ingress">Fjern haken for drivstofftyper stasjonen ikke tilbyr. Brukere vil ikke se disse feltene når de registrerer pris.</p>
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
        kart_url = f'https://www.openstreetmap.org/?mlat={f["lat"]}&mlon={f["lon"]}&zoom=17'
        dato = f['tidspunkt'][:10] if f['tidspunkt'] else '–'
        foreslatt_kjede = f['foreslatt_kjede'] or '–'
        foreslatt_navn = f['foreslatt_navn'] or '–'
        kommentar_html = f'<span style="color:#fbbf24">{f["kommentar"]}</span>' if f.get('kommentar') else '–'
        har_epost = bool(f.get('bruker_id') and f.get('brukernavn') and '@' in (f.get('brukernavn') or ''))
        epost_hint = '' if har_epost else ' title="Anonym bruker – ingen e-post sendes"'
        rader.append(
            f'<tr>'
            f'<td><a href="{kart_url}" target="_blank" style="color:#93c5fd;text-decoration:none">{naavarende}</a></td>'
            f'<td style="color:#e5e7eb">{foreslatt_navn}</td>'
            f'<td style="color:#e5e7eb">{foreslatt_kjede}</td>'
            f'<td style="color:#e5e7eb;max-width:200px;word-break:break-word">{kommentar_html}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{f["brukernavn"] or "–"}</td>'
            f'<td style="color:#94a3b8;font-size:0.78rem">{dato}</td>'
            f'<td style="padding:6px 10px">'
            f'<form method="post" action="/admin/godkjenn-endringsforslag" style="margin:0 0 6px 0">'
            f'<input type="hidden" name="forslag_id" value="{f["id"]}">'
            f'<input type="hidden" name="stasjon_id" value="{f["stasjon_id"]}">'
            f'<input type="hidden" name="foreslatt_navn" value="{f["foreslatt_navn"] or ""}">'
            f'<input type="hidden" name="foreslatt_kjede" value="{f["foreslatt_kjede"] or ""}">'
            f'<input type="hidden" name="bruker_id" value="{f["bruker_id"] or ""}">'
            f'<input type="hidden" name="stasjon_navn" value="{naavarende}">'
            f'<input type="text" name="ekstra_melding" placeholder="Tilleggsmelding (valgfritt)" {epost_hint}'
            f' style="width:180px;font-size:0.75rem;padding:3px 6px;border-radius:4px;'
            f'background:#1f2937;border:1px solid #374151;color:#e5e7eb;margin-bottom:4px">'
            f'<button style="background:transparent;border:1px solid #22c55e;color:#22c55e;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer;display:block">'
            f'Godkjenn{"" if har_epost else " (ingen epost)"}</button></form>'
            f'<form method="post" action="/admin/avvis-endringsforslag" style="margin:0">'
            f'<input type="hidden" name="forslag_id" value="{f["id"]}">'
            f'<input type="hidden" name="bruker_id" value="{f["bruker_id"] or ""}">'
            f'<input type="hidden" name="stasjon_navn" value="{naavarende}">'
            f'<input type="text" name="ekstra_melding" placeholder="Begrunnelse (valgfritt)" {epost_hint}'
            f' style="width:180px;font-size:0.75rem;padding:3px 6px;border-radius:4px;'
            f'background:#1f2937;border:1px solid #374151;color:#e5e7eb;margin-bottom:4px">'
            f'<button style="background:transparent;border:1px solid #6b7280;color:#9ca3af;'
            f'font-size:0.75rem;padding:3px 8px;border-radius:4px;cursor:pointer;display:block">'
            f'Avvis{"" if har_epost else " (ingen epost)"}</button></form>'
            f'</td></tr>'
        )
    rader_html = ''.join(rader) or '<tr><td colspan="7" style="color:#94a3b8">Ingen endringsforslag</td></tr>'
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
  <table><tr><th>Nåværende stasjon</th><th>Foreslått navn</th><th>Foreslått kjede</th><th>Kommentar</th><th>Bruker</th><th>Dato</th><th></th></tr>{rader_html}</table>
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
    bruker_id = request.form.get('bruker_id', type=int)
    stasjon_navn = request.form.get('stasjon_navn', '').strip()
    ekstra_melding = request.form.get('ekstra_melding', '').strip()
    if stasjon_id:
        if foreslatt_navn:
            endre_navn_stasjon(stasjon_id, foreslatt_navn)
        if foreslatt_kjede:
            sett_kjede_for_stasjon(stasjon_id, foreslatt_kjede)
    if bruker_id:
        bruker = finn_bruker_id(bruker_id)
        if bruker and bruker.get('brukernavn') and '@' in bruker['brukernavn']:
            _send_forslag_svar(bruker['brukernavn'], bruker.get('kallenavn') or '', stasjon_navn, godkjent=True, ekstra=ekstra_melding)
    if forslag_id:
        slett_endringsforslag(forslag_id)
    return redirect('/admin/endringsforslag')


@admin_bp.route('/admin/avvis-endringsforslag', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_avvis_endringsforslag():
    forslag_id = request.form.get('forslag_id', type=int)
    bruker_id = request.form.get('bruker_id', type=int)
    stasjon_navn = request.form.get('stasjon_navn', '').strip()
    ekstra_melding = request.form.get('ekstra_melding', '').strip()
    if bruker_id:
        bruker = finn_bruker_id(bruker_id)
        if bruker and bruker.get('brukernavn') and '@' in bruker['brukernavn']:
            _send_forslag_svar(bruker['brukernavn'], bruker.get('kallenavn') or '', stasjon_navn, godkjent=False, ekstra=ekstra_melding)
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


@admin_bp.route('/admin/sett-drivstofftyper', methods=['POST'])
@krever_innlogging
@krever_moderator
def admin_sett_drivstofftyper_json():
    data = request.get_json()
    stasjon_id = data.get('stasjon_id') if data else None
    if not stasjon_id:
        return {'error': 'Mangler stasjon_id'}, 400
    sett_drivstofftyper(
        int(stasjon_id),
        bool(data.get('har_bensin', True)),
        bool(data.get('har_bensin98', True)),
        bool(data.get('har_diesel', True)),
        bool(data.get('har_diesel_avgiftsfri', True)),
    )
    return {'ok': True}


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
        elif action == 'toggle_personlig':
            gjeldende = hent_innstilling('personlig_splash', '')
            sett_innstilling('personlig_splash', '' if gjeldende == '1' else '1')
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

    personlig_aktiv = hent_innstilling('personlig_splash', '') == '1'

    personlig_html = f'''
    <div class="kort" style="border-color:{'#8b5cf6' if personlig_aktiv else '#374151'}">
      <h2 style="color:{'#8b5cf6' if personlig_aktiv else '#94a3b8'}">Personaliserte ukemeldinger {'✓ Aktiv' if personlig_aktiv else '○ Av'}</h2>
      <p style="font-size:0.82rem;color:#94a3b8;margin-bottom:12px">Viser tilpassede splash-meldinger basert på brukerens aktivitet siste 7 dager. Vises maks én gang per uke. Admin-nyheter trumfer alltid.</p>
      <details style="margin-bottom:12px">
        <summary style="font-size:0.82rem;color:#64748b;cursor:pointer">Vis meldingsvarianter</summary>
        <div style="font-size:0.8rem;color:#94a3b8;margin-top:8px;line-height:1.6">
          <p><strong style="color:#e5e7eb">Ikke innlogget:</strong> Oppfordring til å opprette bruker</p>
          <p><strong style="color:#e5e7eb">0 bidrag:</strong> Vennlig oppfordring til å legge inn priser</p>
          <p><strong style="color:#e5e7eb">1–19 bidrag:</strong> Takk med personlig antall</p>
          <p><strong style="color:#e5e7eb">20+ bidrag:</strong> Ekstra anerkjennelse for superbrukere</p>
        </div>
      </details>
      <form method="post" style="margin:0">
        <input type="hidden" name="action" value="toggle_personlig">
        <button class="admin-btn" style="border-color:#8b5cf6;color:#8b5cf6">{'Slå av' if personlig_aktiv else 'Slå på'}</button>
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
{personlig_html}
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
            "WHERE tidspunkt >= date('now', '-19 days') "
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
    labels = [d for d, _ in stats['trend_14d']]
    values = [c for _, c in stats['trend_14d']]
    enheter_dag = unike_enheter_per_dag(14)
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
    <h2>Sidevisninger siste 14 dager</h2>
    <canvas id="graf" style="width:100%;max-height:240px"></canvas>
  </div>
  <div class="seksjon">
    <h2>Unike enheter per dag – siste 14 dager</h2>
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
    <h2>Prisregistreringer per dag – siste 20 dager <span id="historikk-oppdatert" style="font-size:0.75rem;color:#64748b;margin-left:0.5rem"></span></h2>
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

// Prisregistreringer per dag – siste 20 dager (live)
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
    const data = fyllInnDager(raw, 20);
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
    region_tell_24t = {}
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
        if timer < 24:
            reg = _region_for(s.get('lat'), s.get('lon'))
            region_tell_24t[reg] = region_tell_24t.get(reg, 0) + 1
    regioner_js = []
    for navn, farge, lat_min, lat_max, lon_min, lon_max in REGIONER_RECT:
        regioner_js.append({
            'navn': navn, 'farge': farge,
            'type': 'rect',
            'bounds': [[lat_min, lon_min], [lat_max, lon_max]],
            'antall24t': region_tell_24t.get(navn, 0),
        })
    regioner_js.append({
        'navn': 'Møre og Romsdal', 'farge': '#FFC107',
        'type': 'polygon',
        'coords': MORE_POLYGON,
        'antall24t': region_tell_24t.get('Møre og Romsdal', 0),
    })
    region_tell_sorted = sorted(
        [(k, v) for k, v in region_tell_24t.items() if k not in ('Ukjent', 'Annet')],
        key=lambda x: -x[1]
    )

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
  #map{{height:calc(100vh - 160px);width:100%;border-radius:10px}}
  .toolbar{{padding:0 1rem 0.75rem;display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center}}
  .info{{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:0.5rem 0.9rem;
         font-size:0.85rem;color:#94a3b8}}
  .legend{{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:0.5rem 0.9rem;font-size:0.85rem;color:#94a3b8}}
  .legend span{{display:inline-flex;align-items:center;margin-right:0.9rem;cursor:pointer;user-select:none}}
  .legend span.inaktiv{{opacity:0.3;text-decoration:line-through}}
  .legend .dot{{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:0.4rem}}
  .toggle-btn{{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e5e7eb;
               padding:0.4rem 0.8rem;cursor:pointer;font-size:0.8rem}}
  .toggle-btn.aktiv{{border-color:#60a5fa;color:#60a5fa}}
  #regionpanel{{position:absolute;top:120px;right:16px;z-index:1000;background:#111827ee;
                border:1px solid #1f2937;border-radius:10px;padding:0.75rem;
                font-size:0.8rem;color:#e5e7eb;min-width:190px;display:none}}
  #regionpanel h3{{font-size:0.85rem;color:#f1f5f9;margin-bottom:0.5rem}}
  #regionpanel table{{width:100%;border-collapse:collapse}}
  #regionpanel td{{padding:2px 6px}}
  #regionpanel td:last-child{{text-align:right;font-weight:600}}
  .reg-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:5px}}
</style></head><body>
<nav><a href="/admin">← Admin</a></nav>
<h1>Registrerte priser i Norge</h1>
<div class="toolbar">
  <div class="info">{len(stasjoner)} stasjoner med pris</div>
  <div class="legend">
    <span data-kat="fersk"><span class="dot" style="background:#22c55e"></span>&lt; 8t ({tell['fersk']})</span>
    <span data-kat="dagsgammel"><span class="dot" style="background:#a3e635"></span>8–24t ({tell['dagsgammel']})</span>
    <span data-kat="ny"><span class="dot" style="background:#facc15"></span>24–48t ({tell['ny']})</span>
    <span data-kat="gammel"><span class="dot" style="background:#4b5563"></span>2–7d ({tell['gammel']})</span>
    <span data-kat="gammel7"><span class="dot" style="background:#9ca3af"></span>&gt;7d ({tell['gammel7']})</span>
  </div>
  <button class="toggle-btn" id="btnRegioner" onclick="toggleRegioner()">Vis regioner</button>
</div>
<div id="map"></div>
<div id="regionpanel">
  <h3>Priser siste 24t per region</h3>
  <table>{''.join(f"<tr><td><span class='reg-dot' style='background:{farge}'></span>{navn}</td><td>{region_tell_24t.get(navn,0)}</td></tr>" for navn, farge, *_ in REGIONER_RECT + [("Møre og Romsdal", "#FFC107")] if region_tell_24t.get(navn, 0) > 0)}</table>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const stasjoner = {json.dumps(stasjoner, ensure_ascii=False)};
const regioner = {json.dumps(regioner_js, ensure_ascii=False)};
const map = L.map('map').setView([63.4, 10.4], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap'
}}).addTo(map);

// Region-lag
const regionLag = [];
regioner.forEach(r => {{
  let shape;
  const opts = {{color: r.farge, fill: true, fillOpacity: 0.15, weight: 2,
                 interactive: true}};
  if (r.type === 'rect') {{
    shape = L.rectangle(r.bounds, opts);
  }} else {{
    shape = L.polygon(r.coords, opts);
  }}
  shape.bindTooltip(`<b>${{r.navn}}</b><br>${{r.antall24t}} oppdateringer siste 24t`,
    {{sticky: true, className: 'leaflet-tooltip-dark'}});
  regionLag.push(shape);
}});

let regionerVises = false;
function toggleRegioner() {{
  regionerVises = !regionerVises;
  const btn = document.getElementById('btnRegioner');
  const panel = document.getElementById('regionpanel');
  btn.classList.toggle('aktiv', regionerVises);
  btn.textContent = regionerVises ? 'Skjul regioner' : 'Vis regioner';
  panel.style.display = regionerVises ? 'block' : 'none';
  regionLag.forEach(l => regionerVises ? l.addTo(map) : map.removeLayer(l));
}}

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


@admin_bp.route('/admin/rutepris', methods=['GET', 'POST'])
@krever_innlogging
@krever_admin
def admin_rutepris():
    fra_txt = request.form.get('fra', '').strip() if request.method == 'POST' else ''
    til_txt = request.form.get('til', '').strip() if request.method == 'POST' else ''
    drivstoff = request.form.get('drivstoff', 'bensin') if request.method == 'POST' else 'bensin'
    maks_avvik_km = request.form.get('maks_avvik_km', type=float) if request.method == 'POST' else 3.0
    maks_avvik_km = max(0.5, min(maks_avvik_km or 3.0, 15.0))
    gyldige_drivstoff = {
        'bensin': '95 oktan',
        'bensin98': '98 oktan',
        'diesel': 'Diesel',
        'diesel_avgiftsfri': 'Avgiftsfri diesel',
    }
    if drivstoff not in gyldige_drivstoff:
        drivstoff = 'bensin'

    melding = ''
    fra = til = rute = None
    treff = []
    if request.method == 'POST':
        if not fra_txt or not til_txt:
            melding = 'Fyll inn både fra og til.'
        else:
            try:
                fra = _geokod_sted(fra_txt)
                til = _geokod_sted(til_txt)
                if not fra or not til:
                    melding = 'Fant ikke ett av stedene. Prøv mer presist stedsnavn.'
                else:
                    rute = _hent_osrm_rute(fra, til)
                    if not rute:
                        melding = 'Fant ingen kjørbar rute.'
                    else:
                        treff = _finn_billige_langs_rute(rute, drivstoff, maks_avvik_km)
                        if not treff:
                            melding = 'Fant ingen stasjoner med valgt pris langs ruta.'
            except Exception as e:
                logging.getLogger('drivstoff').warning(f'Rutepris feilet: {e}')
                melding = 'Rutesøk feilet. Prøv igjen litt senere.'

    def valgt(v):
        return 'selected' if v == drivstoff else ''

    rader = []
    for idx, s in enumerate(treff, 1):
        navn = html.escape(s['navn'] + (f' ({s["kjede"]})' if s.get('kjede') else ''))
        kart_url = f'https://www.google.com/maps?q={s["lat"]},{s["lon"]}'
        tidspunkt = html.escape((s.get('tidspunkt') or '')[:16])
        rader.append(
            f'<tr>'
            f'<td style="color:#94a3b8">{idx}</td>'
            f'<td><a href="{kart_url}" target="_blank">{navn}</a></td>'
            f'<td class="pris">{s["pris"]:.2f}</td>'
            f'<td>{s["avvik_m"]} m</td>'
            f'<td style="color:#94a3b8">{tidspunkt}</td>'
            f'</tr>'
        )
    tabell = (
        '<table><tr><th>#</th><th>Stasjon</th><th>Pris</th><th>Fra rute</th><th>Sist oppdatert</th></tr>'
        + ''.join(rader) + '</table>'
        if treff else ''
    )
    ruteinfo = ''
    if rute and fra and til:
        ruteinfo = (
            f'<div class="ruteinfo">Rute: <strong>{html.escape(fra["navn"])}</strong> til '
            f'<strong>{html.escape(til["navn"])}</strong> · ca. {rute["km"]:.0f} km · '
            f'{rute["min"]:.0f} min · {len(treff)} treff innenfor {maks_avvik_km:g} km</div>'
        )

    melding_html = f'<p class="melding">{html.escape(melding)}</p>' if melding else ''
    kartdata = {
        'rute': [[lat, lon] for lat, lon in rute['punkter']] if rute else [],
        'treff': [
            {
                'navn': s['navn'],
                'kjede': s.get('kjede') or '',
                'lat': s['lat'],
                'lon': s['lon'],
                'pris': s['pris'],
                'avvik_m': s['avvik_m'],
            }
            for s in treff
        ],
    }

    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Billigst på vei – Admin</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem}}
  .container{{max-width:1100px;margin:0 auto}}
  nav{{margin-bottom:1.5rem;font-size:0.85rem}}
  nav a,a{{color:#93c5fd}}
  h1{{font-size:1.35rem;margin-bottom:0.5rem;color:#f1f5f9}}
  .ingress{{font-size:0.9rem;color:#94a3b8;margin-bottom:1.25rem;line-height:1.5}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:1.25rem;margin-bottom:1rem}}
  form{{display:grid;grid-template-columns:1fr 1fr 170px 130px auto;gap:0.75rem;align-items:end}}
  .felt-wrap{{position:relative}}
  .input-rad{{display:flex;gap:0.4rem}}
  .pos-btn{{width:auto;background:#1f2937;border:1px solid #3b82f6;color:#bfdbfe;padding:0.7rem 0.75rem;white-space:nowrap}}
  .pos-btn:hover{{background:#1e3a8a}}
  label{{font-size:0.78rem;color:#94a3b8;display:block;margin-bottom:0.35rem}}
  input,select{{width:100%;background:#1f2937;border:1px solid #374151;border-radius:8px;color:#e5e7eb;padding:0.7rem 0.8rem;font-size:0.95rem}}
  button{{background:#2563eb;border:0;border-radius:8px;color:white;padding:0.75rem 1.1rem;font-weight:700;cursor:pointer}}
  .autocomplete{{position:absolute;z-index:20;top:100%;left:0;right:0;margin-top:4px;background:#111827;border:1px solid #374151;border-radius:10px;box-shadow:0 18px 40px rgba(0,0,0,0.35);overflow:hidden}}
  .autocomplete[hidden]{{display:none}}
  .autocomplete-rad{{padding:0.65rem 0.8rem;border-bottom:1px solid #1f2937;cursor:pointer;color:#e5e7eb;font-size:0.9rem}}
  .autocomplete-rad:last-child{{border-bottom:0}}
  .autocomplete-rad:hover,.autocomplete-rad.aktiv{{background:#1f2937;color:#bfdbfe}}
  .autocomplete-tom{{padding:0.65rem 0.8rem;color:#94a3b8;font-size:0.88rem}}
  .melding{{color:#f59e0b;margin-top:1rem}}
  .ruteinfo{{color:#cbd5e1;margin-bottom:1rem;font-size:0.9rem}}
  .grid{{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:1rem;align-items:start}}
  table{{width:100%;border-collapse:collapse;font-size:0.88rem}}
  td,th{{padding:9px 10px;border-bottom:1px solid #1f2937;text-align:left}}
  th{{color:#94a3b8;font-weight:600}}
  .pris{{font-weight:800;color:#22c55e}}
  #map{{height:520px;border-radius:12px;border:1px solid #1f2937;background:#020617}}
  @media(max-width:850px){{form{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}#map{{height:360px}}}}
</style></head><body><div class="container">
<nav><a href="/admin">&#8592; Admin</a></nav>
<h1>Billigste stasjon på veien</h1>
<p class="ingress">Admin-prototype. Bruker Photon for stedssøk, OSRM for rute og egne prisdata for å finne stasjoner nær ruta. Ingen AI involvert.</p>
<div class="kort">
  <form method="post">
    <div class="felt-wrap"><label>Fra</label><div class="input-rad"><input id="rute-fra" name="fra" value="{html.escape(fra_txt)}" placeholder="f.eks. Bergen" autocomplete="off" required><button class="pos-btn" id="bruk-posisjon" type="button">Her</button></div><div id="rute-fra-resultater" class="autocomplete" hidden></div></div>
    <div class="felt-wrap"><label>Til</label><input id="rute-til" name="til" value="{html.escape(til_txt)}" placeholder="f.eks. Oslo" autocomplete="off" required><div id="rute-til-resultater" class="autocomplete" hidden></div></div>
    <div><label>Drivstoff</label><select name="drivstoff">
      <option value="bensin" {valgt('bensin')}>95 oktan</option>
      <option value="bensin98" {valgt('bensin98')}>98 oktan</option>
      <option value="diesel" {valgt('diesel')}>Diesel</option>
      <option value="diesel_avgiftsfri" {valgt('diesel_avgiftsfri')}>Avg.fri diesel</option>
    </select></div>
    <div><label>Maks fra rute (km)</label><input type="number" min="0.5" max="15" step="0.5" name="maks_avvik_km" value="{maks_avvik_km:g}"></div>
    <button>Søk</button>
  </form>
  {melding_html}
</div>
{ruteinfo}
<div class="grid">
  <div class="kort">{tabell or '<p style="color:#94a3b8">Søk etter en rute for å se forslag.</p>'}</div>
  <div id="map"></div>
</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const data = {json.dumps(kartdata, ensure_ascii=False)};
const map = L.map('map').setView([63.4, 10.4], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '© OpenStreetMap' }}).addTo(map);
const bounds = [];
if (data.rute.length) {{
  L.polyline(data.rute, {{color:'#60a5fa', weight:5, opacity:0.85}}).addTo(map);
  bounds.push(...data.rute);
}}
data.treff.forEach((s, i) => {{
  const m = L.circleMarker([s.lat, s.lon], {{radius: i < 3 ? 9 : 7, color:'#022c22', fillColor: i < 3 ? '#22c55e' : '#f59e0b', fillOpacity:0.9}})
    .bindPopup(`<strong>${{i+1}}. ${{s.navn}}</strong>${{s.kjede ? ' (' + s.kjede + ')' : ''}}<br>Pris: ${{s.pris.toFixed(2)}}<br>Fra rute: ${{s.avvik_m}} m`)
    .addTo(map);
  bounds.push([s.lat, s.lon]);
}});
if (bounds.length) map.fitBounds(bounds, {{padding:[30,30]}});

function initAutocomplete(inputId, resultId) {{
  const input = document.getElementById(inputId);
  const resultEl = document.getElementById(resultId);
  let timer = null;
  let resultater = [];
  let aktiv = -1;

  function lukk() {{
    resultEl.hidden = true;
    resultEl.innerHTML = '';
    aktiv = -1;
  }}

  function marker() {{
    resultEl.querySelectorAll('.autocomplete-rad').forEach((el, i) => {{
      el.classList.toggle('aktiv', i === aktiv);
    }});
  }}

  function velg(i) {{
    const valgt = resultater[i];
    if (!valgt) return;
    input.value = valgt.navn;
    lukk();
  }}

  async function sok(q) {{
    try {{
      const resp = await fetch(`/api/stedssok?q=${{encodeURIComponent(q)}}`);
      resultater = await resp.json();
      aktiv = -1;
      if (!resultater.length) {{
        resultEl.innerHTML = '<div class="autocomplete-tom">Ingen treff</div>';
        resultEl.hidden = false;
        return;
      }}
      resultEl.innerHTML = resultater.map((r, i) =>
        `<div class="autocomplete-rad" data-i="${{i}}">${{r.navn}}</div>`
      ).join('');
      resultEl.hidden = false;
      resultEl.querySelectorAll('.autocomplete-rad').forEach(el => {{
        el.addEventListener('mousedown', e => {{
          e.preventDefault();
          velg(Number(el.dataset.i));
        }});
      }});
    }} catch {{
      lukk();
    }}
  }}

  input.addEventListener('input', () => {{
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) {{ lukk(); return; }}
    timer = setTimeout(() => sok(q), 250);
  }});

  input.addEventListener('keydown', e => {{
    const rader = resultEl.querySelectorAll('.autocomplete-rad');
    if (e.key === 'Escape') {{ lukk(); return; }}
    if (!rader.length) return;
    if (e.key === 'ArrowDown') {{
      e.preventDefault();
      aktiv = Math.min(aktiv + 1, rader.length - 1);
      marker();
    }} else if (e.key === 'ArrowUp') {{
      e.preventDefault();
      aktiv = Math.max(aktiv - 1, 0);
      marker();
    }} else if (e.key === 'Enter' && aktiv >= 0) {{
      e.preventDefault();
      velg(aktiv);
    }}
  }});

  input.addEventListener('blur', () => setTimeout(lukk, 150));
}}

initAutocomplete('rute-fra', 'rute-fra-resultater');
initAutocomplete('rute-til', 'rute-til-resultater');

document.getElementById('bruk-posisjon').addEventListener('click', () => {{
  const btn = document.getElementById('bruk-posisjon');
  const input = document.getElementById('rute-fra');
  if (!navigator.geolocation) {{
    alert('Nettleseren støtter ikke posisjon.');
    return;
  }}
  btn.disabled = true;
  btn.textContent = 'Henter...';
  navigator.geolocation.getCurrentPosition(
    pos => {{
      input.value = `pos:${{pos.coords.latitude.toFixed(6)}},${{pos.coords.longitude.toFixed(6)}}`;
      btn.textContent = 'Her';
      btn.disabled = false;
    }},
    () => {{
      alert('Kunne ikke hente posisjon. Sjekk posisjonstilgang i nettleseren.');
      btn.textContent = 'Her';
      btn.disabled = false;
    }},
    {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }}
  );
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
@krever_moderator
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


@admin_bp.route('/admin/kilde-statistikk')
@krever_admin
def kilde_statistikk():
    from db import get_conn
    with get_conn() as conn:
        rader = conn.execute('''
            SELECT COALESCE(kilde, 'kart') AS kilde,
                   COUNT(*) AS antall,
                   COUNT(DISTINCT bruker_id) AS unike_brukere,
                   MAX(tidspunkt) AS siste
            FROM priser
            GROUP BY kilde
            ORDER BY antall DESC
        ''').fetchall()
    rader_html = ''.join(
        f'<tr>'
        f'<td><strong>{r["kilde"]}</strong></td>'
        f'<td style="text-align:right">{r["antall"]}</td>'
        f'<td style="text-align:right">{r["unike_brukere"]}</td>'
        f'<td style="text-align:right;color:#94a3b8;font-size:0.85rem">{r["siste"] or "–"}</td>'
        f'</tr>'
        for r in rader
    ) or '<tr><td colspan="4" style="color:#94a3b8">Ingen data</td></tr>'
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kilde-statistikk – Admin</title>
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
  th{{text-align:left;padding:6px 8px;color:#94a3b8;font-weight:500;border-bottom:1px solid #1f2937}}
  th:not(:first-child){{text-align:right}}
  td{{padding:10px 8px;border-bottom:1px solid #1f2937;vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>Kilde-statistikk</h1>
<p class="info">Alle prisregistreringer fordelt på kilde. Historisk data (før kilde-tracking) vises som «kart».</p>
<div class="kort">
  <table>
    <thead><tr><th>Kilde</th><th>Registreringer</th><th>Unike brukere</th><th>Siste</th></tr></thead>
    <tbody>{rader_html}</tbody>
  </table>
</div>
</div></body></html>'''


@admin_bp.route('/admin/ocr-bilder')
@krever_innlogging
@krever_moderator
def admin_ocr_bilder():
    """Vis OCR-forsøk med original/crop-bilder, AI-resultat og fasit."""
    from db import get_conn
    filtre = request.args.get('filter', '')  # 'feil', 'fasit', ''
    side = max(1, int(request.args.get('side', 1)))
    PAGE_SIZE = 20

    base_select = '''SELECT o.id, COALESCE(b.brukernavn, 'bruker ' || o.bruker_id), o.tidspunkt, o.kilde, o.claude_resultat,
        o.lagret_priser, o.bilde_original, o.bilde_crop, o.stasjon_id, o.claude_ms
        FROM ocr_statistikk o LEFT JOIN brukere b ON b.id = o.bruker_id'''

    with get_conn() as conn:
        if filtre == 'feil':
            # Post-filtrering i Python — hent en større batch uten offset
            rows = conn.execute(base_select + '''
                WHERE o.lagret_priser IS NOT NULL AND o.claude_resultat IS NOT NULL
                ORDER BY o.id DESC LIMIT 500''').fetchall()
            totalt_db = None  # ukjent før filtrering
        elif filtre == 'fasit':
            totalt_db = conn.execute('SELECT COUNT(*) FROM ocr_statistikk WHERE lagret_priser IS NOT NULL').fetchone()[0]
            rows = conn.execute(base_select + '''
                WHERE o.lagret_priser IS NOT NULL
                ORDER BY o.id DESC LIMIT ? OFFSET ?''', (PAGE_SIZE, (side - 1) * PAGE_SIZE)).fetchall()
        else:
            totalt_db = conn.execute('SELECT COUNT(*) FROM ocr_statistikk').fetchone()[0]
            rows = conn.execute(base_select + '''
                ORDER BY o.id DESC LIMIT ? OFFSET ?''', (PAGE_SIZE, (side - 1) * PAGE_SIZE)).fetchall()

    felt_liste = ('bensin', 'diesel', 'bensin98', 'diesel_avgiftsfri')
    kort_html = []
    for r in rows:
        ocr_id, bruker, tidspunkt, kilde, claude_json, lagret_json, bilde_orig, bilde_crop, st_id, ms = r
        ai = json.loads(claude_json) if claude_json else {}
        lagret = json.loads(lagret_json) if lagret_json else None
        bekreftet_felt = set()
        if isinstance(lagret, dict) and isinstance(lagret.get('_bekreftet_felt'), list):
            bekreftet_felt = {f for f in lagret.get('_bekreftet_felt') if f in felt_liste}
        sammenlign_felt = tuple(bekreftet_felt) if bekreftet_felt else felt_liste

        # Filtrer: bare vis feil
        if filtre == 'feil' and lagret:
            har_avvik = False
            for f in sammenlign_felt:
                a = ai.get(f)
                l = lagret.get(f)
                if (a is not None or l is not None) and not (a is not None and l is not None and abs(float(a) - float(l)) < 0.02):
                    har_avvik = True
                    break
            if not har_avvik:
                continue

        dato = (tidspunkt or '')[:16].replace('T', ' ')
        modell = ai.get('_modell', kilde or '?')
        confidence = ai.get('confidence', '?')
        kjede = ai.get('kjede', '')

        # Priser-sammenligning
        pris_html = ''
        for f in sammenlign_felt:
            a = ai.get(f)
            l = lagret.get(f) if lagret else None
            if a is None and l is None:
                continue
            a_str = f'{a:.2f}' if a is not None else '–'
            l_str = f'{l:.2f}' if l is not None else '–'
            if a is not None and l is not None and abs(float(a) - float(l)) < 0.02:
                farge = '#22c55e'
            else:
                farge = '#ef4444'
            etk = {'bensin': '95', 'diesel': 'D', 'bensin98': '98', 'diesel_avgiftsfri': 'FD'}[f]
            pris_html += f'<div style="display:flex;justify-content:space-between;gap:8px"><span>{etk}</span><span>AI: {a_str}</span><span style="color:{farge}">Fasit: {l_str}</span></div>'

        if not pris_html:
            pris_html = '<span style="color:#6b7280">Ingen priser</span>'

        # Bilder — thumbnail med lightbox
        img_html = ''
        if bilde_orig:
            src = f'/admin/ocr-bilde/{html.escape(bilde_orig)}'
            img_html += f'<img src="{src}" class="ocr-thumb" data-full="{src}" loading="lazy" title="Original">'
        if bilde_crop:
            src = f'/admin/ocr-bilde/{html.escape(bilde_crop)}'
            img_html += f'<img src="{src}" class="ocr-thumb" data-full="{src}" loading="lazy" title="Crop">'
        if not img_html:
            img_html = '<span style="color:#6b7280">Ingen bilder</span>'

        crop_info = ''
        ocr_bilde = ai.get('_ocr_bilde')
        if isinstance(ocr_bilde, dict):
            crop_info = f' · {ocr_bilde.get("preprocess", "?")}'

        kort_html.append(f'''<div class="kort">
<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start">
  <div class="bilde-gruppe">{img_html}</div>
  <div style="flex:1;min-width:200px">
    <div style="color:#9ca3af;font-size:0.85em">{dato} · {html.escape(str(bruker))} · st.{st_id or "?"} · {html.escape(str(modell))} · {ms or "?"}ms{crop_info}</div>
    <div style="color:#d1d5db;font-size:0.85em">{html.escape(str(kjede or ""))} · confidence: {confidence}</div>
    <div style="margin-top:6px;font-family:monospace;font-size:0.9em">{pris_html}</div>
  </div>
</div></div>''')

    # Paginering for feil-filter (post-filtrert i Python)
    if filtre == 'feil':
        totalt_db = len(kort_html)
        start = (side - 1) * PAGE_SIZE
        kort_html = kort_html[start:start + PAGE_SIZE]

    totalt_sider = max(1, -(-totalt_db // PAGE_SIZE)) if totalt_db else 1

    def side_url(s):
        f = f'?filter={filtre}&side={s}' if filtre else f'?side={s}'
        return f'/admin/ocr-bilder{f}'

    filter_links = (
        f'<a href="/admin/ocr-bilder" class="btn{"" if filtre else " btn-aktiv"}">Alle</a> '
        f'<a href="/admin/ocr-bilder?filter=fasit" class="btn{"" if filtre != "fasit" else " btn-aktiv"}">Med fasit</a> '
        f'<a href="/admin/ocr-bilder?filter=feil" class="btn{"" if filtre != "feil" else " btn-aktiv"}">Bare feil</a>'
    )

    paginering = ''
    if totalt_sider > 1:
        pager = []
        if side > 1:
            pager.append(f'<a href="{side_url(side - 1)}" class="btn">← Forrige</a>')
        pager.append(f'<span style="padding:6px 10px;color:#9ca3af">Side {side} av {totalt_sider}</span>')
        if side < totalt_sider:
            pager.append(f'<a href="{side_url(side + 1)}" class="btn">Neste →</a>')
        paginering = f'<div style="margin-top:20px;display:flex;gap:6px;align-items:center">{"".join(pager)}</div>'

    antall_vist = len(kort_html)
    tittel_antall = f'{antall_vist} (side {side}/{totalt_sider})' if totalt_sider > 1 else str(antall_vist)

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OCR-bilder</title><style>
  body{{background:#111827;color:#e5e7eb;font-family:system-ui;margin:0;padding:16px}}
  .container{{max-width:900px;margin:0 auto}}
  nav a{{color:#93c5fd;text-decoration:none}}
  .kort{{background:#1f2937;border-radius:10px;padding:14px;margin-bottom:12px}}
  .btn{{display:inline-block;padding:6px 14px;background:#374151;color:#e5e7eb;border-radius:6px;text-decoration:none;margin:2px;font-size:0.9em}}
  .btn-aktiv{{background:#2563eb;color:#fff}}
  .bilde-gruppe{{display:flex;gap:8px;flex-wrap:wrap}}
  .ocr-thumb{{max-width:160px;max-height:120px;border-radius:6px;cursor:zoom-in;object-fit:contain;background:#111}}
  #lb-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:1000;align-items:center;justify-content:center;cursor:zoom-out}}
  #lb-overlay.vis{{display:flex}}
  #lb-img{{max-width:95vw;max-height:92vh;border-radius:8px;box-shadow:0 0 40px #000}}
  #lb-lukk{{position:fixed;top:16px;right:20px;font-size:2rem;color:#fff;cursor:pointer;line-height:1;user-select:none}}
</style></head><body><div class="container">
<nav><a href="/admin">← Admin</a></nav>
<h1>OCR-bilder ({tittel_antall})</h1>
<div style="margin-bottom:16px">{filter_links}</div>
{"".join(kort_html) or "<p>Ingen OCR-forsøk funnet.</p>"}
{paginering}
</div>

<div id="lb-overlay"><span id="lb-lukk">✕</span><img id="lb-img" src=""></div>
<script>
const overlay = document.getElementById('lb-overlay');
const lbImg = document.getElementById('lb-img');
document.querySelectorAll('.ocr-thumb').forEach(img => {{
  img.addEventListener('click', () => {{
    lbImg.src = img.dataset.full || img.src;
    overlay.classList.add('vis');
  }});
}});
overlay.addEventListener('click', () => overlay.classList.remove('vis'));
document.addEventListener('keydown', e => {{ if(e.key==='Escape') overlay.classList.remove('vis'); }});
</script>
</body></html>'''


@admin_bp.route('/admin/ocr-bilde/<path:sti>')
@krever_innlogging
@krever_moderator
def admin_ocr_bilde(sti):
    """Server OCR-bilder bak admin-autentisering."""
    from flask import send_from_directory, abort
    bilde_dir = os.environ.get('OCR_BILDE_DIR', '/app/data/ocr-bilder')
    if '..' in sti or sti.startswith('/'):
        abort(403)
    full_sti = os.path.join(bilde_dir, sti)
    if not os.path.isfile(full_sti):
        abort(404)
    return send_from_directory(os.path.dirname(full_sti), os.path.basename(full_sti), mimetype='image/jpeg')
