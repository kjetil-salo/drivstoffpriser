import sqlite3
import math
import os
from datetime import datetime

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivstoff.db')
DB_PATH = os.environ.get('DB_PATH', _default_db)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS stasjoner (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                navn TEXT NOT NULL,
                kjede TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                osm_id TEXT UNIQUE,
                sist_oppdatert TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS priser (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stasjon_id INTEGER NOT NULL,
                bensin REAL,
                diesel REAL,
                bensin98 REAL,
                tidspunkt TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (stasjon_id) REFERENCES stasjoner(id)
            );
            CREATE TABLE IF NOT EXISTS visninger (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                user_agent TEXT,
                ts        TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_stasjoner_pos ON stasjoner(lat, lon);
            CREATE INDEX IF NOT EXISTS idx_visninger_device ON visninger(device_id);
            CREATE INDEX IF NOT EXISTS idx_visninger_ts ON visninger(ts);
            CREATE TABLE IF NOT EXISTS brukere (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                brukernavn TEXT NOT NULL UNIQUE,
                passord_hash TEXT NOT NULL,
                er_admin   INTEGER NOT NULL DEFAULT 0,
                opprettet  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS invitasjoner (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                token     TEXT NOT NULL UNIQUE,
                opprettet TEXT DEFAULT (datetime('now')),
                utloper   TEXT NOT NULL,
                brukt     INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tilbakestilling (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                token     TEXT NOT NULL UNIQUE,
                epost     TEXT NOT NULL,
                opprettet TEXT DEFAULT (datetime('now')),
                utloper   TEXT NOT NULL,
                brukt     INTEGER NOT NULL DEFAULT 0
            );
        ''')


def _migrer_db():
    with get_conn() as conn:
        kolonner = [r[1] for r in conn.execute("PRAGMA table_info(priser)").fetchall()]
        if 'bensin98' not in kolonner:
            conn.execute("ALTER TABLE priser ADD COLUMN bensin98 REAL")
        if 'bruker_id' not in kolonner:
            conn.execute("ALTER TABLE priser ADD COLUMN bruker_id INTEGER REFERENCES brukere(id)")

        stasjon_kolonner = [r[1] for r in conn.execute("PRAGMA table_info(stasjoner)").fetchall()]
        if 'lagt_til_av' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN lagt_til_av INTEGER REFERENCES brukere(id)")
        if 'godkjent' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN godkjent INTEGER DEFAULT 1")


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371e3
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))



def lagre_stasjon(navn, kjede, lat, lon, osm_id):
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO stasjoner (navn, kjede, lat, lon, osm_id)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(osm_id) DO UPDATE SET
                 navn=excluded.navn, kjede=excluded.kjede,
                 lat=excluded.lat, lon=excluded.lon,
                 sist_oppdatert=datetime('now')''',
            (navn, kjede, lat, lon, osm_id)
        )


def lagre_pris(stasjon_id, bensin, diesel, bensin98=None, bruker_id=None):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO priser (stasjon_id, bensin, diesel, bensin98, bruker_id) VALUES (?, ?, ?, ?, ?)',
            (stasjon_id, bensin, diesel, bensin98, bruker_id)
        )


def hent_siste_prisoppdateringer(limit=100) -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT p.id, p.bensin, p.diesel, p.bensin98, p.tidspunkt,
                      s.navn, s.kjede, s.lat, s.lon,
                      b.brukernavn
               FROM priser p
               JOIN stasjoner s ON s.id = p.stasjon_id
               LEFT JOIN brukere b ON b.id = p.bruker_id
               ORDER BY p.id DESC
               LIMIT ?''',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_statistikk() -> dict:
    from datetime import date, timedelta
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        prisendringer = conn.execute("SELECT COUNT(*) FROM priser").fetchone()[0]
        totalt = conn.execute("SELECT COUNT(*) FROM visninger").fetchone()[0]
        unike_enheter = conn.execute(
            "SELECT COUNT(DISTINCT device_id) FROM visninger WHERE device_id != ''"
        ).fetchone()[0]
        today = date.today()
        trend_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
        for row in conn.execute(
            "SELECT DATE(ts) as dato, COUNT(*) as cnt FROM visninger "
            "WHERE ts >= DATE('now', '-29 days') GROUP BY dato"
        ).fetchall():
            if row['dato'] in trend_map:
                trend_map[row['dato']] = row['cnt']

        besok_per_time = conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00:00', ts) as time, COUNT(*) as cnt "
            "FROM visninger WHERE ts >= datetime('now', '-10 hours') "
            "GROUP BY time ORDER BY time"
        ).fetchall()

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    timer_map = {}
    for i in range(10, -1, -1):
        t = (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00:00')
        timer_map[t] = 0
    for row in besok_per_time:
        if row['time'] in timer_map:
            timer_map[row['time']] = row['cnt']

    return {
        'prisendringer': prisendringer,
        'totalt': totalt,
        'unike_enheter': unike_enheter,
        'trend_30d': list(trend_map.items()),
        'besok_per_time': list(timer_map.items()),
    }


def hent_billigste_priser_24t() -> list:
    """Hent de billigste prisene registrert siste 24 timer, per drivstofftype."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT p.bensin, p.diesel, p.bensin98, p.tidspunkt,
                      s.navn, s.kjede
               FROM priser p
               JOIN stasjoner s ON s.id = p.stasjon_id
               WHERE p.tidspunkt > datetime('now', '-24 hours')
                 AND p.id IN (SELECT MAX(p2.id) FROM priser p2
                              WHERE p2.tidspunkt > datetime('now', '-24 hours')
                              GROUP BY p2.stasjon_id)
               ORDER BY p.tidspunkt DESC'''
        ).fetchall()

        resultater = []
        for r in rows:
            d = dict(r)
            resultater.append(d)
        return resultater


def antall_prisoppdateringer_24t() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM priser WHERE tidspunkt > datetime('now', '-24 hours')"
        ).fetchone()[0]


def antall_stasjoner_med_pris() -> int:
    with get_conn() as conn:
        return conn.execute(
            '''SELECT COUNT(DISTINCT stasjon_id) FROM priser
               WHERE bensin IS NOT NULL OR diesel IS NOT NULL OR bensin98 IS NOT NULL'''
        ).fetchone()[0]


def stasjoner_med_pris_koordinater() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            '''SELECT s.navn, s.kjede, s.lat, s.lon,
                      p.bensin, p.diesel, p.bensin98, p.tidspunkt
               FROM stasjoner s
               JOIN priser p ON p.stasjon_id = s.id
               WHERE p.id = (SELECT MAX(p2.id) FROM priser p2 WHERE p2.stasjon_id = s.id)
                 AND (p.bensin IS NOT NULL OR p.diesel IS NOT NULL OR p.bensin98 IS NOT NULL)'''
        ).fetchall()]


def antall_brukere() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM brukere").fetchone()[0]


def opprett_bruker(brukernavn: str, passord_hash: str, er_admin: bool = False):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO brukere (brukernavn, passord_hash, er_admin) VALUES (?, ?, ?)",
            (brukernavn, passord_hash, 1 if er_admin else 0)
        )


def finn_bruker(brukernavn: str) -> dict | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM brukere WHERE brukernavn = ?", (brukernavn,)
        ).fetchone()
        return dict(row) if row else None


def finn_bruker_id(bruker_id: int) -> dict | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM brukere WHERE id = ?", (bruker_id,)
        ).fetchone()
        return dict(row) if row else None


def hent_alle_brukere() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, brukernavn, er_admin, opprettet FROM brukere ORDER BY opprettet"
        ).fetchall()
        return [dict(r) for r in rows]


def slett_bruker(bruker_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM brukere WHERE id = ?", (bruker_id,))


def opprett_invitasjon(token: str, utloper: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO invitasjoner (token, utloper) VALUES (?, ?)",
            (token, utloper)
        )


def hent_invitasjon(token: str) -> dict | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM invitasjoner WHERE token = ? AND brukt = 0 AND utloper > datetime('now')",
            (token,)
        ).fetchone()
        return dict(row) if row else None


def merk_invitasjon_brukt(token: str):
    with get_conn() as conn:
        conn.execute("UPDATE invitasjoner SET brukt = 1 WHERE token = ?", (token,))


def opprett_tilbakestilling(token: str, epost: str, utloper: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tilbakestilling (token, epost, utloper) VALUES (?, ?, ?)",
            (token, epost, utloper)
        )


def hent_tilbakestilling(token: str) -> dict | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM tilbakestilling WHERE token = ? AND brukt = 0 AND utloper > datetime('now')",
            (token,)
        ).fetchone()
        return dict(row) if row else None


def merk_tilbakestilling_brukt(token: str):
    with get_conn() as conn:
        conn.execute("UPDATE tilbakestilling SET brukt = 1 WHERE token = ?", (token,))


def oppdater_passord(epost: str, passord_hash: str):
    with get_conn() as conn:
        conn.execute("UPDATE brukere SET passord_hash = ? WHERE brukernavn = ?", (passord_hash, epost))


def logg_visning(device_id: str, user_agent: str):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO visninger (device_id, user_agent) VALUES (?, ?)',
            (device_id, user_agent)
        )


def finn_naer_stasjon(lat, lon, maks_avstand_m=50):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        delta = 0.005
        rows = conn.execute(
            '''SELECT id, navn, lat, lon FROM stasjoner
               WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?''',
            (lat - delta, lat + delta, lon - delta, lon + delta)
        ).fetchall()
    for row in rows:
        if _haversine(lat, lon, row['lat'], row['lon']) < maks_avstand_m:
            return dict(row)
    return None


def opprett_stasjon(navn, kjede, lat, lon, bruker_id):
    naer = finn_naer_stasjon(lat, lon)
    if naer:
        return None, naer
    with get_conn() as conn:
        cursor = conn.execute(
            '''INSERT INTO stasjoner (navn, kjede, lat, lon, lagt_til_av, godkjent)
               VALUES (?, ?, ?, ?, ?, 1)''',
            (navn, kjede or None, lat, lon, bruker_id)
        )
        stasjon_id = cursor.lastrowid
    return stasjon_id, None


def hent_brukerstasjoner() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.sist_oppdatert,
                      b.brukernavn
               FROM stasjoner s
               LEFT JOIN brukere b ON b.id = s.lagt_til_av
               WHERE s.lagt_til_av IS NOT NULL
               ORDER BY s.sist_oppdatert DESC'''
        ).fetchall()
        return [dict(r) for r in rows]


def slett_stasjon(stasjon_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM priser WHERE stasjon_id = ?", (stasjon_id,))
        conn.execute("DELETE FROM stasjoner WHERE id = ? AND lagt_til_av IS NOT NULL", (stasjon_id,))


def get_stasjoner_med_priser(user_lat, user_lon, radius_m=30000, limit=30):
    # Bounding box for å filtrere i SQL først (1 grad ≈ 111 km)
    delta_lat = radius_m / 111_000
    delta_lon = radius_m / (111_000 * max(math.cos(math.radians(user_lat)), 0.01))

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.lagt_til_av,
                      p.bensin, p.diesel, p.bensin98, p.tidspunkt
               FROM stasjoner s
               LEFT JOIN (
                   SELECT stasjon_id, bensin, diesel, bensin98, tidspunkt
                   FROM priser
                   WHERE id IN (SELECT MAX(id) FROM priser GROUP BY stasjon_id)
               ) p ON p.stasjon_id = s.id
               WHERE s.lat BETWEEN ? AND ? AND s.lon BETWEEN ? AND ?''',
            (user_lat - delta_lat, user_lat + delta_lat,
             user_lon - delta_lon, user_lon + delta_lon)
        ).fetchall()

    result = []
    for row in rows:
        dist = _haversine(user_lat, user_lon, row['lat'], row['lon'])
        if dist <= radius_m:
            result.append({
                'id': row['id'],
                'navn': row['navn'],
                'kjede': row['kjede'] or '',
                'lat': row['lat'],
                'lon': row['lon'],
                'bensin': row['bensin'],
                'diesel': row['diesel'],
                'bensin98': row['bensin98'],
                'pris_tidspunkt': row['tidspunkt'],
                'avstand_m': round(dist),
                'brukeropprettet': row['lagt_til_av'] is not None,
            })

    result.sort(key=lambda x: x['avstand_m'])
    return result[:limit]
