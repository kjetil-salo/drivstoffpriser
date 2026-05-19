"""
Henter priser fra Drivstoffappen for et lite sett stasjoner og lagrer dem
i vår DB — kun hvis Drivstoffappens pris er nyere enn vår siste.

Kjøres av cron: 0 5-23 * * *
"""

import hashlib
import json
import logging
import os
import random
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_conn, lagre_pris

SYNC_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'partner_sync.db')


def _get_sync_conn():
    conn = sqlite3.connect(SYNC_DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS stasjon_bidrag (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tidspunkt   TEXT DEFAULT (datetime('now')),
        stasjon_id  INTEGER NOT NULL,
        bensin      INTEGER DEFAULT 0,
        diesel      INTEGER DEFAULT 0
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bidrag_stasjon ON stasjon_bidrag(stasjon_id)")
    return conn

logging.basicConfig(
    format='%(asctime)s drivstoffappen_sync %(levelname)s %(message)s',
    level=logging.INFO,
)
log = logging.getLogger('drivstoffappen_sync')

BASE_URL = "https://api.drivstoffappen.no"
CLIENT_ID = "com.raskebiler.drivstoff.appen.ios"
RESEND_FROM = "Drivstoffprisene <noreply@ksalo.no>"
VARSLE_TIL = "k@vikebo.com"

PRIS_MIN = 14.0
PRIS_MAX = 37.0
PARTNER_BRUKERNAVN = 'partner1'

# Vår DB-id → Drivstoffappen-id
# Basis-liste — kjøres av cron-jobb
STASJON_MAPPING = {
    1:  433,    # Esso Frekhaug
    2:  2190,   # Circle K Automat Knarvik
    3:  88,     # Esso Nyborg
    4:  687,    # St1 Haukås Nyborg
    16: 1278,   # St1 Marikollen
    19: 25153,  # Uno-X Tertnes
    26: 4064,   # Oljeleverandøren Hylkje
    30: 76,     # Circle K Ulset
    32: 643,    # Circle K Haukås
    33: 644,    # Circle K Helleveien
    42: 49,     # Uno-x gullgruven (Åsane)
    43: 121,    # Uno-X 7-Eleven Nyborg
    45: 1222,   # St1 Isdalstø
    18: 1324,   # St1 Lone
    36: 2093,   # St1 Nygård
    5690: 468,  # Esso Hundvåg
    35: 1094,   # Uno-X 7-Eleven Øyrane torg
    11: 28414,  # Haltbakk Express Ostereidet
    1882: 1351, # St1 Randabergveien
    1887: 221,  # Esso Tjensvollkrysset
    12: 791,    # Circle K Viken
}

# Region-tillegg — kun manuell kjøring via --region
STASJON_MAPPING_HAUGALANDET = {
    70: 3602,   # Circle K Automat Karmsundgata
    2004: 3170, # Circle K Automat Kopervik
    72: 257,    # Circle K Automat Spannaveien
    73: 187,    # Circle K Kvala
    2001: 195,  # Circle K Skudeneshavn
    2005: 259,  # Circle K Sævelandsvik
    2012: 3184, # Circle K Truck Gismarvik
    71: 199,    # Circle K Truck Haugesund
    75: 4569,   # Driv Ekrene
    62: 203,    # Esso Express Avaldsnes
    77: 207,    # Esso Express Gard
    78: 477,    # Esso Karmsundgaten
    76: 216,    # Esso Raglamyr
    2110: 1188, # St1 Aksdal
    2113: 1186, # St1 Eikeskog
    1236: 1304, # St1 Haukås Sveio
    60: 245,    # St1 Karmsundgata
    2006: 1311, # St1 Karmøy
    2007: 246,  # St1 Kopervik
    80: 1342,   # St1 Norheim
    66: 1548,   # Tanken Frakkagjerd
    1529655: 8792, # Tanken Isvik
    19959: 25158,  # Tanken Kvala
    2003: 1545, # Tanken Langåker
    1247: 4406, # Tanken Vikebygd
    69: 1547,   # Tanken Spannaveien
    64: 137,    # Uno-X Avaldsnes
    61: 25150,  # Uno-X Karmsundgata
    2008: 265,  # Uno-X Karmøy
    65: 269,    # Uno-X Norheim
    82: 25157,  # Uno-X Raglamyr
    68: 136,    # Uno-X Spannavegen
    67: 3160,   # YX Bømlo
    2114: 884,  # YX Truck Aksdal
}

STASJON_MAPPING_STAVANGER = {
    1842: 3691,  # Circle K Automat Hafrsfjord
    5661: 2865,  # Circle K Automat Hundvåg
    1869: 189,   # Circle K Automat Lagårdsveien
    1855: 174,   # Circle K Automat Mariero
    1906: 20813, # Circle K Automat Sandnesporten
    1839: 196,   # Circle K Automat Sola
    1836: 181,   # Circle K Forus
    1834: 183,   # Circle K Hana
    1878: 184,   # Circle K Haugesundsgaten
    1875: 801,   # Circle K Hommersåk
    1819: 751,   # Circle K Jørpeland
    1876: 186,   # Circle K Klepp
    1840: 191,   # Circle K Lura
    3091: 194,   # Circle K Randaberg
    1830: 197,   # Circle K Tau
    1849: 775,   # Circle K Tjelta
    1853: 28386, # Circle K Truck Ganddal
    1897: 28648, # Circle K Truck Risavika
    1879: 169,   # Circle K Ålgård
    1852: 170,   # Circle K Åsedalen
    1886: 204,   # Esso Bekkefaret
    1861: 1542,  # Esso Express Løkkeveien
    1884: 219,   # Esso Express Sola
    1837: 206,   # Esso Forus
    1890: 453,   # Esso Hillevåg
    1815: 474,   # Esso Jørpeland
    1885: 544,   # Esso Revheimsveien
    1841: 217,   # Esso Sandnes
    1846: 1167,  # St1 Bogafjell
    1835: 238,   # St1 Forus
    1844: 240,   # St1 Hagakrossen
    1883: 242,   # St1 Haugåsveien
    1850: 244,   # St1 Jærveien
    1856: 248,   # St1 Lura
    1874: 1326,  # St1 Madlakrossen
    1811: 1282,  # St1 Rennesøy
    1904: 4063,  # St1 Risavika
    1880: 250,   # St1 Solakrossen
    1854: 233,   # St1 Ålgård
    1848: 1105,  # Uno-X 7-Eleven Blåsenborg
    1860: 144,   # Uno-X Forus
    1838: 145,   # Uno-X Forussletta
    1909: 28286, # Uno-X Hinna
    1872: 149,   # Uno-X Hove
    1859: 148,   # Uno-X Klepp
    1851: 150,   # Uno-X Kongeparken
    1871: 147,   # Uno-X Kverneland
    1908: 146,   # Uno-X Lura
    1891: 142,   # Uno-X Madlaveien
    1895: 143,   # Uno-X Mariero
    1893: 139,   # Uno-X Randaberg
    1892: 141,   # Uno-X Sola
    1847: 3589,  # Uno-X Tananger
    1845: 140,   # Uno-X Tasta
    1821: 138,   # Uno-X Tau
}

REGIONER = {
    'haugalandet': STASJON_MAPPING_HAUGALANDET,
    'stavanger':   STASJON_MAPPING_STAVANGER,
}

FUEL_NAVN = {1: 'diesel', 2: 'bensin'}
FORSINKELSE_SEK = 5 * 60       # ignorer priser yngre enn 5 min
MAX_ALDER_SEK = 12 * 3600      # ignorer priser eldre enn 12 timer


def _hent_token() -> str:
    req = urllib.request.Request(f"{BASE_URL}/api/v1/authorization-sessions")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())['token']


def _utled_api_nøkkel(token: str) -> str:
    b = bytearray(token, 'utf-8')
    return hashlib.md5(b[1:] + b[:1]).hexdigest()


def _hent_stasjoner(api_key: str, drivstoff_ids: list[int]) -> tuple[list[dict], int]:
    """Returnerer (filtrerte stasjoner, antall stasjoner i hele dumpen med gyldig pris < 24t)."""
    headers = {'X-API-KEY': api_key, 'X-CLIENT-ID': CLIENT_ID}
    req = urllib.request.Request(f"{BASE_URL}/api/v1/stations", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        alle = json.loads(resp.read())
    grense_ms = (datetime.now(timezone.utc).timestamp() - 86400) * 1000
    partner_24t = sum(
        1 for s in alle
        if any(
            p.get('price') is not None and (p.get('lastUpdated') or 0) > grense_ms
            for p in s.get('prices', [])
            if p.get('fuelTypeId') in (1, 2)
        )
    )
    ids_set = set(drivstoff_ids)
    return [s for s in alle if s['id'] in ids_set], partner_24t


def _vaar_siste_tidspunkt(conn, stasjon_id: int, kolonne: str) -> datetime | None:
    row = conn.execute(
        f"SELECT {kolonne}, tidspunkt FROM priser "
        f"WHERE stasjon_id=? AND {kolonne} IS NOT NULL "
        f"ORDER BY tidspunkt DESC LIMIT 1",
        (stasjon_id,)
    ).fetchone()
    if not row:
        return None
    try:
        return datetime.fromisoformat(row[1]).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _hent_eller_opprett_partner(conn) -> int:
    row = conn.execute(
        "SELECT id FROM brukere WHERE brukernavn=?", (PARTNER_BRUKERNAVN,)
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO brukere (brukernavn, passord_hash, er_admin) VALUES (?, ?, 0)",
        (PARTNER_BRUKERNAVN, '!'),
    )
    return conn.execute(
        "SELECT id FROM brukere WHERE brukernavn=?", (PARTNER_BRUKERNAVN,)
    ).fetchone()[0]


def _hent_stasjonsnavn(conn, stasjon_id: int) -> str:
    row = conn.execute("SELECT navn FROM stasjoner WHERE id=?", (stasjon_id,)).fetchone()
    return row[0] if row else str(stasjon_id)


def _send_epost(emne: str, kropp: str):
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key:
        log.warning('RESEND_API_KEY ikke satt — epost ikke sendt')
        return
    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            'from': RESEND_FROM,
            'to': VARSLE_TIL,
            'subject': emne,
            'text': kropp,
        })
        log.info(f'Epost sendt: {emne}')
    except Exception as e:
        log.error(f'Epost feilet: {e}')


def kjør(prosent: float = 100, region: str | None = None):
    nå = datetime.now(timezone.utc)

    if region:
        basis = REGIONER.get(region)
        if basis is None:
            log.error(f'Ukjent region: {region}. Gyldige: {", ".join(REGIONER)}')
            return
        mapping = basis
        log.info(f'Region {region}: {len(mapping)} stasjoner')
    else:
        mapping = STASJON_MAPPING
        if prosent < 100:
            k = max(1, round(len(STASJON_MAPPING) * prosent / 100))
            utvalg = random.sample(list(STASJON_MAPPING.keys()), k)
            mapping = {vaar: STASJON_MAPPING[vaar] for vaar in utvalg}
            log.info(f'Tilfeldig utvalg: {k}/{len(STASJON_MAPPING)} stasjoner ({prosent}%)')

    stats = {
        'stasjoner_sjekket': 0,
        'priser_skrevet': 0,
        'hoppet_over': 0,
        'avvist_validering': 0,
        'feil': 0,
        'partner_stasjoner_24t': 0,
    }
    linjer: list[str] = []

    try:
        token = _hent_token()
        api_key = _utled_api_nøkkel(token)
    except Exception as e:
        log.error(f'Auth feilet: {e}')
        stats['feil'] += 1
        _logg_stats(stats)
        return

    drivstoff_id_til_vaar = {v: k for k, v in mapping.items()}

    try:
        stasjoner, partner_24t = _hent_stasjoner(api_key, list(mapping.values()))
        stats['partner_stasjoner_24t'] = partner_24t
        log.info(f'Drivstoffappen-dump: {partner_24t} stasjoner med priser siste 24t')
    except Exception as e:
        log.error(f'Henting feilet: {e}')
        stats['feil'] += 1
        _logg_stats(stats)
        return

    with get_conn() as conn, _get_sync_conn() as sync_conn:
        partner_id = _hent_eller_opprett_partner(conn)

        for s in stasjoner:
            drivstoff_id = s['id']
            vaar_id = drivstoff_id_til_vaar.get(drivstoff_id)
            if not vaar_id:
                continue

            stats['stasjoner_sjekket'] += 1
            stasjonsnavn = _hent_stasjonsnavn(conn, vaar_id)
            # pris + partnerens originalts per kolonne
            priser_denne = {'bensin': None, 'diesel': None, 'ts_ms': 0}

            for p in s.get('prices', []):
                ft = p.get('fuelTypeId')
                if ft not in (1, 2):
                    continue

                kolonne = FUEL_NAVN[ft]
                pris = p.get('price')
                last_updated_ms = p.get('lastUpdated', 0)

                if pris is None or not last_updated_ms:
                    continue

                nå_ms = nå.timestamp() * 1000
                alder_ms = nå_ms - last_updated_ms

                # Ignorer priser yngre enn 5 min (kan fortsatt være i bevegelse)
                if alder_ms < FORSINKELSE_SEK * 1000:
                    log.debug(f'{stasjonsnavn}: {kolonne} for fersk (< 5 min), hopper over')
                    stats['hoppet_over'] += 1
                    continue

                # Ignorer priser eldre enn 12 timer
                if alder_ms > MAX_ALDER_SEK * 1000:
                    alder_t = int(alder_ms / 3_600_000)
                    log.debug(f'{stasjonsnavn}: {kolonne} for gammel ({alder_t}t), hopper over')
                    stats['hoppet_over'] += 1
                    continue

                # Validering
                if not (PRIS_MIN <= pris <= PRIS_MAX):
                    log.warning(f'{stasjonsnavn}: {kolonne}={pris} avvist (utenfor {PRIS_MIN}–{PRIS_MAX})')
                    stats['avvist_validering'] += 1
                    linjer.append(f'  AVVIST   {stasjonsnavn:<35s} {kolonne:<8s} {pris:.2f} kr (utenfor {PRIS_MIN}–{PRIS_MAX})')
                    continue

                # Sammenlign mot vår siste (bruker partnerens originale ts)
                drivstoff_ts = datetime.fromtimestamp(last_updated_ms / 1000, tz=timezone.utc)
                vaar_ts = _vaar_siste_tidspunkt(conn, vaar_id, kolonne)

                if vaar_ts and vaar_ts >= drivstoff_ts:
                    log.debug(f'{stasjonsnavn}: {kolonne} hoppet over (vår {vaar_ts:%H:%M} >= partners {drivstoff_ts:%H:%M})')
                    stats['hoppet_over'] += 1
                    alder_min = int((nå - drivstoff_ts).total_seconds() / 60)
                    linjer.append(
                        f'  SKIP     {stasjonsnavn:<35s} {kolonne:<8s} {pris:.2f} kr '
                        f'(partner {alder_min}min gammel, vi er nyere)'
                    )
                    continue

                priser_denne[kolonne] = pris
                priser_denne['ts_ms'] = max(priser_denne['ts_ms'], last_updated_ms)

            if priser_denne['bensin'] is not None or priser_denne['diesel'] is not None:
                # Tidspunkt = partnerens ts + tilfeldig 5–10 min
                jitter_min = random.randint(5, 10)
                partner_ts = datetime.fromtimestamp(priser_denne['ts_ms'] / 1000, tz=timezone.utc)
                lagre_ts = (partner_ts + timedelta(minutes=jitter_min)).strftime('%Y-%m-%d %H:%M:%S')

                try:
                    lagret = lagre_pris(
                        vaar_id,
                        bensin=priser_denne['bensin'],
                        diesel=priser_denne['diesel'],
                        bruker_id=partner_id,
                        min_intervall=0,
                        tidspunkt=lagre_ts,
                    )
                    if lagret:
                        stats['priser_skrevet'] += 1
                        deler = []
                        if priser_denne['bensin']:
                            deler.append(f"bensin={priser_denne['bensin']:.2f}")
                        if priser_denne['diesel']:
                            deler.append(f"diesel={priser_denne['diesel']:.2f}")
                        log.info(f'{stasjonsnavn}: lagret {", ".join(deler)} (ts={lagre_ts})')
                        linjer.append(f'  SKREVET  {stasjonsnavn:<35s} {", ".join(deler)} (+{jitter_min}min)')
                        sync_conn.execute(
                            "INSERT INTO stasjon_bidrag (stasjon_id, bensin, diesel) VALUES (?, ?, ?)",
                            (vaar_id,
                             1 if priser_denne['bensin'] is not None else 0,
                             1 if priser_denne['diesel'] is not None else 0),
                        )
                    else:
                        stats['hoppet_over'] += 1
                except Exception as e:
                    log.error(f'{stasjonsnavn}: lagre_pris feilet: {e}')
                    stats['feil'] += 1

    _logg_stats(stats)

    emne = (
        f"Partner1-sync {nå:%d.%m %H:%M} — "
        f"{stats['priser_skrevet']} skrevet, "
        f"{stats['hoppet_over']} skip, "
        f"{stats['avvist_validering']} avvist"
    )
    kropp_linjer = [
        f"Partner1-sync {nå:%Y-%m-%d %H:%M} UTC",
        f"Stasjoner sjekket: {stats['stasjoner_sjekket']}",
        f"Priser skrevet:    {stats['priser_skrevet']}",
        f"Hoppet over:       {stats['hoppet_over']}  (vi hadde nyere)",
        f"Avvist validering: {stats['avvist_validering']}",
        f"Feil:              {stats['feil']}",
        "",
        "Detaljer:",
    ]
    if linjer:
        kropp_linjer += linjer
    else:
        kropp_linjer.append("  (ingen endringer)")

    _send_epost(emne, '\n'.join(kropp_linjer))


def _logg_stats(stats: dict):
    try:
        with get_conn() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(drivstoffappen_sync)").fetchall()}
            if 'partner_stasjoner_24t' not in cols:
                conn.execute("ALTER TABLE drivstoffappen_sync ADD COLUMN partner_stasjoner_24t INTEGER")
            conn.execute(
                "INSERT INTO drivstoffappen_sync "
                "(stasjoner_sjekket, priser_skrevet, hoppet_over, avvist_validering, feil, partner_stasjoner_24t) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    stats['stasjoner_sjekket'],
                    stats['priser_skrevet'],
                    stats['hoppet_over'],
                    stats['avvist_validering'],
                    stats['feil'],
                    stats['partner_stasjoner_24t'],
                ),
            )
    except Exception as e:
        log.error(f'Statistikk-lagring feilet: {e}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--prosent', type=float, default=100,
                        help='Prosent av stasjoner som skal sjekkes (f.eks. 20 = ~20%%)')
    parser.add_argument('--region', choices=list(REGIONER), default=None,
                        help='Kjør kun én region manuelt (haugalandet, stavanger)')
    args = parser.parse_args()
    kjør(prosent=args.prosent, region=args.region)
