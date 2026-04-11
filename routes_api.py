"""API-ruter: stasjoner, priser, stedssøk, statistikk."""

import logging
import math
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta
from functools import wraps

import time

import httpx
from flask import Blueprint, request, jsonify, make_response, session

import base64
import json
import re

from db import (get_stasjoner_med_priser, lagre_pris, logg_visning,
                antall_stasjoner_med_pris, finn_bruker_id, DB_PATH,
                opprett_stasjon, hent_billigste_priser_24t,
                antall_prisoppdateringer_24t, meld_stasjon_nedlagt,
                get_conn, hent_innstilling, hent_toppliste, hent_toppliste_uke,
                hent_min_plassering, logg_blogg_visning,
                legg_til_endringsforslag, unike_enheter_per_dag,
                prisoppdateringer_per_time_24t,
                prisoppdateringer_rullende_24t_uke,
                har_rolle)

logger = logging.getLogger('drivstoff')

api_bp = Blueprint('api', __name__)

_PRIS_MIN_INTERVALL = 300  # sekunder (5 min)

NORGE_BBOX = {'lat_min': 57.0, 'lat_max': 71.5, 'lon_min': 4.0, 'lon_max': 31.5}


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})


@api_bp.route('/api/instance')
def instance():
    is_backup = bool(os.environ.get('FLY_APP_NAME'))
    return jsonify({'backup': is_backup})


@api_bp.route('/api/sync-db', methods=['PUT'])
def sync_db():
    sync_key = os.environ.get('SYNC_KEY', '')
    if not sync_key or request.headers.get('X-Sync-Key') != sync_key:
        return jsonify({'error': 'Ugyldig nøkkel'}), 403

    data = request.get_data()
    if not data:
        return jsonify({'error': 'Ingen data mottatt'}), 400

    fd, tmp_path = tempfile.mkstemp(suffix='.db')
    try:
        os.write(fd, data)
        os.close(fd)

        # Verifiser at mottatt DB er gyldig
        try:
            tmp_conn = sqlite3.connect(tmp_path)
            integrity_inn = tmp_conn.execute('PRAGMA integrity_check').fetchone()[0]
            antall_inn = tmp_conn.execute('SELECT COUNT(*) FROM stasjoner').fetchone()[0]
            tmp_conn.close()
        except sqlite3.DatabaseError as e:
            logger.error(f'Mottatt fil er ikke en gyldig SQLite-database: {e}')
            return jsonify({'error': 'Korrupt DB mottatt: ikke en gyldig database'}), 400
        if integrity_inn != 'ok':
            logger.error(f'Mottatt DB feilet integritetssjekk: {integrity_inn}')
            return jsonify({'error': f'Korrupt DB mottatt: {integrity_inn}'}), 400

        # Sjekk om eksisterende destinasjons-DB er korrupt.
        # Hvis korrupt: flytt unna og la backup() lage ny fra scratch.
        if os.path.exists(DB_PATH):
            try:
                dst_check = sqlite3.connect(DB_PATH, timeout=5)
                dst_integrity = dst_check.execute('PRAGMA integrity_check').fetchone()[0]
                dst_check.close()
                if dst_integrity != 'ok':
                    raise sqlite3.DatabaseError(f'integrity: {dst_integrity}')
            except sqlite3.DatabaseError as e:
                logger.warning(f'Destinasjons-DB er korrupt ({e}) – rydder opp før synk')
                corrupt_path = DB_PATH + '.corrupt'
                if os.path.exists(corrupt_path):
                    os.unlink(corrupt_path)
                os.rename(DB_PATH, corrupt_path)
                for ext in ('-wal', '-shm'):
                    p = DB_PATH + ext
                    if os.path.exists(p):
                        os.unlink(p)

        # Kopier inn via sqlite3.backup() — håndterer WAL korrekt.
        # timeout=30: vent på evt. aktive write-transaksjoner fra Flask-workers.
        src = sqlite3.connect(tmp_path)
        dst = sqlite3.connect(DB_PATH, timeout=30)
        src.backup(dst)
        src.close()
        # PASSIVE checkpoint: skriv WAL-sider til hoveddatabasen uten å blokkere
        # andre connections. WAL-modus forblir aktiv.
        dst.execute("PRAGMA wal_checkpoint(PASSIVE)")
        dst.close()

        # Verifiser at resultatet er en gyldig DB
        verify = sqlite3.connect(DB_PATH)
        result = verify.execute('PRAGMA integrity_check').fetchone()[0]
        antall_ut = verify.execute('SELECT COUNT(*) FROM stasjoner').fetchone()[0]
        verify.close()
        if result != 'ok':
            logger.error(f'Synkronisert DB feilet verifisering: {result}')
            return jsonify({'error': 'Sync fullført men DB feilet verifisering'}), 500

        logger.info(f'Database synkronisert OK: {len(data)} bytes, {antall_inn} → {antall_ut} stasjoner')
        return jsonify({'ok': True, 'bytes': len(data), 'stasjoner': antall_ut})
    except Exception as e:
        logger.error(f'Sync feilet: {e}')
        return jsonify({'error': 'Sync feilet'}), 500
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
    roller = (bruker.get('roller') or '').split()
    if har_rolle(bruker, 'kamera') and 'kamera' not in roller:
        roller.append('kamera')
    return jsonify({'innlogget': True, 'brukernavn': bruker['brukernavn'],
                    'kallenavn': bruker.get('kallenavn') or '', 'bruker_id': bruker['id'],
                    'er_admin': bool(bruker['er_admin']),
                    'roller': roller})


@api_bp.route('/api/stasjoner')
def stasjoner():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius_km = request.args.get('radius', default=30, type=int)
    if lat is None or lon is None:
        return jsonify({'error': 'lat og lon er påkrevd'}), 400
    if not er_i_norge(lat, lon):
        return jsonify({'error': 'Kun tilgjengelig i Norge', 'utenfor': True}), 400

    radius_m = max(1000, min(radius_km * 1000, 100_000))
    limit = 50 if radius_km >= 50 else 30
    data = get_stasjoner_med_priser(lat, lon, radius_m=radius_m, limit=limit)
    return jsonify({'stasjoner': data})


_stedssok_cache: dict[str, tuple[float, list]] = {}
_STEDSSOK_TTL = 600  # sekunder


@api_bp.route('/api/stedssok')
def stedssok():
    q = request.args.get('q', '').strip().lower()
    if len(q) < 2:
        return jsonify([])

    now = time.monotonic()
    cached = _stedssok_cache.get(q)
    if cached and now - cached[0] < _STEDSSOK_TTL:
        return jsonify(cached[1])

    try:
        resp = httpx.get(
            'https://photon.komoot.io/api/',
            params={'q': q, 'limit': 5, 'bbox': '4.0,57.0,31.5,71.5'},
            headers={'User-Agent': 'drivstoffpriser/1.0 (hobby)'},
            timeout=8,
        )
        features = resp.json().get('features', [])
        results = []
        for f in features:
            props = f.get('properties', {})
            if props.get('countrycode', '').upper() != 'NO':
                continue
            coords = f.get('geometry', {}).get('coordinates', [])
            if len(coords) < 2:
                continue
            deler = [props.get(k) for k in ('name', 'county', 'state', 'country') if props.get(k)]
            navn = ', '.join(dict.fromkeys(deler))
            results.append({'navn': navn, 'lat': float(coords[1]), 'lon': float(coords[0])})

        _stedssok_cache[q] = (now, results)
        return jsonify(results)
    except Exception as e:
        logger.warning(f'Stedssøk feilet: {e}')
        return jsonify([])


def _punkt_til_segment_m(lat, lon, a, b):
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


def _geokod_rutepunkt(q: str):
    q = (q or '').strip()
    if q.startswith('pos:'):
        deler = q[4:].split(',')
        if len(deler) == 2:
            try:
                lat, lon = float(deler[0]), float(deler[1])
                if er_i_norge(lat, lon):
                    return {'navn': 'Min posisjon', 'lat': lat, 'lon': lon}
            except ValueError:
                pass
        return None

    if len(q) < 2:
        return None

    resp = httpx.get(
        'https://photon.komoot.io/api/',
        params={'q': q, 'limit': 1, 'bbox': '4.0,57.0,31.5,71.5'},
        headers={'User-Agent': 'drivstoffpriser/1.0 rutepris'},
        timeout=8,
    )
    resp.raise_for_status()
    for f in resp.json().get('features', []):
        props = f.get('properties', {})
        if props.get('countrycode', '').upper() != 'NO':
            continue
        coords = f.get('geometry', {}).get('coordinates', [])
        if len(coords) >= 2:
            lat, lon = float(coords[1]), float(coords[0])
            if not er_i_norge(lat, lon):
                continue
            deler = [props.get(k) for k in ('name', 'county', 'state') if props.get(k)]
            return {'navn': ', '.join(dict.fromkeys(deler)) or q, 'lat': lat, 'lon': lon}
    return None


def _hent_osrm_rute(fra, til):
    resp = httpx.get(
        f'https://router.project-osrm.org/route/v1/driving/{fra["lon"]},{fra["lat"]};{til["lon"]},{til["lat"]}',
        params={'overview': 'full', 'geometries': 'geojson', 'alternatives': 'false', 'steps': 'false'},
        headers={'User-Agent': 'drivstoffpriser/1.0 rutepris'},
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


def _rute_stasjoner_i_boks(punkter, margin):
    min_lat = min(p[0] for p in punkter) - margin
    max_lat = max(p[0] for p in punkter) + margin
    min_lon = min(p[1] for p in punkter) - margin
    max_lon = max(p[1] for p in punkter) + margin
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.lagt_til_av,
                      s.har_bensin, s.har_bensin98, s.har_diesel, s.har_diesel_avgiftsfri,
                      (SELECT NULLIF(bensin, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS bensin,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND bensin IS NOT NULL AND bensin > 0 ORDER BY id DESC LIMIT 1) AS bensin_tidspunkt,
                      (SELECT NULLIF(diesel, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS diesel,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND diesel IS NOT NULL AND diesel > 0 ORDER BY id DESC LIMIT 1) AS diesel_tidspunkt,
                      (SELECT NULLIF(bensin98, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS bensin98,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND bensin98 IS NOT NULL AND bensin98 > 0 ORDER BY id DESC LIMIT 1) AS bensin98_tidspunkt,
                      (SELECT NULLIF(diesel_avgiftsfri, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS diesel_avgiftsfri,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND diesel_avgiftsfri IS NOT NULL AND diesel_avgiftsfri > 0 ORDER BY id DESC LIMIT 1) AS diesel_avgiftsfri_tidspunkt
               FROM stasjoner s
               WHERE s.godkjent != 0
                 AND (s.land IS NULL OR s.land = 'NO')
                 AND s.lat BETWEEN ? AND ? AND s.lon BETWEEN ? AND ?''',
            (min_lat, max_lat, min_lon, max_lon),
        ).fetchall()
    return [dict(r) for r in rows]


def _finn_billige_langs_rute(rute, drivstoff: str, maks_avvik_km: float, limit: int = 25):
    felt_til_tilbud = {
        'bensin': 'har_bensin',
        'bensin98': 'har_bensin98',
        'diesel': 'har_diesel',
        'diesel_avgiftsfri': 'har_diesel_avgiftsfri',
    }
    punkter = rute['punkter']
    if len(punkter) < 2:
        return []

    margin = maks_avvik_km / 111
    kandidater = []
    for s in _rute_stasjoner_i_boks(punkter, margin):
        if not s.get(felt_til_tilbud[drivstoff]):
            continue
        pris = s.get(drivstoff)
        if pris is None or pris <= 0:
            continue
        avstand = min(_punkt_til_segment_m(s['lat'], s['lon'], punkter[i], punkter[i + 1]) for i in range(len(punkter) - 1))
        if avstand <= maks_avvik_km * 1000:
            s.update({
                'pris': pris,
                'avvik_m': round(avstand),
                'brukeropprettet': s.get('lagt_til_av') is not None,
                'har_bensin': bool(s.get('har_bensin')),
                'har_bensin98': bool(s.get('har_bensin98')),
                'har_diesel': bool(s.get('har_diesel')),
                'har_diesel_avgiftsfri': bool(s.get('har_diesel_avgiftsfri')),
            })
            kandidater.append(s)
    kandidater.sort(key=lambda s: (s['pris'], s['avvik_m']))
    return kandidater[:limit]


@api_bp.route('/api/rutepris', methods=['POST'])
def rutepris():
    data = request.get_json(silent=True) or {}
    fra_txt = (data.get('fra') or '').strip()
    til_txt = (data.get('til') or '').strip()
    drivstoff = data.get('drivstoff') or 'diesel'
    if drivstoff not in {'bensin', 'bensin98', 'diesel', 'diesel_avgiftsfri'}:
        return jsonify({'error': 'Ugyldig drivstofftype'}), 400

    try:
        maks_avvik_km = float(data.get('maks_avvik_km', 3))
    except (TypeError, ValueError):
        maks_avvik_km = 3
    maks_avvik_km = max(0.5, min(maks_avvik_km, 15))

    if not fra_txt or not til_txt:
        return jsonify({'error': 'Fra og til er påkrevd'}), 400

    try:
        fra = _geokod_rutepunkt(fra_txt)
        til = _geokod_rutepunkt(til_txt)
        if not fra or not til:
            return jsonify({'error': 'Fant ikke fra- eller tilsted i Norge'}), 400

        rute = _hent_osrm_rute(fra, til)
        if not rute:
            return jsonify({'error': 'Fant ingen kjørerute'}), 400

        treff = _finn_billige_langs_rute(rute, drivstoff, maks_avvik_km)
        return jsonify({
            'fra': fra,
            'til': til,
            'rute': {
                'punkter': rute['punkter'],
                'km': rute['km'],
                'min': rute['min'],
            },
            'treff': treff,
            'drivstoff': drivstoff,
            'maks_avvik_km': maks_avvik_km,
        })
    except httpx.HTTPError as e:
        logger.warning(f'Rutepris ekstern tjeneste feilet: {e}')
        return jsonify({'error': 'Rutetjenesten svarte ikke. Prøv igjen om litt.'}), 502
    except Exception as e:
        logger.exception(f'Rutepris feilet: {e}')
        return jsonify({'error': 'Kunne ikke beregne rute nå'}), 500


@api_bp.route('/api/logview', methods=['POST'])
def logview():
    device_id = request.cookies.get('device_id', '')
    ny_enhet = not device_id
    if ny_enhet:
        device_id = str(uuid.uuid4())

    ua = request.headers.get('User-Agent', '')

    try:
        logg_visning(device_id, ua)
    except Exception as e:
        logger.warning(f'Logging feilet: {e}')

    resp = make_response(jsonify({'ok': True}))
    if ny_enhet:
        resp.set_cookie('device_id', device_id, max_age=63072000, samesite='Lax', path='/')
    return resp


@api_bp.route('/api/totalt-med-pris')
def totalt_med_pris():
    return jsonify({'totalt': antall_stasjoner_med_pris()})


@api_bp.route('/api/statistikk')
def statistikk():
    priser_24t = hent_billigste_priser_24t()
    antall_oppdateringer = antall_prisoppdateringer_24t()

    billigst = {'bensin': None, 'diesel': None, 'bensin98': None, 'diesel_avgiftsfri': None}
    dyrest = {'bensin': None, 'diesel': None, 'bensin98': None, 'diesel_avgiftsfri': None}
    for p in priser_24t:
        for typ in ('bensin', 'diesel', 'bensin98', 'diesel_avgiftsfri'):
            if p[typ] is not None and p[typ] > 0:
                entry = {
                    'pris': p[typ],
                    'stasjon': p['navn'],
                    'kjede': p['kjede'] or '',
                    'tidspunkt': p['tidspunkt'],
                    'stasjon_id': p['id'],
                    'lat': p['lat'],
                    'lon': p['lon'],
                }
                if billigst[typ] is None or p[typ] < billigst[typ]['pris']:
                    billigst[typ] = entry
                if dyrest[typ] is None or p[typ] > dyrest[typ]['pris']:
                    dyrest[typ] = entry

    return jsonify({
        'billigst': billigst,
        'dyrest': dyrest,
        'antall_oppdateringer_24t': antall_oppdateringer,
    })


@api_bp.route('/api/prisregistreringer-per-time')
def prisregistreringer_per_time():
    data = prisoppdateringer_per_time_24t()
    return jsonify([{'time': ts, 'antall': cnt} for ts, cnt in data])


@api_bp.route('/api/prisregistreringer-uke')
def prisregistreringer_uke():
    data = prisoppdateringer_rullende_24t_uke()
    return jsonify([{'time': ts, 'antall': cnt} for ts, cnt in data])


@api_bp.route('/api/enheter-per-dag')
def enheter_per_dag():
    return jsonify(unike_enheter_per_dag(30))


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
    diesel_avgiftsfri_raw = data.get('diesel_avgiftsfri')

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
    diesel_avgiftsfri = til_float(diesel_avgiftsfri_raw)

    bruker_id = session.get('bruker_id')

    lagret = lagre_pris(stasjon_id, bensin, diesel, bensin98, bruker_id=bruker_id, diesel_avgiftsfri=diesel_avgiftsfri, min_intervall=_PRIS_MIN_INTERVALL)
    if lagret:
        logger.info(f'Pris lagret: stasjon={stasjon_id} bensin={bensin} diesel={diesel} bensin98={bensin98} diesel_avgiftsfri={diesel_avgiftsfri} bruker={bruker_id}')
    else:
        logger.info(f'Pris ignorert (rate limit): stasjon={stasjon_id} bruker={bruker_id}')
    return jsonify({'ok': True})


@api_bp.route('/api/stasjon', methods=['POST'])
@krever_innlogging
def ny_stasjon():
    data = request.get_json(silent=True) or {}
    navn = (data.get('navn') or '').strip()
    kjede = (data.get('kjede') or '').strip()
    lat = data.get('lat')
    lon = data.get('lon')

    if not navn or len(navn) > 100:
        return jsonify({'error': 'Navn er påkrevd (maks 100 tegn)'}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return jsonify({'error': 'Ugyldig lat/lon'}), 400

    if not er_i_norge(lat, lon):
        return jsonify({'error': 'Posisjonen må være i Norge'}), 400

    bruker_id = session.get('bruker_id')
    stasjon_id, duplikat = opprett_stasjon(navn, kjede, lat, lon, bruker_id)

    if duplikat:
        return jsonify({
            'error': f'Det finnes allerede en stasjon i nærheten: {duplikat["navn"]}',
            'duplikat': duplikat
        }), 409

    logger.info(f'Ny stasjon opprettet: id={stasjon_id} navn={navn} bruker={bruker_id}')
    return jsonify({
        'ok': True,
        'stasjon': {'id': stasjon_id, 'navn': navn, 'kjede': kjede, 'lat': lat, 'lon': lon}
    })


@api_bp.route('/api/rapporter-nedlagt', methods=['POST'])
@krever_innlogging
def rapporter_nedlagt():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')
    if not stasjon_id:
        return jsonify({'error': 'stasjon_id er påkrevd'}), 400
    bruker_id = session.get('bruker_id')
    try:
        meld_stasjon_nedlagt(stasjon_id, bruker_id)
        logger.info(f'Stasjon {stasjon_id} meldt som nedlagt av bruker {bruker_id}')
        return jsonify({'ok': True})
    except Exception as e:
        logger.warning(f'Rapportering feilet: {e}')
        return jsonify({'error': 'Feil ved rapportering'}), 500


@api_bp.route('/api/foreslaa-endring', methods=['POST'])
@krever_innlogging
def foreslaa_endring():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')
    if not stasjon_id:
        return jsonify({'error': 'stasjon_id er påkrevd'}), 400
    foreslatt_navn = (data.get('foreslatt_navn') or '').strip() or None
    foreslatt_kjede = (data.get('foreslatt_kjede') or '').strip() or None
    er_nedlagt = bool(data.get('er_nedlagt'))
    if not foreslatt_navn and not foreslatt_kjede and not er_nedlagt:
        return jsonify({'error': 'Minst ett felt må fylles ut'}), 400
    bruker_id = session.get('bruker_id')
    try:
        if er_nedlagt:
            meld_stasjon_nedlagt(stasjon_id, bruker_id)
        if foreslatt_navn or foreslatt_kjede:
            legg_til_endringsforslag(stasjon_id, bruker_id, foreslatt_navn, foreslatt_kjede)
        logger.info(f'Endringsforslag for stasjon {stasjon_id} fra bruker {bruker_id}: navn={foreslatt_navn}, kjede={foreslatt_kjede}, nedlagt={er_nedlagt}')
        return jsonify({'ok': True})
    except Exception as e:
        logger.warning(f'Endringsforslag feilet: {e}')
        return jsonify({'error': 'Feil ved innsending'}), 500


@api_bp.route('/api/nyhet')
def nyhet():
    import hashlib

    # Admin-nyhet trumfer alltid
    tekst = hent_innstilling('nyhet_tekst', '')
    utloper = hent_innstilling('nyhet_utloper', '')
    if tekst and utloper:
        try:
            utloper_dt = datetime.fromisoformat(utloper)
            if datetime.now() < utloper_dt:
                nyhet_id = hashlib.md5(tekst.encode()).hexdigest()[:8]
                return jsonify({'tekst': tekst, 'utloper': utloper, 'id': nyhet_id, 'tittel': 'Nyhet'})
        except ValueError:
            pass

    # Personaliserte ukentlige meldinger
    if hent_innstilling('personlig_splash', '') != '1':
        return jsonify({'tekst': None})

    from datetime import timedelta
    from db import get_conn

    uke = datetime.now().isocalendar()[1]
    aar = datetime.now().year
    bruker_id = session.get('bruker_id')

    if bruker_id:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM priser WHERE bruker_id = ? AND tidspunkt >= datetime('now', '-7 days')",
                (bruker_id,)
            ).fetchone()
        antall = row[0] if row else 0

        if antall == 0:
            tekst = ('Nå er vi over 4 000 registrerte brukere!\n\n'
                      'Prisene holdes oppdatert av brukerne selv — hver eneste pris teller. '
                      'Har du mulighet til å legge inn en pris eller to neste gang du fyller?')
            tittel = 'Hei!'
        elif antall < 20:
            tekst = (f'Takk for de {antall} prisene du har lagt inn denne uken!\n\n'
                      'Du er én av mange som holder prisene ferske for over 50\u00a0000 besøkende.')
            tittel = 'Hei!'
        else:
            tekst = (f'Wow — {antall} priser denne uken!\n\n'
                      'Du er en av våre mest aktive bidragsytere, og det merkes. Tusen takk!')
            tittel = 'Hei!'
        splash_id = f'pers_{aar}w{uke}_{bruker_id}'
    else:
        tekst = ('Over 50\u00a0000 har brukt drivstoffprisene.no så langt — og prisene holdes '
                  'oppdatert av brukere som deg.\n\n'
                  'Har du lyst til å bidra? Opprett en bruker, så kan du legge inn priser '
                  'på stasjoner du passerer.')
        tittel = 'Velkommen!'
        splash_id = f'pers_{aar}w{uke}_anon'

    # Utløper ved slutten av uken (søndag 23:59)
    i_dag = datetime.now()
    dager_til_sondag = 6 - i_dag.weekday()
    if dager_til_sondag < 0:
        dager_til_sondag += 7
    utloper = (i_dag + timedelta(days=dager_til_sondag)).replace(hour=23, minute=59, second=59).isoformat()

    return jsonify({'tekst': tekst, 'utloper': utloper, 'id': splash_id, 'tittel': tittel})


@api_bp.route('/api/toppliste')
def toppliste():
    bruker_id = session.get('bruker_id')

    liste = hent_toppliste(limit=20)
    bruker_i_liste = False
    resultat = []
    for rad in liste:
        er_meg = bruker_id is not None and rad['id'] == bruker_id
        if er_meg:
            bruker_i_liste = True
        resultat.append({
            'kallenavn': rad['kallenavn'] or None,
            'antall': rad['antall'],
            'er_meg': er_meg
        })
    min_plass = None
    if bruker_id and not bruker_i_liste:
        min_plass = hent_min_plassering(bruker_id)

    liste_uke = hent_toppliste_uke(limit=20)
    resultat_uke = []
    for rad in liste_uke:
        er_meg = bruker_id is not None and rad['id'] == bruker_id
        resultat_uke.append({
            'kallenavn': rad['kallenavn'] or None,
            'antall': rad['antall'],
            'er_meg': er_meg
        })

    return jsonify({'liste': resultat, 'liste_uke': resultat_uke, 'min_plass': min_plass})


@api_bp.route('/om')
def om():
    return '''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Om – Drivstoffpriser</title>
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem;-webkit-font-smoothing:antialiased}
  .container{max-width:540px;margin:0 auto}
  h1{font-size:1.5rem;margin-bottom:0.5rem;color:#f1f5f9}
  .undertittel{font-size:0.9rem;color:#94a3b8;margin-bottom:1.5rem}
  h2{font-size:1.05rem;margin-bottom:0.75rem;color:#f1f5f9}
  .kort{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.25rem;margin-bottom:1rem}
  p{line-height:1.6;margin-bottom:0.75rem;font-size:0.92rem;color:#cbd5e1}
  p:last-child{margin-bottom:0}
  ul{list-style:none;padding:0;margin:0}
  ul li{font-size:0.92rem;color:#cbd5e1;line-height:1.6;padding:0.25rem 0;padding-left:1.5rem;position:relative}
  ul li::before{content:"";position:absolute;left:0;top:0.65rem;width:6px;height:6px;border-radius:50%;background:#3b82f6}
  a{color:#3b82f6}
  .tilbake{display:inline-block;margin-bottom:1.5rem;color:#94a3b8;font-size:0.85rem;text-decoration:none}
  .tilbake:hover{color:#e5e7eb}
  .emoji{font-size:1.1rem;margin-right:6px}
  .farge-rad{display:flex;align-items:center;gap:8px;margin-bottom:0.5rem;font-size:0.92rem;color:#cbd5e1}
  .farge-rad:last-child{margin-bottom:0}
  .farge-prikk{width:14px;height:14px;border-radius:50%;display:inline-block;flex-shrink:0}
  .steg{display:flex;gap:12px;align-items:flex-start;margin-bottom:0.75rem;font-size:0.92rem;color:#cbd5e1}
  .steg:last-child{margin-bottom:0}
  .steg-nr{background:#3b82f6;color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.8rem;font-weight:600;flex-shrink:0}
  .steg-tekst{line-height:1.5;padding-top:1px}
  .donasjon{display:flex;align-items:center;gap:12px;background:#1f2937;border:1px solid #374151;
            border-radius:8px;padding:14px 16px;text-decoration:none;color:#e5e7eb;margin-top:0.75rem}
  .donasjon:hover{background:#263245}
  .donasjon svg{flex-shrink:0;width:80px}
  .donasjon-tekst{font-size:0.88rem;line-height:1.5}
  .donasjon-tekst strong{color:#f1f5f9}
  .tag{display:inline-block;background:#1e3a5f;color:#93c5fd;font-size:0.78rem;padding:2px 8px;border-radius:4px;margin-right:4px}
</style></head><body><div class="container">
<a class="tilbake" href="/">&#8592; Tilbake til appen</a>
<h1>Drivstoffpriser</h1>
<p class="undertittel">Finn billigst drivstoff i n&#230;rheten &#8212; gratis, mobilvennlig og drevet av brukerne.</p>
<p style="margin-top:0.5rem"><a href="/blogg/" style="color:#93c5fd;font-weight:600">&#128211; Les prisanalyse-bloggen &#8594;</a></p>

<div class="kort">
  <h2>Hva er dette?</h2>
  <p>Drivstoffpriser er en gratis PWA/webapp der brukerne selv registrerer og oppdaterer drivstoffpriser. Jo flere som bidrar, jo ferskere og mer nyttige priser f&#229;r alle.</p>
  <p>Appen st&#248;tter <strong>95 oktan</strong>, <strong>98 oktan</strong>, <strong>diesel</strong> og <strong>avgiftsfri diesel</strong>.</p>
  <p>Du kan bruke appen helt uten konto for &#229; se kart, liste og statistikk. Konto trengs bare hvis du vil bidra med prisoppdateringer, legge til stasjoner eller sende inn forslag.</p>
  <p style="margin-top:0.5rem;font-size:0.85rem;color:#94a3b8">Liker du appen? En liten donasjon hjelper med &#229; dekke serverdrift.</p>
  <a class="donasjon" href="https://qr.vipps.no/box/4aa50659-cefa-415b-b638-fa1f73e65d1e/pay-in" target="_blank" rel="noopener">
    <svg viewBox="0 0 128 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path fill-rule="evenodd" clip-rule="evenodd" d="M128 7.67678C126.56 2.18136 123.063 0 118.289 0C114.422 0 109.568 2.18136 109.568 7.43431C109.568 10.828 111.913 13.4952 115.739 14.1823L119.359 14.8284C121.828 15.2726 122.528 16.2022 122.528 17.4548C122.528 18.8689 121.005 19.6769 118.743 19.6769C115.781 19.6769 113.929 18.6265 113.641 15.6766L108.416 16.4849C109.239 22.1817 114.34 24.5259 118.948 24.5259C123.309 24.5259 127.958 22.0202 127.958 16.9699C127.958 13.535 125.86 11.0307 121.951 10.3024L117.961 9.57584C115.739 9.17187 114.999 8.08075 114.999 7.03034C114.999 5.69675 116.438 4.84898 118.413 4.84898C120.923 4.84898 122.692 5.69675 122.774 8.48472L128 7.67678ZM11.85 16.3226L17.2798 0.605739H23.6567L14.1937 23.9188H9.46293L0 0.606177H6.37685L11.85 16.3226ZM45.2167 7.27281C45.2167 9.13116 43.7356 10.424 42.0073 10.424C40.2795 10.424 38.7988 9.13116 38.7988 7.27281C38.7988 5.41401 40.2795 4.12156 42.0073 4.12156C43.7356 4.12156 45.2172 5.41401 45.2172 7.27281H45.2167ZM46.204 15.5155C44.0642 18.2622 41.8014 20.1613 37.8106 20.1614C33.7386 20.1614 30.5698 17.7371 28.1014 14.1819C27.1137 12.7271 25.5914 12.4041 24.4803 13.1718C23.452 13.8992 23.2057 15.4345 24.1514 16.7681C27.566 21.8994 32.2972 24.8887 37.8102 24.8887C42.8712 24.8887 46.8212 22.4649 49.9064 18.4243C51.0582 16.9296 51.017 15.3943 49.9064 14.5456C48.8776 13.7368 47.3553 14.0208 46.204 15.5155ZM60.3999 12.2019C60.3999 16.9699 63.1978 19.4751 66.3249 19.4751C69.2868 19.4751 72.3317 17.1314 72.3317 12.2019C72.3317 7.3529 69.2868 5.01004 66.3656 5.01004C63.1978 5.01004 60.3999 7.2321 60.3999 12.2019ZM60.3999 3.83883V0.646005H54.5992V32H60.3999V20.8481C62.3338 23.4343 64.8434 24.5259 67.6818 24.5259C72.9901 24.5259 78.1736 20.4043 78.1736 11.9196C78.1736 3.79769 72.784 0.000437673 68.1757 0.000437673C64.514 0.000437673 62.0049 1.65659 60.3999 3.83883ZM88.2551 12.2019C88.2551 16.9699 91.0524 19.4751 94.1796 19.4751C97.1415 19.4751 100.186 17.1314 100.186 12.2019C100.186 7.3529 97.1415 5.01004 94.2203 5.01004C91.0524 5.01004 88.2546 7.2321 88.2546 12.2019H88.2551ZM88.2551 3.83883V0.646005H88.2546H82.4539V32H88.2546V20.8481C90.1885 23.4343 92.6981 24.5259 95.5365 24.5259C100.844 24.5259 106.028 20.4043 106.028 11.9196C106.028 3.79769 100.639 0.000437673 96.0304 0.000437673C92.3687 0.000437673 89.8596 1.65659 88.2551 3.83883Z" fill="#ff5b24"/>
    </svg>
    <div class="donasjon-tekst"><strong>St&#248;tt prosjektet</strong><br>Vipps en kaffekopp eller to</div>
  </a>
</div>

<div class="kort">
  <h2>Slik bruker du appen</h2>
  <div class="steg">
    <span class="steg-nr">1</span>
    <span class="steg-tekst"><strong>Hent posisjon</strong> eller <strong>s&#248;k etter et sted</strong> for &#229; finne stasjoner i n&#230;rheten eller i et annet omr&#229;de.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">2</span>
    <span class="steg-tekst"><strong>Bytt mellom Kart, Liste og Statistikk</strong> nederst i appen. Trykk p&#229; en stasjon for priser, avstand, kjede og navigasjon.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">3</span>
    <span class="steg-tekst"><strong>Logg inn for &#229; bidra</strong>. N&#229;r du er ved en stasjon kan du trykke &#171;Endre pris&#187; og legge inn prisene du ser p&#229; tavla eller pumpa.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">4</span>
    <span class="steg-tekst"><strong>Mangler noe eller er noe feil?</strong> Logg inn og legg til stasjon, foresl&#229; nytt navn/kjede eller meld at en stasjon er nedlagt.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">5</span>
    <span class="steg-tekst"><strong>Tips:</strong> Legg appen til p&#229; hjem-skjermen for raskere tilgang og en mer app-lignende opplevelse p&#229; mobilen.</span>
  </div>
</div>

<div class="kort">
  <h2>Hva finner du i appen?</h2>
  <ul>
    <li><strong>Kart</strong> &#8212; se stasjoner rundt deg med fargekodede mark&#248;rer basert p&#229; hvor gamle prisene er</li>
    <li><strong>Liste</strong> &#8212; sammenlign stasjoner sortert etter avstand eller pris</li>
    <li><strong>Statistikk</strong> &#8212; billigste og dyreste priser siste 24 timer, antall oppdateringer og toppliste</li>
    <li><strong>S&#248;k</strong> &#8212; finn stasjoner i andre byer og omr&#229;der</li>
    <li><strong>Innstillinger</strong> &#8212; velg drivstofftyper, s&#248;keradius og kartvisning</li>
    <li><strong>Bidra</strong> &#8212; oppdater priser, legg til stasjoner og send inn endringsforslag</li>
    <li><strong>Bidragsmodus</strong> &#8212; egen side for raskere prisoppdateringer for aktive brukere</li>
    <li><strong>Fungerer offline</strong> &#8212; sist viste data er tilgjengelige uten nett</li>
  </ul>
</div>

<div class="kort">
  <h2>N&#229;r trenger du konto?</h2>
  <ul>
    <li><strong>Ikke innlogget:</strong> Du kan se stasjoner, priser, statistikk, blogg og bruke s&#248;k og navigasjon</li>
    <li><strong>Innlogget:</strong> Du kan oppdatere priser, legge til stasjoner, velge kallenavn og sende inn forslag</li>
    <li><strong>Moderator / admin:</strong> Har i tillegg tilgang til moderering, adminpanel og enkelte ekstra verkt&#248;y</li>
  </ul>
</div>

<div class="kort">
  <h2>Fargekoder p&#229; kartet</h2>
  <div class="farge-rad"><span class="farge-prikk" style="background:#22c55e"></span> Fersk pris (under 8 timer)</div>
  <div class="farge-rad"><span class="farge-prikk" style="background:#f59e0b"></span> Pris 8&#8211;48 timer gammel</div>
  <div class="farge-rad"><span class="farge-prikk" style="background:#8b5cf6"></span> Pris 2&#8211;7 dager gammel</div>
  <div class="farge-rad"><span class="farge-prikk" style="background:#6b7280"></span> Eldre pris eller ingen pris</div>
</div>

<div class="kort">
  <h2>Installer p&#229; telefonen</h2>
  <p><strong>iPhone (Safari):</strong> Trykk p&#229; del-ikonet og velg &#171;Legg til p&#229; Hjem-skjerm&#187;.</p>
  <p><strong>Android (Chrome):</strong> Trykk p&#229; menyen (tre prikker) og velg &#171;Legg til p&#229; startskjermen&#187;.</p>
  <p style="margin-top:0.5rem;color:#94a3b8;font-size:0.85rem">Hvis GPS oppf&#248;rer seg rart i en innebygd nettleser, fungerer appen som regel best i Safari eller Chrome.</p>
</div>

<div class="kort">
  <h2>Om prosjektet</h2>
  <p>Laget som et hobbyprosjekt av Kjetil Salomonsen. Appen er <strong>helt gratis</strong> &#229; bruke.</p>
  <p>Sp&#248;rsm&#229;l eller tilbakemeldinger? Send en e-post til <a href="mailto:k@vikebo.com">k@vikebo.com</a></p>
  <p>Les v&#229;r <a href="/personvern">personvernerkl&#230;ring</a>.</p>
</div>

<div class="kort">
  <h2>Versjonshistorikk</h2>
  <p><strong>v1.3.x</strong> <span class="tag">april 2026</span></p>
  <ul>
    <li>Personlige splash-meldinger og bedre hjelpetekster i appen</li>
    <li>Flere forbedringer for redigering av priser og stasjonsdetaljer</li>
    <li>Utvidet blogg og analyseinnhold p&#229; <a href="/blogg/">/blogg/</a></li>
  </ul>
  <p style="margin-top:1rem"><strong>v1.2.x</strong> <span class="tag">slutten av mars 2026</span></p>
  <ul>
    <li>Toppliste over mest aktive bidragsytere i statistikk-fanen</li>
    <li>Deling fra innstillinger og bedre bidragsflyt</li>
    <li>Prisanalyse-blogg med ukentlige analyser</li>
  </ul>
  <p style="margin-top:1rem"><strong>v1.1.x</strong> <span class="tag">mars 2026</span></p>
  <ul>
    <li>Registrering ble &#229;pnet for alle</li>
    <li>Valgbar s&#248;keradius og flere drivstofftyper</li>
    <li>Du kan n&#229; melde fra om nedlagte stasjoner</li>
  </ul>
  <p style="margin-top:1rem"><strong>v1.0.0</strong> <span class="tag">mars 2026</span></p>
  <ul>
    <li>F&#248;rste versjon med kart, liste og statistikk</li>
    <li>Brukerregistrering og prisoppdatering</li>
    <li>PWA med offline-st&#248;tte</li>
    <li>Full tilgjengelighet (UU/a11y)</li>
    <li>Steds&#248;k og navigering</li>
  </ul>
</div>

</div></body></html>'''


@api_bp.route('/personvern')
def personvern():
    return '''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Personvern – Drivstoffpriser</title>
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e5e7eb;padding:2rem 1rem;-webkit-font-smoothing:antialiased}
  .container{max-width:540px;margin:0 auto}
  h1{font-size:1.5rem;margin-bottom:0.5rem;color:#f1f5f9}
  .undertittel{font-size:0.9rem;color:#94a3b8;margin-bottom:1.5rem}
  h2{font-size:1.05rem;margin-bottom:0.75rem;color:#f1f5f9}
  .kort{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.25rem;margin-bottom:1rem}
  p{line-height:1.6;margin-bottom:0.75rem;font-size:0.92rem;color:#cbd5e1}
  p:last-child{margin-bottom:0}
  ul{list-style:none;padding:0;margin:0}
  ul li{font-size:0.92rem;color:#cbd5e1;line-height:1.6;padding:0.25rem 0;padding-left:1.5rem;position:relative}
  ul li::before{content:"";position:absolute;left:0;top:0.65rem;width:6px;height:6px;border-radius:50%;background:#3b82f6}
  a{color:#3b82f6}
  .tilbake{display:inline-block;margin-bottom:1.5rem;color:#94a3b8;font-size:0.85rem;text-decoration:none}
  .tilbake:hover{color:#e5e7eb}
</style></head><body><div class="container">
<a class="tilbake" href="/">&#8592; Tilbake til appen</a>
<h1>Personvern</h1>
<p class="undertittel">Sist oppdatert: 24. mars 2026</p>

<div class="kort">
  <h2>Kort oppsummert</h2>
  <p>Drivstoffpriser er et hobbyprosjekt som samler inn s&#229; lite data som mulig. Du trenger ikke opprette konto for &#229; bruke appen. Posisjonen din forblir i nettleseren din og sendes ikke til serveren.</p>
</div>

<div class="kort">
  <h2>Behandlingsansvarlig</h2>
  <p>Kjetil Salomonsen<br><a href="mailto:k@vikebo.com">k@vikebo.com</a></p>
</div>

<div class="kort">
  <h2>Hvilke opplysninger samles inn?</h2>
  <p><strong>Uten innlogging:</strong></p>
  <ul>
    <li>Anonym bes&#248;ksstatistikk: en tilfeldig enhets-ID (lagret i informasjonskapsel) og nettlesertype. Dette brukes utelukkende for &#229; telle unike bes&#248;k. IP-adresser lagres ikke.</li>
  </ul>
  <p><strong>Med innlogging:</strong></p>
  <ul>
    <li>E-postadresse (brukes som brukernavn)</li>
    <li>Passord &#8212; lagres kun som en sikker, irreversibel hash. Ingen kan lese passordet ditt, heller ikke administrator.</li>
    <li>Prisoppdateringer og stasjoner du legger til knyttes til brukerkontoen din.</li>
  </ul>
</div>

<div class="kort">
  <h2>Posisjon / GPS</h2>
  <p>N&#229;r du deler posisjonen din med appen, lagres den <strong>kun lokalt i nettleseren</strong> (localStorage). Posisjonen sendes ikke til serveren og logges ikke.</p>
</div>

<div class="kort">
  <h2>Informasjonskapsler (cookies)</h2>
  <ul>
    <li><strong>device_id</strong> &#8212; tilfeldig ID for anonym bes&#248;ksstatistikk. Utl&#248;per etter 2 &#229;r.</li>
    <li><strong>session</strong> &#8212; brukes kun n&#229;r du er innlogget. Utl&#248;per etter 90 dager.</li>
  </ul>
  <p>Ingen tredjeparts-cookies eller sporingsteknologi brukes.</p>
</div>

<div class="kort">
  <h2>Lagring og sikkerhet</h2>
  <ul>
    <li>All trafikk g&#229;r over <strong>HTTPS</strong> (kryptert forbindelse).</li>
    <li>Data lagres p&#229; servere i <strong>Norge/Europa</strong>.</li>
    <li>Ingen data deles med eller selges til tredjeparter.</li>
  </ul>
</div>

<div class="kort">
  <h2>Dine rettigheter</h2>
  <p>Du har rett til &#229;:</p>
  <ul>
    <li>F&#229; innsyn i hvilke opplysninger som er lagret om deg</li>
    <li>F&#229; opplysninger rettet eller slettet</li>
    <li>Slette brukerkontoen din (under &#171;Min konto&#187; n&#229;r du er innlogget)</li>
  </ul>
  <p>Kontakt <a href="mailto:k@vikebo.com">k@vikebo.com</a> for innsynsforesp&#248;rsler.</p>
</div>

<div class="kort">
  <h2>Endringer</h2>
  <p>Denne personvernerkl&#230;ringen kan oppdateres ved behov. Vesentlige endringer vil bli varslet p&#229; forsiden av appen.</p>
</div>

</div></body></html>'''


# --- Datadeling ---

@api_bp.route('/api/share/prices', methods=['GET'])
def share_prices():
    nøkkel = request.headers.get('X-API-Key', '')
    with get_conn() as conn:
        partner = conn.execute(
            'SELECT partner FROM api_nøkler WHERE nøkkel = ? AND aktiv = 1',
            (nøkkel,)
        ).fetchone()
    if not nøkkel or not partner:
        return jsonify({'error': 'Ugyldig API-nøkkel'}), 403

    partner_navn = partner[0]

    fra = request.args.get('from')
    til = request.args.get('to')

    now = datetime.utcnow()
    if fra:
        try:
            fra_dt = datetime.fromisoformat(fra)
        except ValueError:
            return jsonify({'error': 'Ugyldig from-format, bruk ISO 8601'}), 400
    else:
        fra_dt = now - timedelta(hours=24)

    if til:
        try:
            til_dt = datetime.fromisoformat(til)
        except ValueError:
            return jsonify({'error': 'Ugyldig to-format, bruk ISO 8601'}), 400
    else:
        til_dt = now

    if til_dt <= fra_dt:
        return jsonify({'error': 'to må være etter from'}), 400

    if (til_dt - fra_dt) > timedelta(hours=24):
        return jsonify({'error': 'Maks 24 timers spenn'}), 400

    with get_conn() as conn:
        rows = conn.execute('''
            SELECT s.id, s.navn,
                   p.bensin, p.diesel, p.bensin98, p.tidspunkt
            FROM priser p
            JOIN stasjoner s ON s.id = p.stasjon_id
            WHERE p.tidspunkt >= ? AND p.tidspunkt <= ?
            ORDER BY p.tidspunkt DESC
        ''', (fra_dt.strftime('%Y-%m-%d %H:%M:%S'), til_dt.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()

    prices = [
        {
            'station_id': r[0],
            'name': r[1],
            'petrol': r[2],
            'diesel': r[3],
            'petrol98': r[4],
            'updated': r[5]
        }
        for r in rows
    ]

    with get_conn() as conn:
        conn.execute(
            'INSERT INTO api_logg (partner, antall) VALUES (?, ?)',
            (partner_navn, len(prices))
        )

    return jsonify({'prices': prices})




@api_bp.route('/api/blogg/vis', methods=['POST'])
def blogg_vis():
    data = request.get_json(silent=True) or {}
    slug = (data.get('slug') or '').strip()[:100]
    if not slug:
        return jsonify({'ok': False}), 400
    logg_blogg_visning(slug)
    return jsonify({'ok': True})


_OCR_GRENSE_PER_DAG = 50  # maks kall per bruker per dag
_ocr_bruk = {}  # {bruker_id: (dato, antall)}


_OCR_MIN_PRIS = 15.0
_OCR_MAX_PRIS = 35.0


_OCR_PROMPT_BASE = """Du er en prisavleser for norske bensinstasjoner. Din ENESTE oppgave er å lese drivstoffpriser fra pristavler/prisdisplay.

AVVIS bildet og returner alle null-verdier hvis:
- Bildet ikke viser en pristavle eller prisdisplay fra en bensinstasjon
- Prisene ikke er lesbare (for langt unna, uskarp, refleks)
- Du er usikker på enkeltsiffer og kan ikke korrigere med prislogikken nedenfor

Viktig: Ikke returner alle null bare fordi bildet er vanskelig. Hvis du ser minst én plausibel prisrad med tall i området 15.00–35.00, returner den eller de sikre prisene og sett resten til null.

Returner KUN gyldig JSON uten annen tekst:
{"bensin": null, "diesel": null, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "low", "uncertain_fields": []}

Det finnes kun fire drivstofftyper. Hver kjede har egne produktnavn, men de betyr alltid det samme:
- "bensin" = vanlig bensin. På tavlen: "95", "Blyfri", "B", "miles 95", "Futura 95", eller bare den øverste prisen uten etikett.
- "bensin98" = høyoktan bensin. På tavlen: "98", "V-Power", "miles 98", "Futura 98", "Extra".
- "diesel" = vanlig diesel. På tavlen: "D", "Diesel", "HVO", "HVO100", "Blank diesel", "Biodiesel", "Miljødiesel", "miles D", "Diesel Gold", "B-diesel", "XTL".
- "diesel_avgiftsfri" = avgiftsfri/farget diesel. På tavlen: "FD", "Farget", "Avgiftsfri", "Anleggsdiesel".

Bruk sunn fornuft: uansett hva produktet heter, avgjør om det er bensin 95, bensin 98, diesel eller avgiftsfri diesel.
Noen tavler viser bare 2–3 typer. Dette er normalt. Sett null for typer som ikke finnes på tavlen.
I de aller fleste tilfeller er bare 2 prisrader synlige. Hvis bare 2 rader er synlige, er det som hovedregel bensin 95 og diesel, med mindre etikettene tydelig viser noe annet.
Hvis 3 prisrader er synlige, er det som hovedregel bensin 95, bensin 98 og diesel. Det finnes ingen fast plassering for 98 på skiltet. Stol alltid mest på etiketten på hver rad, ikke på vertikal rekkefølge.

Arbeidsmåte:
1. Finn først selve prisradene visuelt. Se etter en rad som inneholder både drivstoffetikett og en pris.
2. Les etiketten på raden først, og les deretter prisen på samme rad.
3. Match radene til feltene i JSON:
   - "95" eller "miles 95" -> bensin
   - "98", "V-Power", "miles 98" -> bensin98
   - "D", "Diesel", "miles D" -> diesel
   - "FD", "Avgiftsfri", "Farget" -> diesel_avgiftsfri
4. Hvis bare 1–2 prisrader er synlige, er dette normalt. Returner disse og sett resten til null.
5. Prioriter tydelig etikett + tydelig pris på samme rad over generelle antakelser.
6. Ikke flytt en pris fra én rad til en annen bare fordi prisnivået virker mer sannsynlig. Hvis raden tydelig viser "D", skal den raden mappes til diesel. Hvis raden tydelig viser "95", skal den raden mappes til bensin.
7. Hvis en tavle har to synlige rader, og den øverste raden er merket "D" mens nederste er merket "95", skal øverste pris være diesel og nederste pris være bensin.
8. Hvis en tavle har to synlige rader og etikettene er delvis uklare, anta bensin 95 og diesel før du vurderer bensin98 eller avgiftsfri diesel.
9. Hvis en tavle har tre synlige rader, anta som hovedregel at de tre typene er bensin 95, bensin 98 og diesel.
10. Ved tre synlige rader: ikke anta at 98 ligger på en bestemt rad. Bruk etiketten på hver rad for å avgjøre hvilken pris som er 95, 98 og diesel.

Prislogikk (bruk dette aktivt til å korrigere lesefeil):
- Priser er ALLTID mellom 15.00 og 35.00 kr/liter.
- bensin98 er ALLTID dyrere enn bensin (95) — typisk 1–4 kr mer. Eks: bensin=18.79 → bensin98 må være > 18.79. Hvis du har lest bensin98 < bensin, er noe feil — se gjennom sifrene på nytt.
- Diesel er vanligvis billigere enn eller omtrent lik bensin 95.
- Avgiftsfri diesel er ALLTID billigst av alle — typisk 5–10 kr under vanlig diesel. Hvis du har lest avgiftsfri diesel som dyrere enn diesel, er noe feil — sett null for den.

Format:
- Desimaltall med punktum (f.eks. 21.35)
- Priser er ALLTID på formen XX.XX — nøyaktig to siffer før og to siffer etter desimaltegnet.
- Eksempler på korreksjon: "2608" → 26.08, "6.08" → sannsynligvis 26.08, "260.8" → 26.08. Verdier som ikke lar seg korrigere til XX.XX i området 15–35 — sett null.
- Sett null for typer du ikke finner

Kjede:
- "kjede" = kjedelogo eller -navn synlig i bildet (f.eks. "Circle K", "Shell", "Esso"). Ellers null.

Nøyaktighet — LED-display:
- Røde/oransje LED-display: sifrene 1 og 7 forveksles svært lett. Sjekk: har sifferet et topphorisontalt segment? Da er det trolig 7, ikke 1. Eks: "18.19" der 95-oktan er i nærheten av 21.29 (98-oktan), er feil — den laveste prisen for 95 kan gjerne være 18.79 (7 lest som 1).
- 8 og 9 forveksles svært ofte på LED-skilt. Sjekk spesielt nedre venstre segment: hvis nedre venstre segment er tent, er sifferet trolig 8; hvis nedre venstre segment mangler mens øvre/midtre/nedre og høyre side er tent, er det trolig 9. Ikke velg 8 eller 9 uten å kontrollere dette segmentet.
- 6 og 8, 3 og 8, 9 og 5 forveksles også på LED. Bruk alltid prislogikken over til å velge riktig siffer.
- I tall som ligner "20.19" på røde LED-skilt, vurder alltid om tredje siffer egentlig er 7 og tallet derfor er "20.79". Dette er en vanlig feil.
- Returner null kun hvis prisen ikke lar seg tolke til et plausibelt XX.XX-tall i området 15–35 selv etter korreksjonsforsøk.

Ekstra regler for robusthet:
- Ignorer all tekst som ikke er drivstofftype eller pris, som bilvask, tilbud, kaffe, åpningstider og lignende.
- Hvis du ikke sikkert klarer å koble en pris til riktig drivstofftype, bruk null for den typen.
- Hvis du finner 2–4 plausible priser, men er usikker på én av dem, returner de sikre prisene og bruk null for den usikre.
- Sett "confidence" til low, medium eller high.
- Sett "uncertain_fields" til en liste med feltnavn du er usikker på, ellers [].

Eksempler:
Eksempel 1:
- Rad 1 viser "95 miles" og prisen "15.99"
- Rad 2 viser "D miles" og prisen "20.97"
- Ingen andre prisrader er synlige
Svar:
{"bensin": 15.99, "diesel": 20.97, "bensin98": null, "diesel_avgiftsfri": null, "kjede": "Circle K", "confidence": "high", "uncertain_fields": []}

Eksempel 2:
- Rad 1 viser "95" og "22.49"
- Rad 2 viser "98" og "24.39"
- Rad 3 viser "Diesel" og "21.79"
Svar:
{"bensin": 22.49, "diesel": 21.79, "bensin98": 24.39, "diesel_avgiftsfri": null, "kjede": null, "confidence": "high", "uncertain_fields": []}

Eksempel 3:
- Du ser en tydelig dieselrad, men tallene på 95-raden er uklare
Svar:
{"bensin": null, "diesel": 19.87, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "medium", "uncertain_fields": ["bensin"]}

Eksempel 4:
- Tavlen viser to rader
- Øverste rad er merket "D" og prisen ser ut som "20.79"
- Nederste rad er merket "95" og prisen er "15.89"
- Ikke bytt om radene
Svar:
{"bensin": 15.89, "diesel": 20.79, "bensin98": null, "diesel_avgiftsfri": null, "kjede": "Uno-X", "confidence": "high", "uncertain_fields": []}

Eksempel 5:
- Tavlen viser bare to prisrader
- Du ser ingen tydelig 98-rad og ingen tydelig avgiftsfri-rad
- Etikettene er litt vanskelige, men bildet ligner et vanlig norsk skilt med 95 og diesel
Svar:
{"bensin": 19.99, "diesel": 20.79, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "medium", "uncertain_fields": []}

Eksempel 6:
- Tavlen viser tre prisrader
- De tre radene er 95, 98 og diesel
- 98 kan stå øverst, i midten eller nederst
- Bruk etiketten på hver rad, ikke fast radplass
Svar:
{"bensin": 21.49, "diesel": 20.89, "bensin98": 23.29, "diesel_avgiftsfri": null, "kjede": null, "confidence": "medium", "uncertain_fields": []}
"""


_OCR_PROMPT_FALLBACK = """Du leser et enkelt norsk drivstoffskilt med vanligvis 2 eller 3 prisrader.

Oppgaven er mye enklere enn vanlig:
- Finn bare synlige prisrader.
- Les etiketten til venstre og prisen på samme rad.
- Returner kun prisene du er rimelig sikker på.

Viktige regler:
- Hvis du ser bare 2 rader, er det nesten alltid bensin 95 og diesel.
- Hvis du ser 3 rader, er det vanligvis bensin 95, bensin 98 og diesel.
- Det finnes ingen fast vertikal plassering for 98.
- Hvis en rad tydelig er merket "95", skal den mappes til bensin.
- Hvis en rad tydelig er merket "98", skal den mappes til bensin98.
- Hvis en rad tydelig er merket "D" eller "Diesel", skal den mappes til diesel.
- Ikke gjett avgiftsfri diesel hvis den ikke er tydelig synlig.
- Røde LED-tall kan forveksle 1 og 7. Vurder alltid om 20.19 egentlig er 20.79 hvis segmentene ligner.
- Prisene skal være mellom 15.00 og 35.00.
- Hvis du kun klarer å lese 95 og diesel, er det et gyldig svar.

Returner KUN gyldig JSON uten annen tekst:
{"bensin": null, "diesel": null, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "low", "uncertain_fields": []}
"""


_OCR_PROMPT_HAIKU_EKSTRA = """
Ekstra instruks for Haiku:
- Tenk rad-for-rad, ikke bilde-for-bilde. Finn først rektangelet med prisdisplayet, deretter hver horisontale prisrad.
- Tell synlige prisrader: vanligvis 2, av og til 3. Ikke let etter mange andre tall.
- Hvis to rader er synlige og etikettene er uklare eller delvis beskåret, er beste antakelse 95 oktan + diesel. Bruk etiketter hvis de er synlige, ellers bruk øverste synlige pris som bensin og nederste synlige pris som diesel.
- Hvis tre rader er synlige og etikettene er uklare, er beste antakelse 95 oktan, 98 oktan og diesel. Bruk etiketter hvis de er synlige; 98 har ingen fast plass.
- Røde LED-tall er punktmatrise/segmenter. Ikke les "20.79" som "2019" eller "20.19" hvis det tredje sifferet har tydelig 7-form.
- Sjekk 8 og 9 ekstra nøye: 8 har nedre venstre del/segment, 9 mangler vanligvis nedre venstre del/segment.
- Alle priser skal normaliseres til XX.XX. Eksempel: 1599 -> 15.99, 1949 -> 19.49, 2079 -> 20.79.
- Det er bedre å returnere to sikre priser med confidence "medium" enn å returnere alle null.
- Returner likevel null for felt som ikke har en synlig eller plausibel rad.
"""


def _lag_ocr_prompt(forventet_kjede=None, haiku=False):
    prompt = _OCR_PROMPT_BASE
    if haiku:
        prompt += _OCR_PROMPT_HAIKU_EKSTRA
    if forventet_kjede:
        return (
            prompt +
            f'\nMykt hint: bildet er sannsynligvis fra kjeden "{forventet_kjede}". '
            'Bruk dette bare som støtte hvis logo/visuell profil stemmer. '
            'Hvis bildet tydelig viser en annen kjede, stol på bildet, ikke hintet.'
        )
    return prompt


def _parse_ocr_pris(verdi):
    if verdi is None:
        return None
    if isinstance(verdi, (int, float)):
        tall = float(verdi)
        if _OCR_MIN_PRIS <= tall <= _OCR_MAX_PRIS:
            return round(tall, 2)
        if 1500 <= tall <= 3500:
            return round(tall / 100, 2)
        return None

    tekst = str(verdi).strip().lower()
    if not tekst or tekst in ('null', 'none', 'ukjent', 'unknown'):
        return None

    tekst = tekst.replace(',', '.')
    tekst = re.sub(r'[^0-9.]', '', tekst)
    if not tekst:
        return None

    if re.fullmatch(r'\d{4}', tekst):
        tall = int(tekst) / 100
    elif re.fullmatch(r'\d{2}\.\d{2}', tekst) or re.fullmatch(r'\d{1,2}\.\d{2}', tekst):
        tall = float(tekst)
    else:
        return None

    if not (_OCR_MIN_PRIS <= tall <= _OCR_MAX_PRIS):
        return None
    return round(tall, 2)


def _har_ocr_priser(data: dict) -> bool:
    return any(data.get(felt) is not None for felt in ('bensin', 'diesel', 'bensin98', 'diesel_avgiftsfri'))


def _normaliser_ocr_resultat(data):
    if not isinstance(data, dict):
        raise ValueError('OCR-svar må være et objekt')

    resultat = {
        'bensin': _parse_ocr_pris(data.get('bensin')),
        'diesel': _parse_ocr_pris(data.get('diesel')),
        'bensin98': _parse_ocr_pris(data.get('bensin98')),
        'diesel_avgiftsfri': _parse_ocr_pris(data.get('diesel_avgiftsfri')),
        'kjede': None,
    }

    kjede = data.get('kjede')
    if isinstance(kjede, str):
        kjede = kjede.strip()
        if kjede:
            resultat['kjede'] = kjede[:60]

    if resultat['bensin'] is not None and resultat['bensin98'] is not None and resultat['bensin98'] < resultat['bensin']:
        diff = resultat['bensin'] - resultat['bensin98']
        if 0.2 <= diff <= 4.5:
            resultat['bensin'], resultat['bensin98'] = resultat['bensin98'], resultat['bensin']
        else:
            resultat['bensin98'] = None

    if resultat['diesel'] is not None and resultat['diesel_avgiftsfri'] is not None and resultat['diesel_avgiftsfri'] > resultat['diesel']:
        diff = resultat['diesel_avgiftsfri'] - resultat['diesel']
        if 2.0 <= diff <= 12.0:
            resultat['diesel'], resultat['diesel_avgiftsfri'] = resultat['diesel_avgiftsfri'], resultat['diesel']
        else:
            resultat['diesel_avgiftsfri'] = None

    if resultat['diesel_avgiftsfri'] is not None:
        andre = [v for k, v in resultat.items() if k in ('bensin', 'bensin98', 'diesel') and v is not None]
        if andre and resultat['diesel_avgiftsfri'] >= min(andre):
            resultat['diesel_avgiftsfri'] = None

    return resultat


def _haiku_json_request(bilde_b64, content_type, prompt):
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY ikke satt')
    resp = httpx.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 512,
            'temperature': 0,
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': content_type,
                            'data': bilde_b64,
                        }
                    }
                ]
            }]
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    tekst = resp.json()['content'][0]['text'].strip()
    if tekst.startswith('```'):
        tekst = tekst.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return _normaliser_ocr_resultat(json.loads(tekst))


def _ocr_via_haiku(bilde_b64, content_type, forventet_kjede=None):
    primar = _haiku_json_request(
        bilde_b64,
        content_type,
        _lag_ocr_prompt(forventet_kjede, haiku=True),
    )
    if _har_ocr_priser(primar):
        return primar

    fallback_prompt = _OCR_PROMPT_FALLBACK + _OCR_PROMPT_HAIKU_EKSTRA
    if forventet_kjede:
        fallback_prompt += (
            f'\nMykt hint: skiltet er sannsynligvis fra kjeden "{forventet_kjede}". '
            'Bruk bare dette hvis logo eller design stemmer.'
        )
    fallback = _haiku_json_request(bilde_b64, content_type, fallback_prompt)
    return fallback if _har_ocr_priser(fallback) else primar


def _gemini_json_request(bilde_b64, content_type, prompt):
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError('GEMINI_API_KEY ikke satt')
    modeller = os.environ.get('GEMINI_MODELLER') or os.environ.get('GEMINI_MODELL', 'gemini-flash-latest')
    siste_feil = None
    for modell in [m.strip() for m in modeller.split(',') if m.strip()]:
        try:
            resp = httpx.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent',
                params={'key': api_key},
                headers={'content-type': 'application/json'},
                json={
                    'contents': [{
                        'parts': [
                            {'inline_data': {'mime_type': content_type, 'data': bilde_b64}},
                            {'text': prompt},
                        ]
                    }],
                    'generationConfig': {
                        'maxOutputTokens': 256,
                        'temperature': 0,
                        'responseMimeType': 'application/json',
                        'responseSchema': {
                            'type': 'OBJECT',
                            'properties': {
                                'bensin': {'type': 'NUMBER', 'nullable': True},
                                'diesel': {'type': 'NUMBER', 'nullable': True},
                                'bensin98': {'type': 'NUMBER', 'nullable': True},
                                'diesel_avgiftsfri': {'type': 'NUMBER', 'nullable': True},
                                'kjede': {'type': 'STRING', 'nullable': True},
                                'confidence': {'type': 'STRING', 'enum': ['low', 'medium', 'high']},
                                'uncertain_fields': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
                            },
                            'required': ['bensin', 'diesel', 'bensin98', 'diesel_avgiftsfri', 'kjede', 'confidence', 'uncertain_fields'],
                        },
                    },
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            tekst = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            if tekst.startswith('```'):
                tekst = tekst.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            resultat = json.loads(tekst)
            resultat['_modell'] = modell
            return resultat
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
            siste_feil = e
            logger.warning(f'Gemini OCR feilet med modell={modell}: {e}')
    if isinstance(siste_feil, httpx.HTTPError):
        raise siste_feil
    if siste_feil:
        raise RuntimeError(f'Kunne ikke tolke Gemini-svar: {siste_feil}')
    raise ValueError('Ingen Gemini-modeller konfigurert')


def _ocr_via_gemini(bilde_b64, content_type, forventet_kjede=None):
    primar = _normaliser_ocr_resultat(
        _gemini_json_request(bilde_b64, content_type, _lag_ocr_prompt(forventet_kjede))
    )
    if _har_ocr_priser(primar):
        return primar

    fallback_prompt = _OCR_PROMPT_FALLBACK
    if forventet_kjede:
        fallback_prompt += (
            f'\nMykt hint: skiltet er sannsynligvis fra kjeden "{forventet_kjede}". '
            'Bruk bare dette hvis logo eller design stemmer.'
        )
    fallback = _normaliser_ocr_resultat(
        _gemini_json_request(bilde_b64, content_type, fallback_prompt)
    )
    return fallback if _har_ocr_priser(fallback) else primar


@api_bp.route('/api/gjenkjenn-priser', methods=['POST'])
@krever_innlogging
def gjenkjenn_priser():
    """Gjenkjenn drivstoffpriser fra bilde via AI Vision API.
    Modell styres av env-var OCR_MODELL (haiku|gemini). Kun for admin/moderator."""
    bruker_id = session.get('bruker_id')
    bruker = finn_bruker_id(bruker_id)
    if not bruker or not (bruker.get('er_admin') or har_rolle(bruker, 'moderator') or har_rolle(bruker, 'kamera')):
        return jsonify({'error': 'Ingen tilgang til kamera'}), 403

    # Rate limit: maks N kall per bruker per dag
    i_dag = datetime.now().date()
    dato, antall = _ocr_bruk.get(bruker_id, (i_dag, 0))
    if dato != i_dag:
        antall = 0
    if antall >= _OCR_GRENSE_PER_DAG:
        return jsonify({'error': f'Maks {_OCR_GRENSE_PER_DAG} bildeanalyser per dag'}), 429
    _ocr_bruk[bruker_id] = (i_dag, antall + 1)

    fil = request.files.get('bilde')
    if not fil:
        return jsonify({'error': 'Ingen bilde lastet opp'}), 400

    bilde_data = fil.read()
    if len(bilde_data) > 5 * 1024 * 1024:
        return jsonify({'error': 'Bilde for stort (maks 5 MB)'}), 400

    content_type = fil.content_type or 'image/jpeg'
    if content_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif'):
        content_type = 'image/jpeg'

    bilde_b64 = base64.b64encode(bilde_data).decode('utf-8')
    ocr_modell = os.environ.get('OCR_MODELL', 'haiku').lower()
    forventet_kjede = (request.form.get('forventet_kjede') or '').strip()[:60] or None

    try:
        if ocr_modell == 'gemini':
            try:
                priser = _ocr_via_gemini(bilde_b64, content_type, forventet_kjede=forventet_kjede)
                brukt_modell = priser.get('_modell') or 'gemini'
                if not _har_ocr_priser(priser):
                    logger.warning(f'Gemini OCR fant ingen priser for bruker={bruker_id}; prøver Haiku fallback')
                    priser = _ocr_via_haiku(bilde_b64, content_type, forventet_kjede=forventet_kjede)
                    brukt_modell = 'haiku-fallback'
            except (ValueError, httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError, RuntimeError) as e:
                logger.warning(f'Gemini OCR feilet for bruker={bruker_id}; prøver Haiku fallback: {e}')
                priser = _ocr_via_haiku(bilde_b64, content_type, forventet_kjede=forventet_kjede)
                brukt_modell = 'haiku-fallback'
        else:
            priser = _ocr_via_haiku(bilde_b64, content_type, forventet_kjede=forventet_kjede)
            brukt_modell = 'haiku'
        logger.info(f'OCR-gjenkjenning: bruker={bruker_id} modell={brukt_modell} resultat={priser}')
        priser['_modell'] = brukt_modell
        return jsonify(priser)
    except ValueError as e:
        logger.error(f'OCR konfigurasjonsfeil: {e}')
        return jsonify({'error': 'AI-tjeneste ikke konfigurert'}), 503
    except httpx.HTTPError as e:
        logger.error(f'OCR API-feil ({ocr_modell}): {e}')
        return jsonify({'error': 'AI-tjeneste midlertidig utilgjengelig'}), 503
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.error(f'OCR parse-feil ({ocr_modell}): {e}')
        return jsonify({'error': 'Kunne ikke tolke AI-svar'}), 502


@api_bp.route('/api/ocr-statistikk', methods=['POST'])
@krever_innlogging
def ocr_statistikk():
    """Logg OCR-statistikk: tesseract vs claude, hva brukeren faktisk lagret."""
    data = request.get_json(silent=True) or {}
    bruker_id = session.get('bruker_id')

    with get_conn() as conn:
        conn.execute('''INSERT INTO ocr_statistikk
            (bruker_id, kilde, tesseract_ok, tesseract_ms, tesseract_resultat,
             tesseract_raatekst, claude_ok, claude_ms, claude_resultat,
             lagret_priser, tesseract_feil, claude_feil)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (bruker_id,
             data.get('kilde'),
             1 if data.get('tesseract_ok') else 0,
             data.get('tesseract_ms'),
             json.dumps(data.get('tesseract_resultat')) if data.get('tesseract_resultat') else None,
             (data.get('tesseract_raatekst') or '')[:2000],
             1 if data.get('claude_ok') else 0,
             data.get('claude_ms'),
             json.dumps(data.get('claude_resultat')) if data.get('claude_resultat') else None,
             json.dumps(data.get('lagret')) if data.get('lagret') else None,
             data.get('tesseract_feil'),
             data.get('claude_feil')))

    return jsonify({'ok': True})
