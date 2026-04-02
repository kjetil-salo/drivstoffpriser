#!/usr/bin/env python3
"""
Henter ALLE bensinstasjoner i Norge fra Overpass API og lagrer i databasen.
Kan kjøres som standalone script eller importeres.

Bruk:
    python seed_stasjoner.py
"""

import logging
import time

import httpx

from db import init_db, _migrer_db, lagre_stasjon, get_conn

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('seed')

OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]

# Norge bounding box
NORGE_BBOX = (57.0, 4.0, 71.5, 31.5)  # sør, vest, nord, øst

OVERPASS_QUERY = f'''[out:json][timeout:120];
(
  node["amenity"="fuel"]({NORGE_BBOX[0]},{NORGE_BBOX[1]},{NORGE_BBOX[2]},{NORGE_BBOX[3]});
  way["amenity"="fuel"]({NORGE_BBOX[0]},{NORGE_BBOX[1]},{NORGE_BBOX[2]},{NORGE_BBOX[3]});
);
out center;'''


def hent_alle_stasjoner_norge():
    """Henter alle bensinstasjoner i Norge fra Overpass. Returnerer antall lagret."""
    data = None

    for url in OVERPASS_URLS:
        logger.info(f'Prøver {url} ...')
        try:
            resp = httpx.post(url, data={'data': OVERPASS_QUERY}, timeout=180)
            if resp.status_code == 429:
                logger.warning(f'{url}: 429 rate limit, prøver neste')
                time.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
            logger.info(f'Fikk svar fra {url}')
            break
        except Exception as e:
            logger.warning(f'{url} feilet: {e}')
            time.sleep(5)

    if data is None:
        logger.error('Alle Overpass-endepunkter feilet')
        return 0

    elements = data.get('elements', [])
    logger.info(f'Mottok {len(elements)} elementer fra Overpass')

    count = 0
    hoppet_over = 0
    for el in elements:
        tags = el.get('tags', {})

        # Hopp over nedlagte stasjoner
        if tags.get('disused') == 'yes' or tags.get('demolished') == 'yes' or tags.get('abandoned') == 'yes':
            hoppet_over += 1
            continue

        if el['type'] == 'node':
            lat, lon = el['lat'], el['lon']
        elif el['type'] == 'way' and 'center' in el:
            lat, lon = el['center']['lat'], el['center']['lon']
        else:
            continue

        navn = tags.get('name') or tags.get('brand') or 'Bensinstasjon'
        kjede = tags.get('brand') or tags.get('operator') or None
        osm_id = f"{el['type']}/{el['id']}"
        land = tags.get('addr:country') or None

        lagre_stasjon(navn, kjede, lat, lon, osm_id, land)
        count += 1

    if hoppet_over:
        logger.info(f'Hoppet over {hoppet_over} nedlagte stasjoner')
    logger.info(f'Lagret/oppdatert {count} stasjoner')
    return count


if __name__ == '__main__':
    init_db()
    _migrer_db()

    with get_conn() as conn:
        before = conn.execute('SELECT COUNT(*) FROM stasjoner').fetchone()[0]

    antall = hent_alle_stasjoner_norge()

    with get_conn() as conn:
        after = conn.execute('SELECT COUNT(*) FROM stasjoner').fetchone()[0]

    logger.info(f'Før: {before} stasjoner, etter: {after} stasjoner (hentet {antall} fra OSM)')
