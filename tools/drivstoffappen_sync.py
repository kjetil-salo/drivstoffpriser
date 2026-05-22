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
USER_AGENT = "Drivstoffappen/3.5.4 (com.raskebiler.drivstoff.appen; build:689; iOS 26.4.2) Alamofire/5.12.0"
REQUESTER_ID = "47C44FEA-48B3-4054-9282-D91DB913AD8C"
RESEND_FROM = "Drivstoffprisene <noreply@ksalo.no>"
VARSLE_TIL = "k@vikebo.com"

PRIS_MIN = 14.0
PRIS_MAX = 37.0
PARTNER_BRUKERNAVN = 'partner:partner1'
DUMP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'drivstoffappen_live.json')

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
    1882: 1351, # St1 Randabergveien
    1887: 221,  # Esso Tjensvollkrysset
    12: 791,    # Circle K Viken
    41: 53,     # Uno-X Fjøsanger
    155: 1216,  # St1 Bønes
    27: 314,   # Uno-X Fyllingsdalen
    39: 592,   # Esso Vestkanten
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

STASJON_MAPPING_JAEREN = {
    1859: 148,   # Uno-X Klepp
    1876: 186,   # Circle K Klepp
    1910: 1539,  # Tanken Kåsen
    1881: 230,   # St1 Bryne
    1889: 205,   # Esso Bryne
    1862: 151,   # Uno-X Bryne
    1888: 152,   # Uno-X Nærbø
    1863: 2861,  # Circle K Automat Nærbø
    1877: 193,   # Circle K Nærbø
}

STASJON_MAPPING_FØRDE = {
    3810: 28301,  # Circle K Truck Førde
    3804: 79,     # Esso Førde
    3812: 24503,  # Knapphus Energi Øyrane
    3819: 21676,  # Oljeleverandøren Førde
    3818: 1233,   # St1 Truck Firda billag
    3815: 47,     # Uno-X Førde
    3813: 2307,   # YX Coop Førde (automat)
    3803: 25194,  # YX Express Hafstadvegen (automat)
    3805: 117,    # YX Førde
    3816: 1071,   # YX Jølstraholmen
}

STASJON_MAPPING_BERGENBY = {
    31: 56,         # Circle K Automat Askøy
    21: 2059,       # Circle K Automat Fyllingsdalen
    22: 2104,       # Circle K Automat Godvik
    7: 3490,        # Circle K Automat Sædalen
    1289: 753,      # Circle K Fjell
    137: 743,       # Circle K Flesland
    153: 665,       # Circle K Nesttun
    13: 66,         # Circle K Ravnanger
    143: 822,       # Circle K Sandsli
    1283: 6143,     # Circle K Skogsvåg
    52: 415,        # Esso Express Landåstorget
    14: 476,        # Esso Kanalveien
    38: 486,        # Esso Laksevåg
    142: 527,       # Esso Nesttun
    1275: 372,      # Esso Ågotnes
    149: 25178,     # Haltbakk Express Søfteland
    1529716: 28677, # Haltbakk Kokstad
    9: 28393,       # Haltbakk express Askøy
    668911: 4134,   # Oljeleverandøren Drotningsvik
    9500: 28643,    # Oljeleverandøren Fjøsanger
    1529676: 28372, # Oljeleverandøren Lønningsflaten
    144: 1214,      # St1 Blomsterdalen
    154: 1320,      # St1 Laguneparken
    140: 1339,      # St1 Nesttun
    5: 1219,        # St1 Sandviken
    10: 508,        # St1 Storetveit
    1292: 109,      # St1 Straume
    20: 1383,       # St1 Varden
    17: 119,        # Uno-X 7-Eleven Drotningsvik
    8: 1088,        # Uno-X 7-Eleven Kleppestø
    1287: 1027,     # Uno-X 7-Eleven Kolltveit
    6: 1090,        # Uno-X 7-Eleven Natland
    29: 50,         # Uno-X Hauglandshella
    151: 55,        # Uno-X Kokstad
    1290: 52,       # Uno-X Straume
    162: 54,        # Uno-X Søreide
    1281: 986,      # YX Skogsvåg
}

STASJON_MAPPING_ASKOY_SOTRA_OYGARDEN = {
    # Øygarden
    2632: 2212,     # Circle K Automat Tjeldstø
    1285: 919,      # YX Rong
    1529682: 4793,  # Herdla
    # Askøy
    31: 56,         # Circle K Automat Askøy
    8: 1088,        # Uno-X 7-Eleven Kleppestø
    9: 28393,       # Haltbakk express Askøy
    13: 66,         # Circle K Ravnanger
    29: 50,         # Uno-X Hauglandshella
    44: 4133,       # Fromreide (Kjerrgarden)
    # Sotra/Fjell
    1289: 753,      # Circle K Fjell
    1283: 6143,     # Circle K Skogsvåg
    1281: 986,      # YX Skogsvåg
    1287: 1027,     # Uno-X 7-Eleven Kolltveit
    1290: 52,       # Uno-X Straume
    1292: 109,      # St1 Straume
    1275: 372,      # Esso Ågotnes
    # Sund
    1529665: 28359, # Joker Bakkasund
    152: 2258,      # Spar Steinsland
}

STASJON_MAPPING_KRISTIANSAND = {
    4247: 3179,    # Circle K Automat Brennåsen
    4248: 2241,    # Circle K Automat Sørlandsparken
    4246: 177,     # Circle K Automat Voiebyen
    4245: 179,     # Circle K Elvegaten
    4244: 8962,    # Circle K Truck Dalane
    1529776: 28664, # Driv Skibåsen
    4293: 6618,    # Esso Express Kjuttaviga
    4253: 210,     # Esso Express Krossen
    4231: 498,     # Esso Express Vågsbygd
    4234: 213,     # Esso Oddemarka
    4239: 218,     # Esso Søgne
    4237: 28368,   # Høllen brygge
    4252: 226,     # St1 Fidjane vest
    4251: 1291,    # St1 Fidjane øst
    4222: 1331,    # St1 Mosby
    4221: 1340,    # St1 Nodeland
    4250: 236,     # St1 Sørlandsparken
    4226: 1164,    # St1 Truck Kristiansand
    4235: 256,     # St1 Valhalla
    4233: 255,     # St1 Vige
    4228: 276,     # Uno-X 7-Eleven Vågsbygd
    4218: 25231,   # Uno-X Hamresanden
    4220: 25136,   # Uno-X Rosseland
    4287: 159,     # Uno-X Skibåsen
    4229: 158,     # Uno-X Sørlandsparken
    4227: 263,     # YX Håneskrysset
    4238: 273,     # YX Søgne (automat)
    4292: 28592,   # YX Truck Veøy Kristiansand
}

STASJON_MAPPING_MORE_ROMSDAL = {
    # --- Kristiansund (11 stasjoner) ---
    4411:    1432,  # Best Bremsnes (automat)
    4430:    2146,  # Bunker Oil Kristiansund
    4422:    2179,  # Circle K Truck Sødalen
    4420:     795,  # Circle K Viadukten
    4410:     519,  # Esso Express Løkkemyra
    1529671: 28407, # Haltbakk Express Frei
    4415:    1244,  # St1 Autokrysset
    4427:    3258,  # Uno-X Averøya
    4418:      37,  # Uno-X Kongens plass
    4426:    2275,  # Uno-X Løkkemyra
    4428:   25521,  # Uno-X Truck Frei

    # --- Molde og Romsdal (30 stasjoner) ---
    4417:    2144,  # Bunker Oil Batnfjorden
    1529634: 28564, # Bunker Oil Bud
    9289:    2143,  # Bunker Oil Hjelset
    1263472: 25242, # Bunker Oil Hollingen
    7249:    2142,  # Bunker Oil Malmefjorden
    7240:    3180,  # Bunker Oil Nesjestranda
    1529701: 2140,  # Bunker Oil Vestnes
    4419:    3884,  # Circle K Automat Eide
    7242:     838,  # Circle K Automat Julsundveien
    7235:     611,  # Circle K Molde
    5261:     605,  # Circle K Åndalsnes
    1529724: 21034, # Driv Elnesvågen
    1181647: 25520, # Driv Tornes
    1163468: 5673,  # Esso Energi Malmefjorden
    1529695: 5677,  # Esso Energi Årødalen
    4425:     576,  # Esso Express Elnesvågen
    5262:     513,  # Esso Øran
    5253:   25244,  # SnarKjøp Mittet
    7232:    1242,  # St1 Bolsønes
    7233:    1386,  # St1 Vestnes
    5260:    1240,  # St1 Åndalsnes
    7237:   22888,  # Uno-X Årødalen
    7234:     129,  # Uno-X 7-Eleven Reknes
    7236:      39,  # Uno-X Moldegård
    7247:     867,  # Uno-X Truck Straumen
    7248:   28588,  # Uno-X Truck Veøy Molde
    5256:   28589,  # Uno-X Truck Veøy Åndalsnes
    1529696: 28649, # YX Joker Eidsbygda
    1529704: 3168,  # YX Joker Kleive
    4424:    2247,  # YX Skjelvik

    # --- Ålesund og Sunnmøre (61 stasjoner) ---
    7148:    3492,  # Best Eidet
    3673:    2129,  # Bunker Oil Breivika
    3663:    2132,  # Bunker Oil Ekornes
    1529722: 2123,  # Bunker Oil Gjerdsvika
    1529742: 2103,  # Bunker Oil Godøy
    2606:    2128,  # Bunker Oil Hessa
    2607:   28658,  # Bunker Oil Lerstad
    2603:    2126,  # Bunker Oil Mauseidvågen
    2605:    2102,  # Bunker Oil Nørvevika
    1529730: 2133,  # Bunker Oil Skodje
    1504329: 2134,  # Bunker Oil Stette
    1529734: 2121,  # Bunker Oil Sæbø
    1529721: 2124,  # Bunker Oil Tjørvåg
    1381657: 28520, # Bunker Oil Vartdal
    1529720: 2136,  # Bunker Oil Vatne
    1529702: 2138,  # Bunker Oil Vigra
    7160:    2030,  # Circle K Automat Brattvåg
    3629:    3661,  # Circle K Automat Flisnes
    3633:    2251,  # Circle K Automat Fosnavåg
    2593:     748,  # Circle K Automat Hatlane
    3645:     744,  # Circle K Automat Sykkylven
    2589:    3659,  # Circle K Automat Valderøy
    7157:     710,  # Circle K Digerneset
    2592:     642,  # Circle K Hareid
    3647:     723,  # Circle K Moa
    104:    28237,  # Circle K Truck Furene
    101:      831,  # Circle K Volda
    97:        65,  # Circle K Ørsta
    1529660: 28296, # Coop Folkestad Dalsfjord Bensin
    102:    25476,  # Coop Lauvstad
    1529778: 25449, # Drivstoff Åsevika Rovde
    3653:     564,  # Esso Spjelkavik
    2586:     595,  # Esso Vigra
    1529711: 25419, # Knapphus Energi Rysteland
    2604:    3262,  # MH24 Dragsund
    3672:    6660,  # MH24 Fosnavåg
    3668:    2965,  # MH24 Haugsbygda
    99:      1239,  # St1 Express Hovdebygda
    2594:     112,  # St1 Ulsteinvik
    2590:    1384,  # St1 Vegsund
    106:     1290,  # St1 Volda
    98:       104,  # St1 Ørsta
    1520542: 22526, # Storbilservice Emdal
    1529779: 6095,  # Tanken Ellingsøy
    1529744: 3183,  # Tanken Gursken
    1418045: 28309, # Tanken Jensholmen Herøy
    2601:    1092,  # Uno-X 7-Eleven Tinghuset
    2597:      42,  # Uno-X Gåseid
    2602:   25096,  # Uno-X Langevåg
    2596:     886,  # Uno-X Truck Waagan
    2595:      43,  # Uno-X Ulsteinvik
    2599:      41,  # Uno-X Valderøya
    110:    25008,  # Uno-X Volda
    2600:    1093,  # Uno-X Ysteneset
    7177:    3552,  # Uno-X Vallekrysset
    103:       44,  # Uno-X Ørsta
    3630:     992,  # YX Fosnavåg
    109:     5692,  # YX Furene Volda
    3635:     925,  # YX Larsnes
    3654:     902,  # YX Sykkylven
    3634:     942,  # YX Søvik
}

REGIONER = {
    'haugalandet':          STASJON_MAPPING_HAUGALANDET,
    'stavanger':            STASJON_MAPPING_STAVANGER,
    'jaeren':               STASJON_MAPPING_JAEREN,
    'kristiansand':         STASJON_MAPPING_KRISTIANSAND,
    'forde':                STASJON_MAPPING_FØRDE,
    'bergenby':             STASJON_MAPPING_BERGENBY,
    'askoy_sotra_oygarden': STASJON_MAPPING_ASKOY_SOTRA_OYGARDEN,
    'more_romsdal':         STASJON_MAPPING_MORE_ROMSDAL,
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


def _hent_og_lagre_dump(api_key: str) -> list[dict]:
    headers = {
        'X-API-KEY': api_key,
        'X-CLIENT-ID': CLIENT_ID,
        'User-Agent': USER_AGENT,
        'X-Requester-Id': REQUESTER_ID,
        'Accept-Language': 'nb-NO;q=1.0, nn-NO;q=0.9',
    }
    req = urllib.request.Request(f"{BASE_URL}/api/v1/stations", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        alle = json.loads(resp.read())
    with open(DUMP_PATH, 'w', encoding='utf-8') as f:
        json.dump({'generert': datetime.now(timezone.utc).isoformat(), 'antall': len(alle), 'stasjoner': alle}, f)
    log.info(f'Dump lagret: {len(alle)} stasjoner → {DUMP_PATH}')
    return alle


def _les_dump() -> tuple[list[dict], str]:
    with open(DUMP_PATH, encoding='utf-8') as f:
        data = json.load(f)
    return data['stasjoner'], data['generert']


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
    stats = {
        'stasjoner_sjekket': 0,
        'priser_skrevet': 0,
        'hoppet_over': 0,
        'avvist_validering': 0,
        'feil': 0,
        'partner_stasjoner_24t': 0,
    }
    linjer: list[str] = []

    if region:
        basis = REGIONER.get(region)
        if basis is None:
            log.error(f'Ukjent region: {region}. Gyldige: {", ".join(REGIONER)}')
            return
        mapping = basis
        if prosent < 100:
            k = max(1, round(len(basis) * prosent / 100))
            utvalg = random.sample(list(basis.keys()), k)
            mapping = {vaar: basis[vaar] for vaar in utvalg}
            log.info(f'Region {region} tilfeldig utvalg: {k}/{len(basis)} stasjoner ({prosent}%)')
        try:
            alle_stasjoner, dump_ts = _les_dump()
            log.info(f'Region {region}: {len(mapping)} stasjoner (dump fra {dump_ts})')
        except Exception as e:
            log.error(f'Dump-lesing feilet: {e}')
            return
    else:
        mapping = STASJON_MAPPING
        if prosent < 100:
            k = max(1, round(len(STASJON_MAPPING) * prosent / 100))
            utvalg = random.sample(list(STASJON_MAPPING.keys()), k)
            mapping = {vaar: STASJON_MAPPING[vaar] for vaar in utvalg}
            log.info(f'Tilfeldig utvalg: {k}/{len(STASJON_MAPPING)} stasjoner ({prosent}%)')

        try:
            token = _hent_token()
            api_key = _utled_api_nøkkel(token)
        except Exception as e:
            log.error(f'Auth feilet: {e}')
            stats['feil'] += 1
            _logg_stats(stats)
            return

        try:
            alle_stasjoner = _hent_og_lagre_dump(api_key)
        except Exception as e:
            log.error(f'Henting feilet: {e}')
            stats['feil'] += 1
            _logg_stats(stats)
            return

    grense_ms = (nå.timestamp() - 86400) * 1000
    partner_24t = sum(
        1 for s in alle_stasjoner
        if any(
            p.get('price') is not None and (p.get('lastUpdated') or 0) > grense_ms
            for p in s.get('prices', [])
            if p.get('fuelTypeId') in (1, 2)
        )
    )
    stats['partner_stasjoner_24t'] = partner_24t
    log.info(f'Drivstoffappen-dump: {partner_24t} stasjoner med priser siste 24t')

    drivstoff_id_til_vaar = {v: k for k, v in mapping.items()}
    ids_set = set(mapping.values())
    stasjoner = [s for s in alle_stasjoner if s['id'] in ids_set]

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
    parser.add_argument('--region', choices=list(REGIONER.keys()), default=None,
                        help='Kjør kun én region manuelt (haugalandet, stavanger)')
    args = parser.parse_args()
    kjør(prosent=args.prosent, region=args.region)
