"""API-ruter: stasjoner, priser, stedssøk, statistikk."""

import logging
import math
import os
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import time

import httpx
from flask import Blueprint, request, jsonify, make_response, session

import base64
import io
import json
import re
import unicodedata

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import numpy as np
except ImportError:  # pragma: no cover - produksjon har Pillow, fallback bruker originalbildet
    Image = ImageEnhance = ImageFilter = np = None

from db import (get_stasjoner_med_priser, lagre_pris, bekreft_pris, logg_visning,
                antall_stasjoner_med_pris, finn_bruker_id, DB_PATH,
                opprett_stasjon, hent_billigste_priser_24t,
                antall_prisoppdateringer_24t, meld_stasjon_nedlagt,
                get_conn, hent_innstilling, hent_toppliste, hent_toppliste_uke,
                hent_min_plassering, logg_blogg_visning,
                legg_til_endringsforslag, unike_enheter_per_dag,
                prisoppdateringer_per_time_24t,
                prisoppdateringer_rullende_24t_uke,
                har_rolle, hent_kjede_snitt_24t,
                sjekk_rate_limit, logg_rate_limit, hent_anonym_bruker_id,
                mask_stasjon_priser_for_tilganger,
                hent_preferences, sett_preferences)

logger = logging.getLogger('drivstoff')

api_bp = Blueprint('api', __name__)

_PRIS_MIN_INTERVALL = 300  # sekunder (5 min)
_PRIS_MIN = 14.0
_PRIS_MAX = 37.0

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


_STASJONER_EXPORT_NS = uuid.UUID('b3d9e4a1-7c2f-4e8b-a6d1-0f5c3e2b1a9d')

_KJEDE_TIL_BRAND = {
    'best': 'BEST',
    'bondetanken': 'BONDETANKEN',
    'bunker oil': 'BUNKER_OIL',
    'buskerud olje': 'BUSKERUD_OLJE',
    'circle k': 'CIRCLE_K',
    'coop': 'COOP',
    'dalholen bensin': 'DALHOLEN_BENSIN',
    'driv': 'DRIV',
    'esso': 'ESSO',
    'fina': 'FINA',
    'fuel4u': 'FUEL4U',
    'haltbakk express': 'HALTBAKK_EXPRESS',
    'haugaland olje': 'HAUGALAND_OLJE',
    'helgeland oljeservice': 'HELGELAND_OLJESERVICE',
    'knapphus': 'KNAPPHUS',
    'lyse': 'LYSE',
    'max': 'MAX',
    'mh24': 'MH24',
    'minol': 'MINOL',
    'narbutikken': 'NARBUTIKKEN',
    'oljeleverandøren': 'OLJELEVERANDOREN',
    'oljeleverandoren': 'OLJELEVERANDOREN',
    'preem': 'PREEM',
    'st1': 'ST1',
    'tank': 'TANK',
    'tanken': 'TANKEN',
    'trønder oil': 'TRONDER_OIL',
    'tronder oil': 'TRONDER_OIL',
    'uno-x': 'UNO_X',
    'yx': 'YX',
}


def _kjede_til_brand(kjede):
    if not kjede:
        return 'INDEPENDENT'
    return _KJEDE_TIL_BRAND.get(kjede.strip().lower(), 'INDEPENDENT')


@api_bp.route('/api/v1/stasjoner')
def eksporter_stasjoner():
    nøkkel = request.headers.get('X-API-Key', '')
    if not nøkkel:
        return jsonify({'error': 'Ugyldig eller manglende API-nøkkel'}), 403

    gyldig_partnernøkkel = False
    with get_conn() as conn:
        partner = conn.execute(
            'SELECT 1 FROM api_nøkler WHERE nøkkel = ? AND aktiv = 1',
            (nøkkel,)
        ).fetchone()
        gyldig_partnernøkkel = partner is not None

    # Behold støtte for eldre intern integrasjon som fortsatt bruker env-nøkkel.
    stations_api_key = os.environ.get('STATIONS_API_KEY', '')
    if not gyldig_partnernøkkel and (not stations_api_key or nøkkel != stations_api_key):
        return jsonify({'error': 'Ugyldig eller manglende API-nøkkel'}), 403

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT id, navn, kjede, lat, lon, osm_id,
                      har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri
               FROM stasjoner
               WHERE godkjent = 1
                 AND (land IS NULL OR land = 'NO')
               ORDER BY id'''
        ).fetchall()

    stasjoner = []
    for r in rows:
        fuel_types = []
        if r['har_bensin']:
            fuel_types.append('GASOLINE_95')
        if r['har_bensin98']:
            fuel_types.append('GASOLINE_98')
        if r['har_diesel']:
            fuel_types.append('DIESEL')
        if r['har_diesel_avgiftsfri']:
            fuel_types.append('COLORED_DIESEL')
        if not fuel_types:
            fuel_types = ['GASOLINE_95', 'DIESEL']

        stasjoner.append({
            'id': str(uuid.uuid5(_STASJONER_EXPORT_NS, str(r['id']))),
            'osm_id': r['osm_id'],
            'brand': _kjede_til_brand(r['kjede']),
            'location': r['navn'],
            'address': '',
            'lat': r['lat'],
            'lon': r['lon'],
            'fuel_types': fuel_types,
        })

    return jsonify(stasjoner)


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
    anonym_tillatt = hent_innstilling('anonym_innlegging') == '1'
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return jsonify({'innlogget': False, 'anonym_innlegging': anonym_tillatt})
    bruker = finn_bruker_id(bruker_id)
    if not bruker:
        session.clear()
        return jsonify({'innlogget': False, 'anonym_innlegging': anonym_tillatt})
    roller = (bruker.get('roller') or '').split()
    if har_rolle(bruker, 'kamera') and 'kamera' not in roller:
        roller.append('kamera')
    return jsonify({'innlogget': True, 'brukernavn': bruker['brukernavn'],
                    'kallenavn': bruker.get('kallenavn') or '', 'bruker_id': bruker['id'],
                    'er_admin': bool(bruker['er_admin']),
                    'roller': roller, 'anonym_innlegging': anonym_tillatt,
                    'preferences': hent_preferences(bruker['id'])})


@api_bp.route('/api/bruker/preferences', methods=['PUT'])
def sett_bruker_preferences():
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return jsonify({'error': 'Ikke innlogget'}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Ugyldig data'}), 400
    # Tillat kun kjente nøkler for å unngå at klienten lagrer vilkårlig data
    _TILLATNE_NØKLER = {'bensin', 'bensin98', 'diesel', 'diesel_avgiftsfri',
                        'radius', 'radiusValg', 'radiusEgen', 'kartvisning', 'rabattkort'}
    renset = {k: v for k, v in data.items() if k in _TILLATNE_NØKLER}
    # Valider og rens rabattkort-verdier
    if 'rabattkort' in renset:
        rb = renset['rabattkort']
        _GYLDIGE_KJEDER = {'Circle K', 'Uno-X', 'YX', 'Esso', 'St1'}
        if not isinstance(rb, dict):
            renset['rabattkort'] = {}
        else:
            renset['rabattkort'] = {
                k: max(0, min(500, int(v)))
                for k, v in rb.items()
                if k in _GYLDIGE_KJEDER and isinstance(v, (int, float)) and v > 0
            }
    sett_preferences(bruker_id, renset)
    return jsonify({'ok': True})


@api_bp.route('/api/stasjoner')
def stasjoner():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius_km = request.args.get('radius', default=30, type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'lat og lon er påkrevd'}), 400
    if not er_i_norge(lat, lon):
        return jsonify({'error': 'Kun tilgjengelig i Norge', 'utenfor': True}), 400

    if radius_km is None or not math.isfinite(radius_km):
        radius_km = 30
    radius_m = max(100, min(round(radius_km * 1000), 100_000))
    limit = 50 if radius_km >= 50 else 30
    data = get_stasjoner_med_priser(lat, lon, radius_m=radius_m, limit=limit)
    return jsonify({'stasjoner': data})


_stedssok_cache: dict[str, tuple[float, list]] = {}
_STEDSSOK_TTL = 600  # sekunder


def _normaliser_soketekst(tekst: str) -> str:
    tekst = (tekst or '').strip().lower()
    erstatninger = {
        'æ': 'ae',
        'ø': 'o',
        'å': 'a',
    }
    for gammel, ny in erstatninger.items():
        tekst = tekst.replace(gammel, ny)
    tekst = unicodedata.normalize('NFKD', tekst)
    tekst = ''.join(ch for ch in tekst if not unicodedata.combining(ch))
    tekst = re.sub(r'[^a-z0-9]+', ' ', tekst)
    return ' '.join(tekst.split())


def _matcher_stasjonssok(query: str, navn: str, kjede: str) -> bool:
    query_norm = _normaliser_soketekst(query)
    if len(query_norm) < 2:
        return False

    haystack = _normaliser_soketekst(f'{navn} {kjede}')
    if not haystack:
        return False
    if query_norm in haystack:
        return True

    tokens = [token for token in query_norm.split() if len(token) >= 2]
    return bool(tokens) and all(token in haystack for token in tokens)


@api_bp.route('/api/stedssok')
def stedssok():
    q_raw = request.args.get('q', '').strip()
    q = _normaliser_soketekst(q_raw)
    if len(q) < 2:
        return jsonify([])

    now = time.monotonic()
    cached = _stedssok_cache.get(q)
    if cached and now - cached[0] < _STEDSSOK_TTL:
        return jsonify(cached[1])

    # Søk i egne stasjoner
    stasjons_treff = []
    try:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rader = conn.execute(
                '''SELECT id, navn, kjede, lat, lon FROM stasjoner
                   WHERE godkjent = 1 AND (land IS NULL OR land = 'NO')
                ''',
            ).fetchall()
        for r in rader:
            if not _matcher_stasjonssok(q_raw, r['navn'] or '', r['kjede'] or ''):
                continue
            visningsnavn = f"{r['navn']}" + (f" ({r['kjede']})" if r['kjede'] else "")
            stasjons_treff.append({
                'navn': visningsnavn,
                'lat': r['lat'],
                'lon': r['lon'],
                'type': 'stasjon',
                'id': r['id'],
            })
        stasjons_treff = stasjons_treff[:5]
    except Exception as e:
        logger.warning(f'Stasjonssøk feilet: {e}')

    # Søk i Photon (eksterne steder)
    steds_treff = []
    try:
        resp = httpx.get(
            'https://photon.komoot.io/api/',
            params={'q': q, 'limit': 5, 'bbox': '4.0,57.0,31.5,71.5'},
            headers={'User-Agent': 'drivstoffpriser/1.0 (hobby)'},
            timeout=8,
        )
        features = resp.json().get('features', [])
        for f in features:
            props = f.get('properties', {})
            if props.get('countrycode', '').upper() != 'NO':
                continue
            coords = f.get('geometry', {}).get('coordinates', [])
            if len(coords) < 2:
                continue
            deler = [props.get(k) for k in ('name', 'county', 'state', 'country') if props.get(k)]
            navn = ', '.join(dict.fromkeys(deler))
            steds_treff.append({'navn': navn, 'lat': float(coords[1]), 'lon': float(coords[0]), 'type': 'sted'})
    except Exception as e:
        logger.warning(f'Stedssøk feilet: {e}')

    # Fjern Photon-treff som er nær en av våre stasjoner (< 200m)
    for s in stasjons_treff:
        steds_treff = [
            st for st in steds_treff
            if abs(st['lat'] - s['lat']) + abs(st['lon'] - s['lon']) > 0.002
        ]

    results = stasjons_treff + steds_treff
    _stedssok_cache[q] = (now, results)
    return jsonify(results)


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


def _hent_osrm_rute(fra, til, via=None):
    punkter = [fra]
    if via:
        punkter.append(via)
    punkter.append(til)
    koordinater = ';'.join(f'{p["lon"]},{p["lat"]}' for p in punkter)
    resp = httpx.get(
        f'https://router.project-osrm.org/route/v1/driving/{koordinater}',
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


def _hent_graphhopper_rute(fra, til, via=None):
    api_key = os.environ.get('GRAPHHOPPER_API_KEY', '')
    params = [('vehicle', 'car'), ('locale', 'no'), ('key', api_key),
              ('steps', 'false'), ('points_encoded', 'false')]
    for p in ([fra] + ([via] if via else []) + [til]):
        params.append(('point', f'{p["lat"]},{p["lon"]}'))
    resp = httpx.get(
        'https://graphhopper.com/api/1/route',
        params=params,
        headers={'User-Agent': 'drivstoffpriser/1.0 rutepris'},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    paths = data.get('paths') or []
    if not paths:
        return None
    coords = paths[0].get('points', {}).get('coordinates', [])
    punkter = [(float(lat), float(lon)) for lon, lat in coords]
    return {'punkter': punkter, 'km': paths[0].get('distance', 0) / 1000, 'min': paths[0].get('time', 0) / 60000}


def _hent_rute(fra, til, via=None):
    motor = os.environ.get('RUTE_MOTOR', 'graphhopper').lower()
    if motor == 'osrm':
        return _hent_osrm_rute(fra, til, via)
    try:
        return _hent_graphhopper_rute(fra, til, via)
    except Exception as e:
        logger.warning(f'GraphHopper feilet, prøver OSRM som fallback: {e}')
        return _hent_osrm_rute(fra, til, via)


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
    return [mask_stasjon_priser_for_tilganger(dict(r)) for r in rows]


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
        tidspunkt = s.get(f'{drivstoff}_tidspunkt')
        if not tidspunkt or tidspunkt < (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S'):
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
    via_txt = (data.get('via') or '').strip()
    drivstoff = data.get('drivstoff') or 'diesel'
    if drivstoff not in {'bensin', 'bensin98', 'diesel', 'diesel_avgiftsfri'}:
        return jsonify({'error': 'Ugyldig drivstofftype'}), 400

    try:
        maks_avvik_km = float(data.get('maks_avvik_km', 0.5))
    except (TypeError, ValueError):
        maks_avvik_km = 0.5
    maks_avvik_km = max(0.5, min(maks_avvik_km, 15))

    if not fra_txt or not til_txt:
        return jsonify({'error': 'Fra og til er påkrevd'}), 400

    try:
        fra = _geokod_rutepunkt(fra_txt)
        til = _geokod_rutepunkt(til_txt)
        if not fra or not til:
            return jsonify({'error': 'Fant ikke fra- eller tilsted i Norge'}), 400
        via = _geokod_rutepunkt(via_txt) if via_txt else None
        if via_txt and not via:
            return jsonify({'error': 'Fant ikke via-sted i Norge'}), 400

        rute = _hent_rute(fra, til, via)
        if not rute:
            return jsonify({'error': 'Fant ingen kjørerute'}), 400

        treff = _finn_billige_langs_rute(rute, drivstoff, maks_avvik_km)
        return jsonify({
            'fra': fra,
            'til': til,
            'via': via,
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
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius = request.args.get('radius', type=float)
    priser_24t = hent_billigste_priser_24t(lat=lat, lon=lon, radius_km=radius)
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


@api_bp.route('/api/kjede-snitt')
def kjede_snitt():
    return jsonify(hent_kjede_snitt_24t())


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



_ANONYM_PRIS_MAKS = 10
_ANONYM_PRIS_VINDU = 3600  # sekunder (1 time)
_AVVIK_GRENSE_ADVARSEL = 0.30   # advarsel i frontend + epost til admin
_AVVIK_GRENSE_ANONYM   = 0.40   # hard avvisning for anonyme


def _sjekk_prisavvik(stasjon_id, bensin, diesel, bensin98, diesel_avgiftsfri, grense):
    """Returnerer liste med avvik-strenger hvis noen pris avviker mer enn grensen, ellers tom liste."""
    with get_conn() as conn:
        rad = conn.execute(
            '''SELECT bensin, diesel, bensin98, diesel_avgiftsfri FROM priser
               WHERE stasjon_id = ? ORDER BY tidspunkt DESC LIMIT 1''',
            (stasjon_id,)
        ).fetchone()
    if not rad:
        return []
    par = [
        ('95 oktan',       bensin,            rad[0]),
        ('Diesel',         diesel,            rad[1]),
        ('98 oktan',       bensin98,          rad[2]),
        ('Avg.fri diesel', diesel_avgiftsfri, rad[3]),
    ]
    avvik = []
    for label, ny, gammel in par:
        if ny is not None and gammel is not None and gammel > 0:
            pst = abs(ny - gammel) / gammel
            if pst > grense:
                avvik.append(f'{label}: {gammel:.2f} → {ny:.2f} kr ({round(pst * 100)}%)')
    return avvik


def _varsle_prisavvik(stasjon_id, bruker_id, avvik_info, ip):
    """Send epost til admin om at noen har passert advarselvinduet med stor prisendring."""
    try:
        import resend
        with get_conn() as conn:
            navn_rad = conn.execute('SELECT navn FROM stasjoner WHERE id = ?', (stasjon_id,)).fetchone()
            stasjon_navn = navn_rad[0] if navn_rad else f'stasjon {stasjon_id}'
            bruker_rad = conn.execute('SELECT brukernavn FROM brukere WHERE id = ?', (bruker_id,)).fetchone()
            bruker_navn = bruker_rad[0] if bruker_rad else f'bruker_id={bruker_id}'
        linjer = ''.join(f'<li>{a}</li>' for a in avvik_info)
        resend.Emails.send({
            'from': 'Drivstoffpriser <noreply@ksalo.no>',
            'to': 'kjetil@vikebo.com',
            'subject': f'Prisavvik: {stasjon_navn}',
            'html': (
                f'<p>En bruker passerte advarselvinduet med stor prisendring.</p>'
                f'<p><strong>Stasjon:</strong> {stasjon_navn} (id={stasjon_id})<br>'
                f'<strong>Bruker:</strong> {bruker_navn}<br>'
                f'<strong>IP:</strong> {ip}</p>'
                f'<ul>{linjer}</ul>'
            ),
        })
    except Exception as e:
        logger.error(f'Varsling om prisavvik feilet: {e}')


@api_bp.route('/api/pris', methods=['POST'])
def oppdater_pris():
    bruker_id = session.get('bruker_id')
    anonym = not bruker_id
    if anonym:
        if hent_innstilling('anonym_innlegging') != '1':
            return jsonify({'error': 'Ikke innlogget'}), 401
        ip = request.remote_addr
        if sjekk_rate_limit('anonym_pris', ip, _ANONYM_PRIS_MAKS, _ANONYM_PRIS_VINDU):
            return jsonify({'error': 'For mange innlegginger. Prøv igjen senere.'}), 429
        bruker_id = hent_anonym_bruker_id()

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

    for navn, pris in (
        ('95 oktan', bensin),
        ('diesel', diesel),
        ('98 oktan', bensin98),
        ('avgiftsfri diesel', diesel_avgiftsfri),
    ):
        if pris is not None and not (_PRIS_MIN <= pris <= _PRIS_MAX):
            return jsonify({'error': f'{navn} må være mellom {_PRIS_MIN:g} og {_PRIS_MAX:g} kr'}), 400

    kilde = data.get('kilde') or None

    # Avvikssjekk mot siste kjente pris for stasjonen
    if anonym:
        avvik_anonym = _sjekk_prisavvik(stasjon_id, bensin, diesel, bensin98, diesel_avgiftsfri, _AVVIK_GRENSE_ANONYM)
        if avvik_anonym:
            logger.warning(
                f'Anonym prisinnlegging avvist (stort avvik): stasjon={stasjon_id} '
                f'ip={request.remote_addr} avvik={avvik_anonym}'
            )
            return jsonify({'error': 'Prisen avviker for mye fra siste kjente pris. Logg inn for å legge inn store prisendringer.'}), 400
    else:
        avvik_info = _sjekk_prisavvik(stasjon_id, bensin, diesel, bensin98, diesel_avgiftsfri, _AVVIK_GRENSE_ADVARSEL)
        if avvik_info:
            threading.Thread(
                target=_varsle_prisavvik,
                args=(stasjon_id, bruker_id, avvik_info, request.remote_addr),
                daemon=True,
            ).start()

    intervall = 0 if anonym else _PRIS_MIN_INTERVALL
    antall_oppgitte = sum(p is not None for p in (bensin, diesel, bensin98, diesel_avgiftsfri))
    tillat_korreksjon = not (kilde == 'bidrag' and antall_oppgitte == 1)
    lagret = lagre_pris(
        stasjon_id, bensin, diesel, bensin98,
        bruker_id=bruker_id,
        diesel_avgiftsfri=diesel_avgiftsfri,
        min_intervall=intervall,
        kilde=kilde,
        tillat_korreksjon=tillat_korreksjon,
    )
    if lagret:
        if anonym:
            logg_rate_limit('anonym_pris', request.remote_addr)
        logger.info(f'Pris lagret: stasjon={stasjon_id} bensin={bensin} diesel={diesel} bensin98={bensin98} diesel_avgiftsfri={diesel_avgiftsfri} bruker={bruker_id} kilde={kilde}')
        if bruker_id == 4494:
            logger.warning(f'system:anonym pris lagret: stasjon={stasjon_id} ip={request.remote_addr}')
    else:
        logger.info(f'Pris ignorert (rate limit): stasjon={stasjon_id} bruker={bruker_id}')
    return jsonify({'ok': True})


@api_bp.route('/api/bekreft-pris', methods=['POST'])
@krever_innlogging
def bekreft_en_pris():
    data = request.get_json(silent=True) or {}
    stasjon_id = data.get('stasjon_id')
    type_navn = data.get('type')

    if not stasjon_id or not type_navn:
        return jsonify({'error': 'stasjon_id og type er påkrevd'}), 400

    bruker_id = session.get('bruker_id')
    lagret = bekreft_pris(stasjon_id, type_navn, bruker_id, min_intervall=_PRIS_MIN_INTERVALL)
    if lagret:
        logger.info(f'Pris bekreftet: stasjon={stasjon_id} type={type_navn} bruker={bruker_id}')
    return jsonify({'ok': True, 'lagret': lagret})


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
    kommentar = (data.get('kommentar') or '').strip()[:500] or None
    er_nedlagt = bool(data.get('er_nedlagt'))
    if not foreslatt_navn and not foreslatt_kjede and not er_nedlagt and not kommentar:
        return jsonify({'error': 'Minst ett felt må fylles ut'}), 400
    bruker_id = session.get('bruker_id')
    try:
        if er_nedlagt:
            meld_stasjon_nedlagt(stasjon_id, bruker_id)
        if foreslatt_navn or foreslatt_kjede or kommentar:
            legg_til_endringsforslag(stasjon_id, bruker_id, foreslatt_navn, foreslatt_kjede, kommentar)
        logger.info(f'Endringsforslag for stasjon {stasjon_id} fra bruker {bruker_id}: navn={foreslatt_navn}, kjede={foreslatt_kjede}, nedlagt={er_nedlagt}, kommentar={bool(kommentar)}')
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
    noekkel = hent_innstilling('nyhet_noekkel', '')
    if tekst and utloper:
        try:
            utloper_dt = datetime.fromisoformat(utloper)
            if datetime.now() < utloper_dt:
                nyhet_id = hashlib.md5(tekst.encode()).hexdigest()[:8]
                return jsonify({'tekst': tekst, 'utloper': utloper, 'id': nyhet_id, 'tittel': 'Nyhet', 'noekkel': noekkel})
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
  <div class="farge-rad"><span class="farge-prikk" style="background:#fb923c"></span> Pris 8&#8211;24 timer gammel</div>
  <div class="farge-rad"><span class="farge-prikk" style="background:#ef4444"></span> Pris over 24 timer gammel eller ingen pris</div>
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
    <li><strong>Favorittstasjoner</strong> &#8212; lagre favoritter p&#229; hjem-skjermen uten innlogging</li>
    <li><strong>Anonymt prisinnlegging</strong> &#8212; legg inn pris uten konto (lavterskel for nye brukere)</li>
    <li><strong>Kamera/OCR</strong> &#8212; ta bilde av prisskiltet og la appen lese av prisen automatisk</li>
    <li><strong>Egendefinert s&#248;keradius</strong> &#8212; velg radius fra 1 til 250 km</li>
    <li><strong>Endringsforslag</strong> &#8212; foresl&#229; nytt navn eller kjede p&#229; en stasjon direkte fra appen</li>
    <li><strong>Godkjenning av nye stasjoner</strong> &#8212; brukerforeslåtte stasjoner godkjennes f&#248;r de vises for alle</li>
    <li><strong>Kjede-snittpriser</strong> &#8212; se gjennomsnittspris per kjede i statistikk-fanen</li>
    <li><strong>Radius-filter i statistikk</strong> &#8212; se billigste/dyreste priser avgrenset til valgt omr&#229;de</li>
    <li><strong>PWA-installknapp</strong> &#8212; enklere &#171;Legg til som app&#187; for iOS, Android og desktop</li>
    <li><strong>Nye kjeder:</strong> TANK, Bunker Oil, Trønder Oil</li>
    <li>Utvidet blogg og prisanalyser p&#229; <a href="/blogg/">/blogg/</a></li>
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

# Bildelagring for treningsdata (feature-flagget via env)
_OCR_LAGRE_BILDER = os.environ.get('OCR_LAGRE_BILDER', '').strip() == '1'
_OCR_BILDE_DIR = os.environ.get('OCR_BILDE_DIR', '/app/data/ocr-bilder')
_OCR_BILDE_RETENTION_DAGER = int(os.environ.get('OCR_BILDE_RETENTION_DAGER', '90'))

_OCR_MIN_PRIS = 15.0
_OCR_MAX_PRIS = 35.0
_OCR_CROP_MAX_SIDE = 1800
_OCR_CROP_MIN_PIXLER = 20
_OCR_DRIVSTOFF_FELT = ('bensin', 'diesel', 'bensin98', 'diesel_avgiftsfri')
_OCR_DRIVSTOFF_LABELS = {
    'bensin': '95 oktan bensin',
    'diesel': 'diesel',
    'bensin98': '98 oktan bensin',
    'diesel_avgiftsfri': 'avgiftsfri/farget diesel',
}


def _ocr_lagre_bilde(bilde_data, underkatalog, filnavn):
    """Lagre OCR-bilde til disk. Best effort — returnerer relativ sti eller None."""
    if not _OCR_LAGRE_BILDER:
        return None
    try:
        dato_dir = datetime.now().strftime('%Y/%m/%d')
        full_dir = os.path.join(_OCR_BILDE_DIR, underkatalog, dato_dir)
        os.makedirs(full_dir, exist_ok=True)
        full_sti = os.path.join(full_dir, filnavn)
        with open(full_sti, 'wb') as f:
            f.write(bilde_data)
        return os.path.join(underkatalog, dato_dir, filnavn)
    except Exception as e:
        logger.warning(f'OCR bildelagring feilet ({underkatalog}/{filnavn}): {e}')
        return None


def _ocr_rydd_gamle_bilder():
    """Slett OCR-bilder eldre enn retention-perioden. Kjøres best-effort."""
    if not _OCR_LAGRE_BILDER or _OCR_BILDE_RETENTION_DAGER <= 0:
        return
    try:
        grense = datetime.now() - timedelta(days=_OCR_BILDE_RETENTION_DAGER)
        for underkatalog in ('originals', 'crops'):
            base = os.path.join(_OCR_BILDE_DIR, underkatalog)
            if not os.path.isdir(base):
                continue
            for aar in os.listdir(base):
                aar_dir = os.path.join(base, aar)
                if not os.path.isdir(aar_dir):
                    continue
                for mnd in os.listdir(aar_dir):
                    mnd_dir = os.path.join(aar_dir, mnd)
                    if not os.path.isdir(mnd_dir):
                        continue
                    for dag in os.listdir(mnd_dir):
                        dag_dir = os.path.join(mnd_dir, dag)
                        if not os.path.isdir(dag_dir):
                            continue
                        try:
                            dato = datetime(int(aar), int(mnd), int(dag))
                            if dato < grense:
                                import shutil
                                shutil.rmtree(dag_dir)
                                logger.info(f'OCR retention: slettet {dag_dir}')
                        except (ValueError, OSError):
                            continue
    except Exception as e:
        logger.warning(f'OCR retention-opprydding feilet: {e}')


def _bbox_fra_maske(maske):
    """Finn enkel bbox for satte piksler i en numpy boolean-maske (h×w)."""
    antall = int(maske.sum())
    if antall < _OCR_CROP_MIN_PIXLER:
        return None
    rader = np.where(maske.any(axis=1))[0]
    kolonner = np.where(maske.any(axis=0))[0]
    min_y, max_y = int(rader[0]), int(rader[-1])
    min_x, max_x = int(kolonner[0]), int(kolonner[-1])
    return (min_x, min_y, max_x + 1, max_y + 1, antall)


def _led_klynge_bbox_fra_maske(maske):
    """Finn en strammere bbox rundt LED-lignende røde klynger.

    Store røde logoflater kan ellers dra vanlig bbox altfor bredt. Her deles
    masken i komponenter, og vi prioriterer små/medium komponenter som ligner
    segmenterte tall.
    """
    h, w = maske.shape
    steg = 2 if max(w, h) > 1200 else 1
    maske_sub = maske[::steg, ::steg]
    ys_sub, xs_sub = np.where(maske_sub)
    if len(xs_sub) < _OCR_CROP_MIN_PIXLER:
        return None
    if len(xs_sub) > 30_000:
        # For mange røde piksler – sannsynligvis neonramme/logo, ikke LED-display.
        # BFS på et så stort sett er tregt; faller tilbake til enkel bbox.
        return None
    punkter = set(zip((xs_sub * steg).tolist(), (ys_sub * steg).tolist()))

    komponenter = []
    naboer = (
        (-steg, -steg), (0, -steg), (steg, -steg),
        (-steg, 0), (steg, 0),
        (-steg, steg), (0, steg), (steg, steg),
    )
    while punkter:
        start = punkter.pop()
        stack = [start]
        min_x = max_x = start[0]
        min_y = max_y = start[1]
        antall = 1
        while stack:
            x, y = stack.pop()
            for dx, dy in naboer:
                nabo = (x + dx, y + dy)
                if nabo in punkter:
                    punkter.remove(nabo)
                    stack.append(nabo)
                    antall += 1
                    nx, ny = nabo
                    min_x = min(min_x, nx)
                    max_x = max(max_x, nx)
                    min_y = min(min_y, ny)
                    max_y = max(max_y, ny)
        if antall >= 4:
            komponenter.append((min_x, min_y, max_x + steg, max_y + steg, antall))

    kandidater = []
    for box in komponenter:
        x1, y1, x2, y2, antall = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        tetthet = antall / max(1, (bw / steg) * (bh / steg))
        if bw > 280 or bh > 260:
            continue
        if antall > 1800 and tetthet > 0.30:
            continue
        if 6 <= bw <= 240 and 10 <= bh <= 220 and tetthet <= 0.85:
            kandidater.append(box)

    if not kandidater:
        return None

    grupper = []
    for box in sorted(kandidater, key=lambda b: b[4], reverse=True):
        x1, y1, x2, y2, antall = box
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        lagt_til = False
        for gruppe in grupper:
            gx1, gy1, gx2, gy2, total, n = gruppe
            gcx = (gx1 + gx2) / 2
            gcy = (gy1 + gy2) / 2
            if abs(cx - gcx) <= 360 and abs(cy - gcy) <= 260:
                gruppe[0] = min(gx1, x1)
                gruppe[1] = min(gy1, y1)
                gruppe[2] = max(gx2, x2)
                gruppe[3] = max(gy2, y2)
                gruppe[4] = total + antall
                gruppe[5] = n + 1
                lagt_til = True
                break
        if not lagt_til:
            grupper.append([x1, y1, x2, y2, antall, 1])

    def score(gruppe):
        x1, y1, x2, y2, total, n = gruppe
        areal = max(1, (x2 - x1) * (y2 - y1))
        # Prisskilt sitter nesten alltid under logoen – boost grupper lavere i bildet.
        cy = (y1 + y2) / 2
        y_faktor = 1.0 + 0.4 * (cy / max(1, h))
        return total * min(n, 10) / math.sqrt(areal) * y_faktor

    beste = max(grupper, key=score)
    if beste[5] < 2 or beste[4] < _OCR_CROP_MIN_PIXLER:
        return None
    return (beste[0], beste[1], beste[2], beste[3], beste[4], beste[5])


def _utvid_bbox(box, img_size, faktor_x=3.8, faktor_y=4.2, min_bredde=360, min_hoyde=300):
    x1, y1, x2, y2 = box[:4]
    w, h = img_size
    bw = max(x2 - x1, min_bredde)
    bh = max(y2 - y1, min_hoyde)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    ny_w = min(w, bw * faktor_x)
    ny_h = min(h, bh * faktor_y)
    nx1 = max(0, int(cx - ny_w / 2))
    ny1 = max(0, int(cy - ny_h / 2))
    nx2 = min(w, int(cx + ny_w / 2))
    ny2 = min(h, int(cy + ny_h / 2))
    if nx2 - nx1 < min_bredde:
        mangler = min_bredde - (nx2 - nx1)
        nx1 = max(0, nx1 - mangler // 2)
        nx2 = min(w, nx1 + min_bredde)
    if ny2 - ny1 < min_hoyde:
        mangler = min_hoyde - (ny2 - ny1)
        ny1 = max(0, ny1 - mangler // 2)
        ny2 = min(h, ny1 + min_hoyde)
    return (nx1, ny1, nx2, ny2)


def _forbered_haiku_bilde(bilde_data, content_type):
    """Lag en billig server-side crop/zoom for kamera-OCR før Haiku-kall.

    Målet er ikke perfekt objektgjenkjenning, bare å gi små LED-tall flere
    piksler i bildet. Faller tilbake til originalen ved feil.
    """
    meta = {'preprocess': 'original', 'content_type': content_type, 'haiku_image': 'original'}
    if Image is None:
        meta['reason'] = 'pillow_missing'
        return base64.b64encode(bilde_data).decode('utf-8'), content_type, meta

    try:
        img = Image.open(io.BytesIO(bilde_data))
        img = img.convert('RGB')
        original_w, original_h = img.size
        img.thumbnail((_OCR_CROP_MAX_SIDE, _OCR_CROP_MAX_SIDE), Image.Resampling.LANCZOS)
        w, h = img.size

        img_np = np.array(img, dtype=np.float32)
        r_ch = img_np[:, :, 0]
        g_ch = img_np[:, :, 1]
        b_ch = img_np[:, :, 2]

        rod_maske = (
            (r_ch >= 115) & (g_ch <= 95) & (b_ch <= 95) &
            (r_ch >= g_ch * 1.25) & (r_ch >= b_ch * 1.25)
        )
        luminans = 0.299 * r_ch + 0.587 * g_ch + 0.114 * b_ch
        rod_led_maske = rod_maske & (luminans <= 90)
        gul_maske = (
            (r_ch >= 135) & (g_ch >= 95) & (b_ch <= 95) &
            (np.abs(r_ch - g_ch) <= 95) & (r_ch >= b_ch * 1.7) & (g_ch >= b_ch * 1.4)
        )

        rod_box = _bbox_fra_maske(rod_maske)
        led_box = _led_klynge_bbox_fra_maske(rod_led_maske) or _led_klynge_bbox_fra_maske(rod_maske)
        gul_box = _bbox_fra_maske(gul_maske)

        valgt_box = None
        strategi = 'resized_original'
        led_komponenter = led_box[5] if led_box else 0
        if led_box:
            valgt_box = _utvid_bbox(led_box, img.size, faktor_x=2.2, faktor_y=2.8, min_bredde=420, min_hoyde=340)
            strategi = 'red_led_tight_crop'
        elif rod_box:
            valgt_box = _utvid_bbox(rod_box, img.size, faktor_x=5.8, faktor_y=6.2, min_bredde=420, min_hoyde=340)
            strategi = 'red_led_crop'
        elif gul_box:
            valgt_box = _utvid_bbox(gul_box, img.size, faktor_x=2.8, faktor_y=3.2, min_bredde=440, min_hoyde=360)
            strategi = 'yellow_sign_crop'

        if valgt_box:
            crop = img.crop(valgt_box)
        else:
            # Avstandsbilder har ofte skilt i øvre/midtre del. Dette er en trygg
            # fallback som fortsatt bevarer nok kontekst.
            valgt_box = (int(w * 0.15), int(h * 0.10), int(w * 0.85), int(h * 0.72))
            crop = img.crop(valgt_box)

        cw, ch = crop.size
        scale = min(3.0, max(1.0, 1700 / max(cw, ch)))
        if scale > 1.05:
            crop = crop.resize((int(cw * scale), int(ch * scale)), Image.Resampling.LANCZOS)

        crop = ImageEnhance.Contrast(crop).enhance(1.25)
        crop = ImageEnhance.Sharpness(crop).enhance(1.45)
        crop = crop.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))

        out = io.BytesIO()
        crop.save(out, format='JPEG', quality=90, optimize=True)
        meta.update({
            'preprocess': strategi,
            'haiku_image': 'server_crop',
            'original_size': [original_w, original_h],
            'processed_size': list(crop.size),
            'crop_box': list(valgt_box),
            'red_pixels': rod_box[4] if rod_box else 0,
            'red_led_dark_pixels': int(rod_led_maske.sum()),
            'red_led_components': led_komponenter,
            'yellow_pixels': gul_box[4] if gul_box else 0,
        })
        return base64.b64encode(out.getvalue()).decode('utf-8'), 'image/jpeg', meta
    except Exception as e:
        logger.warning(f'OCR bilde-preprosessering feilet, bruker original: {e}')
        meta['reason'] = 'preprocess_failed'
        return base64.b64encode(bilde_data).decode('utf-8'), content_type, meta


def _hent_ocr_stasjon_kontekst(stasjon_id):
    try:
        stasjon_id = int(stasjon_id)
    except (TypeError, ValueError):
        return None
    if stasjon_id <= 0:
        return None
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT id, navn, kjede, har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri
               FROM stasjoner WHERE id = ?''',
            (stasjon_id,)
        ).fetchone()
        if not row:
            return None
        tillatte = {
            'bensin': bool(row[3]),
            'bensin98': bool(row[4]),
            'diesel': bool(row[5]),
            'diesel_avgiftsfri': bool(row[6]),
        }
        # Hent siste kjente priser for stasjonen (hjelper modellen med å unngå sifferfeil)
        forrige_priser = {}
        for felt, kolonne in [('bensin', 'bensin'), ('diesel', 'diesel'),
                               ('bensin98', 'bensin98'), ('diesel_avgiftsfri', 'diesel_avgiftsfri')]:
            pris_row = conn.execute(
                f'''SELECT {kolonne} FROM priser
                    WHERE stasjon_id = ? AND {kolonne} IS NOT NULL
                    ORDER BY id DESC LIMIT 1''',
                (stasjon_id,)
            ).fetchone()
            if pris_row and pris_row[0] is not None:
                forrige_priser[felt] = round(float(pris_row[0]), 2)
    return {
        'id': row[0],
        'navn': row[1],
        'kjede': row[2],
        'tillatte': tillatte,
        'forrige_priser': forrige_priser,
    }


def _ocr_tillatte_felt(stasjon_kontekst):
    if not stasjon_kontekst:
        return None
    tillatte = stasjon_kontekst.get('tillatte') or {}
    return {felt for felt in _OCR_DRIVSTOFF_FELT if tillatte.get(felt)}


def _filtrer_ocr_drivstoff(resultat, stasjon_kontekst):
    tillatte = _ocr_tillatte_felt(stasjon_kontekst)
    if not tillatte:
        return resultat
    fjernet = []
    for felt in _OCR_DRIVSTOFF_FELT:
        if felt not in tillatte and resultat.get(felt) is not None:
            resultat[felt] = None
            fjernet.append(felt)
    resultat['_tillatte_drivstoff'] = sorted(tillatte)
    if fjernet:
        resultat['_fjernet_ikke_solgt'] = fjernet
    return resultat


def _ocr_stasjon_prompt_tillegg(stasjon_kontekst):
    tillatte = _ocr_tillatte_felt(stasjon_kontekst)
    if not tillatte:
        return ''
    solgt = ', '.join(_OCR_DRIVSTOFF_LABELS[felt] for felt in _OCR_DRIVSTOFF_FELT if felt in tillatte)
    ikke_solgt = ', '.join(_OCR_DRIVSTOFF_LABELS[felt] for felt in _OCR_DRIVSTOFF_FELT if felt not in tillatte)
    tekst = (
        '\nStasjonskontekst:\n'
        f'- Valgt stasjon i appen: {stasjon_kontekst.get("navn") or "ukjent"}'
        f' ({stasjon_kontekst.get("kjede") or "ukjent kjede"}).\n'
        f'- Denne stasjonen er registrert med disse drivstofftypene: {solgt}.\n'
        '- Returner null for alle drivstofftyper som ikke står i listen over registrerte drivstofftyper, '
        'selv om du synes du ser et tall på bildet.\n'
    )
    if ikke_solgt:
        tekst += f'- Ikke bruk disse feltene: {ikke_solgt}.\n'
    forrige = stasjon_kontekst.get('forrige_priser') or {}
    if forrige:
        deler = [f'{_OCR_DRIVSTOFF_LABELS.get(k, k)}: {v} kr' for k, v in forrige.items()]
        tekst += (
            f'- Sist kjente priser for denne stasjonen: {", ".join(deler)}.\n'
            '  Bruk dette som sanity-check: hvis ditt OCR-resultat avviker mer enn ~3 kr fra '
            'forrige pris, dobbeltsjekk sifrene nøye (spesielt 1↔7, 8↔9, 6↔8 på LED). '
            'Priser KAN ha endret seg, men store avvik bør verifiseres.\n'
        )
    return tekst


_OCR_PROMPT_BASE = """Du er en OCR-leser for norske drivstoffskilt. Din ENESTE oppgave er å lese drivstoffpriser fra selve pristavlen/prisdisplayet.

AVVIS bildet og returner alle null-verdier hvis:
- Bildet ikke viser en drivstoff-pristavle/prisdisplay
- Prisene er for små, uskarpe, skjult av refleks eller ikke lesbare
- Du ikke klarer å koble en tydelig pris til en tydelig eller plausibel drivstofftype

Viktig: Ikke returner alle null bare fordi bildet er vanskelig. Hvis du ser minst én plausibel prisrad med tall i området 15.00–35.00, returner sikre priser og sett resten til null.

Returner KUN gyldig JSON uten annen tekst:
{"bensin": null, "diesel": null, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "low", "uncertain_fields": []}

Det finnes kun fire drivstofftyper:
- "bensin" = vanlig 95 oktan bensin. På tavlen: "95", "Blyfri", "B", "miles 95", "Futura 95", eller vanlig 95-rad.
- "bensin98" = høyoktan bensin. På tavlen: "98", "V-Power", "miles 98", "Futura 98", "Extra".
- "diesel" = vanlig diesel. På tavlen: "D", "Diesel", "HVO", "HVO100", "Blank diesel", "Biodiesel", "Miljødiesel", "miles D", "Diesel Gold", "B-diesel", "XTL".
- "diesel_avgiftsfri" = avgiftsfri/farget diesel. På tavlen: "FD", "Farget", "Avgiftsfri", "Avg.fri", "Anleggsdiesel".

Arbeidsmåte:
1. Finn først prisdisplayet/pristavlen. Ignorer bilvask, tilbud, kaffe, åpningstider og andre tall.
2. Tell synlige prisrader. Norske skilt har vanligvis 2 rader, av og til 3, sjelden 4.
3. Les hver rad horisontalt: drivstoffetikett på raden + pris på samme rad.
4. Match hver rad til riktig JSON-felt.
5. Returner sikre priser. Sett null for manglende eller usikre felt.

Radlogikk:
- Hvis bare 2 rader er synlige, er det normalt 95 + diesel.
- Hvis 2 rader er synlige og etikettene er uklare, anta 95 + diesel bare hvis prisene er tydelige.
- Hvis bare én av to rader har tydelig etikett, bruk den etiketten og la den andre raden være den andre vanlige typen. Eksempel: nederste rad er tydelig "95" -> nederste pris er bensin, øverste pris er diesel.
- Ikke fyll "bensin98" hvis du ikke ser 98/V-Power/miles 98/Futura 98/tilsvarende etikett.
- Ikke fyll "diesel_avgiftsfri" hvis du ikke ser FD/Farget/Avgiftsfri/Avg.fri/Anleggsdiesel/tilsvarende etikett.
- Hvis både D/Diesel og HVO/HVO100 vises på samme skilt, skal D/Diesel-raden brukes som "diesel". HVO-raden skal ignoreres fordi appen ikke har eget HVO-felt.
- Hvis 3 rader er synlige, er det vanligvis 95 + 98 + diesel ELLER 95 + diesel + farget diesel (FD/avgiftsfri).
- Haltbakk Express og liknende har ofte 95 + diesel + FD (farget diesel) — IKKE 98. Les etikettene nøye.
- 98 har ingen fast plassering. Bruk etiketten på raden, ikke radnummer.
- Hvis etiketten er tydelig, stol på etiketten selv om prisnivået virker overraskende.
- Ikke flytt en pris fra én rad til en annen bare fordi prisnivået passer bedre.
- Hvis øverste rad er "D" og nederste rad er "95", skal øverste pris være diesel og nederste pris være bensin.

Prislogikk (bruk dette aktivt til å korrigere lesefeil):
- Priser skal være mellom 15.00 og 35.00 kr/liter.
- bensin98 er normalt dyrere enn bensin 95, ofte 1–4 kr mer. Hvis 98 < 95, sjekk sifrene igjen. Hvis fortsatt usikkert, sett 98 til null.
- Diesel er ofte nær eller lavere enn 95, men kan variere.
- Avgiftsfri/farget diesel er normalt klart billigere enn vanlig diesel. Hvis den ser dyrere ut enn vanlig diesel, sjekk etikett og siffer ekstra nøye. Hvis raden tydelig er FD/Avgiftsfri, returner verdien, men sett "diesel_avgiftsfri" i uncertain_fields hvis du er usikker.

Format:
- Desimaltall med punktum (f.eks. 21.35)
- Priser skal normaliseres til XX.XX — to siffer før og to siffer etter desimaltegnet.
- Eksempler på korreksjon: "2608" → 26.08, "6.08" → sannsynligvis 26.08, "260.8" → 26.08. Verdier som ikke lar seg korrigere til XX.XX i området 15–35 — sett null.
- Sett null for typer du ikke finner

Kjede:
- "kjede" = kjedelogo eller -navn synlig i bildet (f.eks. "Circle K", "St1", "Esso", "Uno-X", "YX", "Best", "Tanken", "Haltbakk Express"). Ellers null.

Nøyaktighet — LED-display:
- På bilder tatt langt unna er desimalpunkt/komma ofte svakt eller usynlig. Les fire røde LED-siffer som XX.XX, ikke som heltall. Eksempel: 1949 -> 19.49 og 2079 -> 20.79.
- Uno-X-skilt kan ha to røde prisrader uten store produktnavn. Ofte er en liten "95" synlig ved nederste rad. Da er nederste rad bensin 95, og øverste rad er diesel selv om den er dyrere enn bensin.
- Røde/oransje LED-display: sifrene 1 og 7 forveksles svært lett. Sjekk: har sifferet et topphorisontalt segment? Da er det trolig 7, ikke 1. Eks: "18.19" der 95-oktan er i nærheten av 21.29 (98-oktan), er feil — den laveste prisen for 95 kan gjerne være 18.79 (7 lest som 1).
- Les 7-tall ekstra strengt på røde LED-skilt: et 7-tall har toppstrek og høyre segmenter, mens 1 mangler toppstreken. Hvis en pris ser ut som "16.19", men tredje siffer har en tydelig toppstrek, skal den leses som "16.79".
- 8 og 9 forveksles svært ofte på LED-skilt. Sjekk spesielt nedre venstre segment: hvis nedre venstre segment er tent, er sifferet trolig 8; hvis nedre venstre segment mangler mens øvre/midtre/nedre og høyre side er tent, er det trolig 9. Ikke velg 8 eller 9 uten å kontrollere dette segmentet.
- 4 og 9 kan også ligne på LED-skilt. Sjekk topp- og bunnsegmentene: 9 har vanligvis både toppsegment og bunnsegment tent, mens 4 vanligvis mangler toppsegment og bunnsegment og består mest av midtsegment + øvre venstre + høyre side. Ikke les 19.49 som 19.99 eller omvendt uten å sjekke disse segmentene.
- 6 og 8, 3 og 8, 9 og 5 forveksles også på LED. Sjekk spesielt siste siffer: 6 har nederste venstre segment tent, 5 mangler normalt nederste høyre segment. Ikke les 26.86 som 26.85 hvis siste siffer har lukket 6-form.
- I tall som ligner "20.19" på røde LED-skilt, vurder alltid om tredje siffer egentlig er 7 og tallet derfor er "20.79". Dette er en vanlig feil.
- Returner null kun hvis prisen ikke lar seg tolke til et plausibelt XX.XX-tall i området 15–35 selv etter korreksjonsforsøk.

Ekstra regler for robusthet:
- Hvis du ikke sikkert klarer å koble en pris til riktig drivstofftype, bruk null for den typen.
- Hvis du finner 2–4 plausible priser, men er usikker på én av dem, returner de sikre prisene og bruk null for den usikre.
- "confidence": high = tydelige etiketter og priser, medium = 1–2 sikre priser med noe usikkerhet, low = vanskelig bilde/få sikre felt.
- "uncertain_fields" = liste med feltnavn du er usikker på, ellers [].

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

Eksempel 7 (Haltbakk Express / 3 rader med farget diesel):
- Tavlen viser tre prisrader
- Rad 1 viser "95" og "17.59"
- Rad 2 viser "D" og "22.49"
- Rad 3 viser "FG" og "19.29"
- Ingen 98-rad er synlig
Svar:
{"bensin": 17.59, "diesel": 22.49, "bensin98": null, "diesel_avgiftsfri": 19.29, "kjede": "Haltbakk Express", "confidence": "high", "uncertain_fields": []}

"""


_OCR_PROMPT_FALLBACK = """Du leser et enkelt norsk drivstoffskilt med vanligvis 2 eller 3 prisrader.

Oppgaven er mye enklere enn vanlig:
- Finn prisdisplayet.
- Tell synlige prisrader.
- Les hver rad horisontalt: etikett + pris på samme rad.
- Returner kun prisene du er rimelig sikker på.

Viktige regler:
- Hvis du ser bare 2 rader, er det nesten alltid bensin 95 og diesel.
- Hvis du ser 3 rader, er det vanligvis bensin 95, bensin 98 og diesel ELLER bensin 95, diesel og farget diesel (FD/FG/avgiftsfri).
- Les etikettene nøye — ikke anta 98 hvis det står FD/FG/Farget/Avgiftsfri.
- Det finnes ingen fast vertikal plassering for 98.
- Hvis en rad tydelig er merket "95", skal den mappes til bensin.
- Hvis nederste rad er merket "95", skal nederste pris være bensin, og en umerket øverste rad på et vanlig 2-raders skilt skal vanligvis være diesel.
- Hvis en rad tydelig er merket "98", skal den mappes til bensin98.
- Hvis en rad tydelig er merket "D" eller "Diesel", skal den mappes til diesel.
- Hvis både D/Diesel og HVO/HVO100 finnes på samme skilt, bruk D/Diesel som diesel og ignorer HVO.
- Ikke gjett avgiftsfri diesel hvis den ikke er tydelig synlig.
- Langt unna kan desimalpunktet være usynlig: fire røde siffer skal normalt leses som XX.XX.
- Gult Uno-X-skilt med to røde rader har ofte diesel øverst og 95/bensin nederst, men les alltid sifrene i bildet og ikke bruk faste eksempelpriser.
- Røde LED-tall kan forveksle 1 og 7. Vurder alltid om 20.19 egentlig er 20.79 hvis segmentene ligner.
- 8 og 9, 4 og 9, 6 og 8 kan ligne. Sjekk segmentene før du bestemmer siffer.
- Prisene skal være mellom 15.00 og 35.00.
- Hvis du kun klarer å lese 95 og diesel, er det et gyldig svar.

Returner KUN gyldig JSON uten annen tekst:
{"bensin": null, "diesel": null, "bensin98": null, "diesel_avgiftsfri": null, "kjede": null, "confidence": "low", "uncertain_fields": []}
"""


_OCR_PROMPT_HAIKU_EKSTRA = """
Ekstra instruks for Haiku:
- Tenk rad-for-rad, ikke bilde-for-bilde. Finn først rektangelet med prisdisplayet, deretter hver horisontale prisrad.
- Tell synlige prisrader: vanligvis 2, av og til 3. Ikke let etter mange andre tall.
- Hvis to rader er synlige og bare én rad har lesbar etikett, bruk den etiketten først. Hvis nederste rad viser "95", er nederste pris bensin 95 og den andre synlige prisen er vanlig diesel.
- Hvis to rader er synlige og ingen etiketter er lesbare, returner de to prisene bare hvis de passer klart som 95 + diesel; ikke stol blindt på vertikal rekkefølge.
- Hvis tre rader er synlige, les etikettene nøye. Det kan være 95+98+diesel ELLER 95+diesel+FD/FG (farget diesel). Bruk etiketter hvis de er synlige; 98 har ingen fast plass.
- Ikke fyll 98 eller avgiftsfri diesel bare fordi du forventer flere produkter. Fyll dem bare når raden/etiketten er synlig eller svært tydelig.
- For gule Uno-X-skilt tatt langt unna: finn de røde LED-tallene i midten av skiltet. Hvis nederste rad har liten "95", skal nederste pris være bensin 95 og øverste synlige pris vanligvis diesel. Ikke bruk faste eksempelpriser.
- Røde LED-tall er punktmatrise/segmenter. Ikke les "20.79" som "2019" eller "20.19" hvis det tredje sifferet har tydelig 7-form.
- På samme måte: ikke les "16.79" som "16.19" hvis tredje siffer har topphorisontal strek. Det er en 7, ikke en 1.
- Sjekk 8 og 9 ekstra nøye: 8 har nedre venstre del/segment, 9 mangler vanligvis nedre venstre del/segment.
- Sjekk 4 og 9 ekstra nøye: 9 har topp og bunn, 4 mangler vanligvis topp og bunn.
- Sjekk 5 og 6 ekstra nøye i siste siffer: 6 har en lukket/nedre venstre form; 5 har ikke samme nedre venstre segment.
- Alle priser skal normaliseres til XX.XX. Eksempel: 1599 -> 15.99, 1949 -> 19.49, 2079 -> 20.79.
- Det er bedre å returnere to sikre priser med confidence "medium" enn å returnere alle null.
- Returner likevel null for felt som ikke har en synlig eller plausibel rad.
"""


def _lag_ocr_prompt(forventet_kjede=None, haiku=False, stasjon_kontekst=None):
    prompt = _OCR_PROMPT_BASE
    if haiku:
        prompt += _OCR_PROMPT_HAIKU_EKSTRA
    prompt += _ocr_stasjon_prompt_tillegg(stasjon_kontekst)
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


def _ocr_antall_priser(data: dict) -> int:
    return sum(1 for felt in _OCR_DRIVSTOFF_FELT if data.get(felt) is not None)


def _ocr_dekker_vanlige_drivstoff(data: dict, stasjon_kontekst) -> int:
    tillatte = _ocr_tillatte_felt(stasjon_kontekst) if stasjon_kontekst else {'bensin', 'diesel'}
    return sum(1 for felt in ('bensin', 'diesel') if felt in tillatte and data.get(felt) is not None)


def _ocr_bor_prove_gemini_fallback(data: dict, stasjon_kontekst) -> bool:
    """Bruk Gemini som kontroll når Haiku mister eller kan ha byttet viktige rader."""
    if not _har_ocr_priser(data):
        return True
    tillatte = _ocr_tillatte_felt(stasjon_kontekst) if stasjon_kontekst else {'bensin', 'diesel'}
    vanlige = [felt for felt in ('bensin', 'diesel') if felt in tillatte]
    if len(vanlige) >= 2 and any(data.get(felt) is None for felt in vanlige):
        return True
    return 'bensin98' in tillatte and data.get('bensin98') is not None and data.get('diesel') is not None


def _ocr_gemini_er_bedre(gemini_resultat: dict, haiku_resultat: dict, stasjon_kontekst) -> bool:
    if not _har_ocr_priser(gemini_resultat):
        return False
    gemini_score = _ocr_antall_priser(gemini_resultat) + 2 * _ocr_dekker_vanlige_drivstoff(gemini_resultat, stasjon_kontekst)
    haiku_score = _ocr_antall_priser(haiku_resultat) + 2 * _ocr_dekker_vanlige_drivstoff(haiku_resultat, stasjon_kontekst)
    if gemini_score > haiku_score:
        return True
    if gemini_score < haiku_score:
        return False
    tillatte = _ocr_tillatte_felt(stasjon_kontekst) if stasjon_kontekst else set()
    return 'bensin98' in tillatte and gemini_resultat != haiku_resultat


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

    confidence = data.get('confidence')
    if confidence in ('low', 'medium', 'high'):
        resultat['confidence'] = confidence

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


def _ocr_korriger_med_forrige(resultat, stasjon_kontekst):
    """Post-prosessering: korriger sannsynlige 1↔7-forvekslinger ved å sammenligne med forrige priser.

    Kun 1↔7-swap (den vanligste LED-feilen). Korrigerer kun hvis:
    - Originalen avviker >1 kr fra forrige pris
    - Korreksjonen gir en verdi innenfor 0.30 kr fra forrige pris
    """
    if not stasjon_kontekst:
        return resultat
    forrige = stasjon_kontekst.get('forrige_priser') or {}
    if not forrige:
        return resultat

    for felt in _OCR_DRIVSTOFF_FELT:
        ocr_val = resultat.get(felt)
        forrige_val = forrige.get(felt)
        if ocr_val is None or forrige_val is None:
            continue
        original_diff = abs(ocr_val - forrige_val)
        if original_diff < 0.30:
            continue  # Nær nok, ingen korreksjon nødvendig

        # Prøv alle enkelt-siffer 1↔7-swaps
        ocr_str = f'{ocr_val:.2f}'
        beste = ocr_val
        beste_diff = original_diff
        for i, ch in enumerate(ocr_str):
            if ch == '1':
                ny = ocr_str[:i] + '7' + ocr_str[i+1:]
            elif ch == '7':
                ny = ocr_str[:i] + '1' + ocr_str[i+1:]
            else:
                continue
            try:
                ny_val = float(ny)
            except ValueError:
                continue
            if not (_OCR_MIN_PRIS <= ny_val <= _OCR_MAX_PRIS):
                continue
            ny_diff = abs(ny_val - forrige_val)
            if ny_diff < beste_diff:
                beste = ny_val
                beste_diff = ny_diff

        # Bare korriger hvis resultatet er svært nært forrige pris
        if beste != ocr_val and beste_diff <= 0.30:
            logger.info(f'OCR 1↔7 korreksjon: {felt} {ocr_val} → {beste} (forrige={forrige_val})')
            resultat[felt] = beste

    return resultat


def _ocr_match_oppsummering(ai_resultat, lagret_priser):
    if not isinstance(ai_resultat, dict) or not isinstance(lagret_priser, dict):
        return None
    bekreftet_felt = lagret_priser.get('_bekreftet_felt')
    if isinstance(bekreftet_felt, list):
        felt = tuple(f for f in bekreftet_felt if f in _OCR_DRIVSTOFF_FELT)
    else:
        felt = _OCR_DRIVSTOFF_FELT
    relevante = []
    riktige = 0
    for navn in felt:
        ai = _parse_ocr_pris(ai_resultat.get(navn))
        lagret = _parse_ocr_pris(lagret_priser.get(navn))
        if ai is None and lagret is None:
            continue
        relevante.append(navn)
        if ai is not None and lagret is not None and abs(ai - lagret) < 0.01:
            riktige += 1
    if not relevante:
        return None
    return {'riktige': riktige, 'totalt': len(relevante), 'ok': riktige == len(relevante)}


def _ocr_tidspunkt_fra_data(data):
    tidspunkt = data.get('tidspunkt')
    if isinstance(tidspunkt, str):
        tidspunkt = tidspunkt.strip()
        if tidspunkt:
            return tidspunkt[:40]
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _ocr_stasjon_id_fra_statistikk(data, lagret):
    """Finn stasjon_id til OCR-statistikk fra eksplisitt felt eller lagret fasit."""
    kandidater = [data.get('stasjon_id')]
    claude_resultat = data.get('claude_resultat')
    if isinstance(claude_resultat, dict):
        kandidater.append(claude_resultat.get('_stasjon_id'))
    if isinstance(lagret, dict):
        kandidater.append(lagret.get('stasjon_id'))
    for verdi in kandidater:
        if not verdi:
            continue
        try:
            stasjon_id = int(verdi)
        except (TypeError, ValueError):
            continue
        if stasjon_id > 0:
            return stasjon_id
    return None


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
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': content_type,
                            'data': bilde_b64,
                        }
                    },
                    {'type': 'text', 'text': prompt},
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


def _ocr_via_haiku(bilde_b64, content_type, forventet_kjede=None, bilde_meta=None, stasjon_kontekst=None):
    kall = 1
    primar = _filtrer_ocr_drivstoff(_haiku_json_request(
        bilde_b64,
        content_type,
        _lag_ocr_prompt(forventet_kjede, haiku=True, stasjon_kontekst=stasjon_kontekst),
    ), stasjon_kontekst)
    if _har_ocr_priser(primar):
        primar['_haiku_calls'] = kall
        if bilde_meta:
            primar['_ocr_bilde'] = bilde_meta
        return primar

    fallback_prompt = _OCR_PROMPT_FALLBACK + _OCR_PROMPT_HAIKU_EKSTRA
    if forventet_kjede:
        fallback_prompt += (
            f'\nMykt hint: skiltet er sannsynligvis fra kjeden "{forventet_kjede}". '
            'Bruk bare dette hvis logo eller design stemmer.'
        )
    fallback_prompt += _ocr_stasjon_prompt_tillegg(stasjon_kontekst)
    kall += 1
    fallback = _filtrer_ocr_drivstoff(
        _haiku_json_request(bilde_b64, content_type, fallback_prompt),
        stasjon_kontekst,
    )
    resultat = fallback if _har_ocr_priser(fallback) else primar
    resultat['_haiku_calls'] = kall
    if bilde_meta:
        resultat['_ocr_bilde'] = bilde_meta
    return resultat


def _gemini_json_request(bilde_b64, content_type, prompt):
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError('GEMINI_API_KEY ikke satt')
    modeller = os.environ.get('GEMINI_MODELLER') or os.environ.get('GEMINI_MODELL', 'gemini-2.5-flash-lite')
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


def _ocr_via_gemini(bilde_b64, content_type, forventet_kjede=None, stasjon_kontekst=None):
    primar = _filtrer_ocr_drivstoff(
        _normaliser_ocr_resultat(
            _gemini_json_request(bilde_b64, content_type, _lag_ocr_prompt(forventet_kjede, stasjon_kontekst=stasjon_kontekst))
        ),
        stasjon_kontekst,
    )
    if _har_ocr_priser(primar):
        return primar

    fallback_prompt = _OCR_PROMPT_FALLBACK
    if forventet_kjede:
        fallback_prompt += (
            f'\nMykt hint: skiltet er sannsynligvis fra kjeden "{forventet_kjede}". '
            'Bruk bare dette hvis logo eller design stemmer.'
        )
    fallback_prompt += _ocr_stasjon_prompt_tillegg(stasjon_kontekst)
    fallback = _filtrer_ocr_drivstoff(
        _normaliser_ocr_resultat(
            _gemini_json_request(bilde_b64, content_type, fallback_prompt)
        ),
        stasjon_kontekst,
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
        # Kjør retention-opprydding én gang per dag (best effort)
        if not _ocr_bruk.get('_retention_dato') or _ocr_bruk['_retention_dato'] != i_dag:
            _ocr_bruk['_retention_dato'] = i_dag
            try:
                _ocr_rydd_gamle_bilder()
            except Exception:
                pass
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
    stasjon_id_str = request.form.get('stasjon_id')
    stasjon_kontekst = _hent_ocr_stasjon_kontekst(stasjon_id_str)
    forventet_kjede = (request.form.get('forventet_kjede') or '').strip()[:60] or None
    if stasjon_kontekst and stasjon_kontekst.get('kjede') and not forventet_kjede:
        forventet_kjede = stasjon_kontekst.get('kjede')

    # Lagre originalbilde (best effort)
    ts = datetime.now().strftime('%H%M%S')
    bilde_id = f'ocr-{bruker_id}-{ts}'
    original_sti = _ocr_lagre_bilde(bilde_data, 'originals', f'{bilde_id}-original.jpg')

    try:
        haiku_b64 = haiku_content_type = haiku_bilde_meta = None
        crop_sti = None
        if ocr_modell == 'gemini':
            try:
                priser = _ocr_via_gemini(bilde_b64, content_type, forventet_kjede=forventet_kjede, stasjon_kontekst=stasjon_kontekst)
                brukt_modell = priser.get('_modell') or 'gemini'
                if not _har_ocr_priser(priser):
                    logger.warning(f'Gemini OCR fant ingen priser for bruker={bruker_id}; prøver Haiku fallback')
                    haiku_b64, haiku_content_type, haiku_bilde_meta = _forbered_haiku_bilde(bilde_data, content_type)
                    crop_sti = _ocr_lagre_bilde(base64.b64decode(haiku_b64), 'crops', f'{bilde_id}-crop.jpg')
                    priser = _ocr_via_haiku(haiku_b64, haiku_content_type, forventet_kjede=forventet_kjede, bilde_meta=haiku_bilde_meta, stasjon_kontekst=stasjon_kontekst)
                    brukt_modell = 'haiku-fallback'
            except (ValueError, httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError, RuntimeError) as e:
                logger.warning(f'Gemini OCR feilet for bruker={bruker_id}; prøver Haiku fallback: {e}')
                haiku_b64, haiku_content_type, haiku_bilde_meta = _forbered_haiku_bilde(bilde_data, content_type)
                crop_sti = _ocr_lagre_bilde(base64.b64decode(haiku_b64), 'crops', f'{bilde_id}-crop.jpg')
                priser = _ocr_via_haiku(haiku_b64, haiku_content_type, forventet_kjede=forventet_kjede, bilde_meta=haiku_bilde_meta, stasjon_kontekst=stasjon_kontekst)
                brukt_modell = 'haiku-fallback'
        else:
            haiku_b64, haiku_content_type, haiku_bilde_meta = _forbered_haiku_bilde(bilde_data, content_type)
            crop_sti = _ocr_lagre_bilde(base64.b64decode(haiku_b64), 'crops', f'{bilde_id}-crop.jpg')
            priser = _ocr_via_haiku(haiku_b64, haiku_content_type, forventet_kjede=forventet_kjede, bilde_meta=haiku_bilde_meta, stasjon_kontekst=stasjon_kontekst)
            brukt_modell = 'haiku'
            if os.environ.get('GEMINI_API_KEY') and _ocr_bor_prove_gemini_fallback(priser, stasjon_kontekst):
                try:
                    gemini_priser = _ocr_via_gemini(bilde_b64, content_type, forventet_kjede=forventet_kjede, stasjon_kontekst=stasjon_kontekst)
                    if _ocr_gemini_er_bedre(gemini_priser, priser, stasjon_kontekst):
                        logger.info(
                            f'OCR Gemini-kontroll valgt: haiku={priser} gemini={gemini_priser}'
                        )
                        priser = gemini_priser
                        brukt_modell = 'gemini-control'
                except (ValueError, httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError, RuntimeError) as e:
                    logger.warning(f'Gemini OCR-kontroll feilet etter Haiku for bruker={bruker_id}: {e}')
        priser = _ocr_korriger_med_forrige(priser, stasjon_kontekst)
        priser['_modell'] = brukt_modell
        if stasjon_kontekst:
            priser['_stasjon_id'] = stasjon_kontekst.get('id')
        logger.info(
            f'OCR-gjenkjenning: bruker={bruker_id} modell={brukt_modell} '
            f'haiku_calls={priser.get("_haiku_calls")} bilde={priser.get("_ocr_bilde")} resultat={priser}'
        )
        if original_sti or crop_sti:
            priser['_ocr_bilder'] = {'original': original_sti, 'crop': crop_sti}
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
    claude_resultat = data.get('claude_resultat')
    lagret = data.get('lagret')
    match = _ocr_match_oppsummering(claude_resultat, lagret)
    tidspunkt = _ocr_tidspunkt_fra_data(data)

    # Hent bildestier fra claude_resultat
    ocr_bilder = claude_resultat.get('_ocr_bilder') if isinstance(claude_resultat, dict) else None
    bilde_original = ocr_bilder.get('original') if isinstance(ocr_bilder, dict) else None
    bilde_crop = ocr_bilder.get('crop') if isinstance(ocr_bilder, dict) else None
    if isinstance(claude_resultat, dict):
        tillatte = claude_resultat.get('_tillatte_drivstoff')
        ocr_bilde = claude_resultat.get('_ocr_bilde')
    stasjon_id = _ocr_stasjon_id_fra_statistikk(data, lagret)

    with get_conn() as conn:
        cursor = conn.execute('''INSERT INTO ocr_statistikk
            (bruker_id, tidspunkt, kilde, tesseract_ok, tesseract_ms, tesseract_resultat,
             tesseract_raatekst, claude_ok, claude_ms, claude_resultat,
             lagret_priser, tesseract_feil, claude_feil,
             bilde_original, bilde_crop, stasjon_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (bruker_id,
             tidspunkt,
             data.get('kilde'),
             1 if data.get('tesseract_ok') else 0,
             data.get('tesseract_ms'),
             json.dumps(data.get('tesseract_resultat')) if data.get('tesseract_resultat') else None,
             (data.get('tesseract_raatekst') or '')[:2000],
             1 if data.get('claude_ok') else 0,
             data.get('claude_ms'),
             json.dumps(claude_resultat) if claude_resultat else None,
             json.dumps(lagret) if lagret else None,
             data.get('tesseract_feil'),
             data.get('claude_feil'),
             bilde_original,
             bilde_crop,
             stasjon_id))
        rad_id = cursor.lastrowid

    bilde_meta = claude_resultat.get('_ocr_bilde') if isinstance(claude_resultat, dict) else None
    logger.info(
        f'OCR-statistikk: bruker={bruker_id} kilde={data.get("kilde")} '
        f'tidspunkt={tidspunkt} '
        f'claude_ok={bool(data.get("claude_ok"))} claude_ms={data.get("claude_ms")} '
        f'haiku_calls={claude_resultat.get("_haiku_calls") if isinstance(claude_resultat, dict) else None} '
        f'bilde={bilde_meta} match={match}'
    )

    return jsonify({'ok': True, 'id': rad_id})


@api_bp.route('/api/ocr-statistikk/<int:rad_id>', methods=['PATCH'])
@krever_innlogging
def ocr_statistikk_oppdater(rad_id):
    """Oppdater lagret_priser på en eksisterende OCR-statistikk-rad."""
    data = request.get_json(silent=True) or {}
    bruker_id = session.get('bruker_id')
    lagret = data.get('lagret')
    with get_conn() as conn:
        conn.execute(
            'UPDATE ocr_statistikk SET lagret_priser = ? WHERE id = ? AND bruker_id = ?',
            (json.dumps(lagret) if lagret else None, rad_id, bruker_id))
    return jsonify({'ok': True})
