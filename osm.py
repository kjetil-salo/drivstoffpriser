import httpx
import logging
import threading
import time
from db import lagre_stasjon, har_ferske_stasjoner

logger = logging.getLogger('drivstoff')
OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]

# Round-robin teller og backoff-sporing per endepunkt
_rr_index = 0
_backoff_until = {}  # url → timestamp når den kan brukes igjen
_henting_pagar = False  # hindrer samtidige Overpass-kall
_BACKOFF_TIMEOUT = 120  # sekunder backoff ved timeout/serverfeil
_BACKOFF_RATELIMIT = 120  # sekunder backoff ved 429
_lock = threading.Lock()


def hent_stasjoner_fra_osm_async(lat, lon, radius_m=30000):
    """Starter OSM-henting i bakgrunnstråd. Blokkerer ikke kallet."""
    if har_ferske_stasjoner(lat, lon, max_alder_timer=336):  # 14 dager
        return

    with _lock:
        global _henting_pagar
        if _henting_pagar:
            return
        _henting_pagar = True

    t = threading.Thread(target=_hent_fra_overpass, args=(lat, lon, radius_m), daemon=True)
    t.start()


def hent_stasjoner_fra_osm(lat, lon, radius_m=30000):
    """Synkron variant — brukes kun fra bakgrunnsjobber/tester."""
    if har_ferske_stasjoner(lat, lon, max_alder_timer=336):  # 14 dager
        return
    _gjor_overpass_kall(lat, lon, radius_m)


def _hent_fra_overpass(lat, lon, radius_m):
    """Intern: gjør selve Overpass-kallet."""
    global _rr_index, _henting_pagar
    try:
        _gjor_overpass_kall(lat, lon, radius_m)
    finally:
        with _lock:
            _henting_pagar = False


def _gjor_overpass_kall(lat, lon, radius_m):
    """Intern: selve HTTP-kallet mot Overpass."""
    global _rr_index

    maps_url = f'https://www.google.com/maps?q={lat},{lon}'
    logger.info(f'Overpass-søk fra posisjon {lat:.4f}, {lon:.4f} — {maps_url}')

    query = f'''[out:json][timeout:15];
(
  node["amenity"="fuel"](around:{radius_m},{lat},{lon});
  way["amenity"="fuel"](around:{radius_m},{lat},{lon});
);
out center;'''

    now = time.monotonic()
    n = len(OVERPASS_URLS)
    with _lock:
        start = _rr_index % n
        _rr_index += 1

    # Bygg rekkefølge med round-robin start, hopp over de i backoff
    urls = []
    for i in range(n):
        url = OVERPASS_URLS[(start + i) % n]
        if _backoff_until.get(url, 0) <= now:
            urls.append(url)

    if not urls:
        logger.debug('Alle Overpass-endepunkter i backoff, hopper over')
        return

    data = None
    with httpx.Client() as client:
        for url in urls:
            try:
                resp = client.post(url, data={'data': query}, timeout=15)
                if resp.status_code == 429:
                    _backoff_until[url] = now + _BACKOFF_RATELIMIT
                    logger.warning(f'Overpass {url}: 429 rate limit, backoff {_BACKOFF_RATELIMIT}s')
                    continue
                resp.raise_for_status()
                data = resp.json()
                logger.info(f'Brukte Overpass-endepunkt: {url}')
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    _backoff_until[url] = now + _BACKOFF_RATELIMIT
                    logger.warning(f'Overpass {url}: 429 rate limit, backoff {_BACKOFF_RATELIMIT}s')
                else:
                    _backoff_until[url] = now + _BACKOFF_TIMEOUT
                    logger.warning(f'Overpass {url} feilet: {e}')
            except Exception as e:
                _backoff_until[url] = now + _BACKOFF_TIMEOUT
                logger.warning(f'Overpass {url} feilet: {e}')
    if data is None:
        logger.warning('Alle Overpass-endepunkter feilet')
        return

    count = 0
    for el in data.get('elements', []):
        tags = el.get('tags', {})
        if el['type'] == 'node':
            elat, elon = el['lat'], el['lon']
        elif el['type'] == 'way' and 'center' in el:
            elat, elon = el['center']['lat'], el['center']['lon']
        else:
            continue

        navn = tags.get('name') or tags.get('brand') or 'Bensinstasjon'
        kjede = tags.get('brand') or tags.get('operator') or ''
        osm_id = f"{el['type']}/{el['id']}"

        lagre_stasjon(navn, kjede, elat, elon, osm_id)
        count += 1

    logger.info(f'Lagret {count} stasjoner fra OSM')
