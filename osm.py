import httpx
import logging
from db import lagre_stasjon, har_ferske_stasjoner

logger = logging.getLogger('drivstoff')
OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]


def hent_stasjoner_fra_osm(lat, lon, radius_m=20000):
    """Henter bensinstasjoner fra OSM og lagrer i SQLite. Hopper over hvis data er ferske."""
    if har_ferske_stasjoner(lat, lon):
        logger.debug('Ferske OSM-data finnes, hopper over henting')
        return

    logger.info(f'Henter bensinstasjoner fra OSM rundt {lat:.4f}, {lon:.4f}')

    query = f'''[out:json][timeout:20];
(
  node["amenity"="fuel"](around:{radius_m},{lat},{lon});
  way["amenity"="fuel"](around:{radius_m},{lat},{lon});
);
out center;'''

    data = None
    with httpx.Client() as client:
        for url in OVERPASS_URLS:
            try:
                resp = client.post(url, data={'data': query}, timeout=25)
                resp.raise_for_status()
                data = resp.json()
                logger.info(f'Brukte Overpass-endepunkt: {url}')
                break
            except Exception as e:
                logger.warning(f'Overpass {url} feilet: {e}')
    if data is None:
        raise RuntimeError('Alle Overpass-endepunkter feilet')

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
