"""API-ruter: stasjoner, priser, stedssøk, statistikk."""

import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta
from functools import wraps

import time

import httpx
from flask import Blueprint, request, jsonify, make_response, session

from db import (get_stasjoner_med_priser, lagre_pris, logg_visning,
                antall_stasjoner_med_pris, finn_bruker_id, DB_PATH,
                opprett_stasjon, hent_billigste_priser_24t,
                antall_prisoppdateringer_24t, meld_stasjon_nedlagt,
                get_conn, hent_innstilling, hent_toppliste, hent_toppliste_uke,
                hent_min_plassering, logg_blogg_visning,
                legg_til_endringsforslag, unike_enheter_per_dag,
                prisoppdateringer_per_time_24t,
                prisoppdateringer_rullende_24t_uke)

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
    return jsonify({'innlogget': True, 'brukernavn': bruker['brukernavn'],
                    'kallenavn': bruker.get('kallenavn') or '', 'bruker_id': bruker['id'],
                    'er_admin': bool(bruker['er_admin']),
                    'roller': (bruker.get('roller') or '').split()})


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
    tekst = hent_innstilling('nyhet_tekst', '')
    utloper = hent_innstilling('nyhet_utloper', '')
    if not tekst or not utloper:
        return jsonify({'tekst': None})
    try:
        utloper_dt = datetime.fromisoformat(utloper)
    except ValueError:
        return jsonify({'tekst': None})
    if datetime.now() >= utloper_dt:
        return jsonify({'tekst': None})
    nyhet_id = hashlib.md5(tekst.encode()).hexdigest()[:8]
    return jsonify({'tekst': tekst, 'utloper': utloper, 'id': nyhet_id})


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
<p class="undertittel">Finn billigst drivstoff i n&#230;rheten &#8212; gratis og drevet av brukerne.</p>
<p style="margin-top:0.5rem"><a href="/blogg/" style="color:#93c5fd;font-weight:600">&#128211; Les prisanalyse-bloggen &#8594;</a></p>

<div class="kort">
  <h2>Hva er dette?</h2>
  <p>En gratis webapp der brukerne selv registrerer og oppdaterer drivstoffpriser. Jo flere som bidrar, jo bedre og ferskere priser f&#229;r alle.</p>
  <p>Appen st&#248;tter <strong>95 oktan</strong>, <strong>98 oktan</strong>, <strong>Diesel</strong> og <strong>Avgiftsfri diesel</strong>.</p>
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
    <span class="steg-tekst"><strong>Hent posisjon</strong> eller <strong>s&#248;k etter et sted</strong> for &#229; se stasjoner i n&#230;rheten.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">2</span>
    <span class="steg-tekst"><strong>Trykk p&#229; en stasjon</strong> p&#229; kartet eller i listen for &#229; se priser, avstand og navigere dit.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">3</span>
    <span class="steg-tekst"><strong>Oppdater priser</strong> n&#229;r du er innom en stasjon &#8212; trykk &#171;Endre pris&#187; og legg inn det du ser p&#229; pumpa. Du kan ogs&#229; bekrefte at eksisterende priser stemmer.</span>
  </div>
  <div class="steg">
    <span class="steg-nr">4</span>
    <span class="steg-tekst"><strong>Mangler en stasjon?</strong> Logg inn og trykk <strong>+</strong> i toppmenyen for &#229; legge den til.</span>
  </div>
</div>

<div class="kort">
  <h2>Funksjoner</h2>
  <ul>
    <li><strong>Kart</strong> &#8212; se stasjoner rundt deg med fargekodede mark&#248;rer og priser</li>
    <li><strong>Liste</strong> &#8212; stasjoner sortert etter avstand med priser og kjedelogo</li>
    <li><strong>Statistikk</strong> &#8212; billigste priser siste 24 timer og antall oppdateringer</li>
    <li><strong>S&#248;k</strong> &#8212; finn stasjoner i andre byer og omr&#229;der</li>
    <li><strong>Navigering</strong> &#8212; trykk &#171;Naviger hit&#187; for &#229; &#229;pne veibeskrivelse</li>
    <li><strong>Innstillinger</strong> &#8212; velg hvilke drivstofftyper du vil se</li>
    <li><strong>Fungerer offline</strong> &#8212; sist viste priser er tilgjengelige uten nett</li>
    <li><strong>Legg til p&#229; hjem-skjermen</strong> &#8212; appen kan installeres som en app p&#229; telefonen</li>
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
</div>

<div class="kort">
  <h2>Om prosjektet</h2>
  <p>Laget som et hobbyprosjekt av Kjetil Salomonsen. Appen er <strong>helt gratis</strong> &#229; bruke.</p>
  <p>Sp&#248;rsm&#229;l eller tilbakemeldinger? Send en e-post til <a href="mailto:k@vikebo.com">k@vikebo.com</a></p>
  <p>Les v&#229;r <a href="/personvern">personvernerkl&#230;ring</a>.</p>
</div>

<div class="kort">
  <h2>Versjonshistorikk</h2>
  <p><strong>v1.2.0</strong> <span class="tag">28. mars 2026</span></p>
  <ul>
    <li>Toppliste over mest aktive bidragsytere i statistikk-fanen</li>
    <li>Del appen enkelt med venner via innstillinger-menyen</li>
    <li>Prisanalyse-blogg: ukentlige analyser p&#229; <a href="/blogg/">/blogg/</a></li>
  </ul>
  <p style="margin-top:1rem"><strong>v1.1.2</strong> <span class="tag">26.&#8211;27. mars 2026</span></p>
  <ul>
    <li>Registrering er n&#229; &#229;pen for alle &#8212; ingen tilgangskode trengs</li>
    <li>Ny kjede: Tanken</li>
    <li>Du kan n&#229; melde fra om nedlagte stasjoner</li>
  </ul>
  <p style="margin-top:1rem"><strong>v1.1.0</strong> <span class="tag">25. mars 2026</span></p>
  <ul>
    <li>Ny innstilling: velg s&#248;keradius (5&#8211;100 km)</li>
    <li>Fikset s&#248;kefelt som ikke reagerte p&#229; klikk</li>
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
