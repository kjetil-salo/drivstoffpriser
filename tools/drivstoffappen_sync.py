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
}

FUEL_NAVN = {1: 'diesel', 2: 'bensin'}
FORSINKELSE_SEK = 5 * 60  # ignorer priser yngre enn 5 min


def _hent_token() -> str:
    req = urllib.request.Request(f"{BASE_URL}/api/v1/authorization-sessions")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())['token']


def _utled_api_nøkkel(token: str) -> str:
    b = bytearray(token, 'utf-8')
    return hashlib.md5(b[1:] + b[:1]).hexdigest()


def _hent_stasjoner(api_key: str, drivstoff_ids: list[int]) -> list[dict]:
    ids_str = ','.join(str(i) for i in drivstoff_ids)
    url = f"{BASE_URL}/api/v1/stations?ids={ids_str}"
    headers = {'X-API-KEY': api_key, 'X-CLIENT-ID': CLIENT_ID}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


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


def kjør():
    nå = datetime.now(timezone.utc)
    stats = {
        'stasjoner_sjekket': 0,
        'priser_skrevet': 0,
        'hoppet_over': 0,
        'avvist_validering': 0,
        'feil': 0,
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

    drivstoff_id_til_vaar = {v: k for k, v in STASJON_MAPPING.items()}

    try:
        stasjoner = _hent_stasjoner(api_key, list(STASJON_MAPPING.values()))
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

                # Ignorer priser yngre enn 5 min (kan fortsatt være i bevegelse)
                nå_ms = nå.timestamp() * 1000
                if (nå_ms - last_updated_ms) < FORSINKELSE_SEK * 1000:
                    log.debug(f'{stasjonsnavn}: {kolonne} for fersk (< 5 min), hopper over')
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
        f"Drivstoffappen-sync {nå:%d.%m %H:%M} — "
        f"{stats['priser_skrevet']} skrevet, "
        f"{stats['hoppet_over']} skip, "
        f"{stats['avvist_validering']} avvist"
    )
    kropp_linjer = [
        f"Drivstoffappen-sync {nå:%Y-%m-%d %H:%M} UTC",
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
            conn.execute(
                "INSERT INTO drivstoffappen_sync "
                "(stasjoner_sjekket, priser_skrevet, hoppet_over, avvist_validering, feil) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    stats['stasjoner_sjekket'],
                    stats['priser_skrevet'],
                    stats['hoppet_over'],
                    stats['avvist_validering'],
                    stats['feil'],
                ),
            )
    except Exception as e:
        log.error(f'Statistikk-lagring feilet: {e}')


if __name__ == '__main__':
    kjør()
