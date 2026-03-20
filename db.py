import sqlite3
import math
import os

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivstoff.db')
DB_PATH = os.environ.get('DB_PATH', _default_db)


def get_conn():
    return sqlite3.connect(DB_PATH)


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
                tidspunkt TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (stasjon_id) REFERENCES stasjoner(id)
            );
            CREATE TABLE IF NOT EXISTS visninger (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ip        TEXT,
                device_id TEXT,
                user_agent TEXT,
                ts        TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_visninger_device ON visninger(device_id);
            CREATE INDEX IF NOT EXISTS idx_visninger_ts ON visninger(ts);
        ''')


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371e3
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def har_ferske_stasjoner(lat, lon, max_alder_timer=24):
    """Sjekk om det finnes ferske stasjoner nær denne posisjonen (bounding box ±0.15 grader ≈ ~15km)."""
    delta = 0.15
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT COUNT(*) FROM stasjoner
               WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
               AND sist_oppdatert > datetime('now', ? || ' hours')''',
            (lat - delta, lat + delta, lon - delta, lon + delta, f'-{max_alder_timer}')
        ).fetchone()
        return row[0] > 0


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


def lagre_pris(stasjon_id, bensin, diesel):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO priser (stasjon_id, bensin, diesel) VALUES (?, ?, ?)',
            (stasjon_id, bensin, diesel)
        )


def get_statistikk() -> dict:
    from datetime import date, timedelta
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        totalt = conn.execute("SELECT COUNT(*) FROM visninger").fetchone()[0]
        unike_enheter = conn.execute(
            "SELECT COUNT(DISTINCT device_id) FROM visninger WHERE device_id != ''"
        ).fetchone()[0]
        unike_ips = conn.execute("SELECT COUNT(DISTINCT ip) FROM visninger").fetchone()[0]

        today = date.today()
        trend_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
        for row in conn.execute(
            "SELECT DATE(ts) as dato, COUNT(*) as cnt FROM visninger "
            "WHERE ts >= DATE('now', '-29 days') GROUP BY dato"
        ).fetchall():
            if row['dato'] in trend_map:
                trend_map[row['dato']] = row['cnt']

        siste_besok = conn.execute(
            "SELECT ip, device_id, ts FROM visninger ORDER BY ts DESC LIMIT 10"
        ).fetchall()

    return {
        'totalt': totalt,
        'unike_enheter': unike_enheter,
        'unike_ips': unike_ips,
        'trend_30d': list(trend_map.items()),
        'siste_besok': [dict(r) for r in siste_besok],
    }


def logg_visning(ip: str, device_id: str, user_agent: str):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO visninger (ip, device_id, user_agent) VALUES (?, ?, ?)',
            (ip, device_id, user_agent)
        )


def get_stasjoner_med_priser(user_lat, user_lon, radius_m=20000, limit=15):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon,
                      p.bensin, p.diesel, p.tidspunkt
               FROM stasjoner s
               LEFT JOIN (
                   SELECT stasjon_id, bensin, diesel, tidspunkt
                   FROM priser
                   WHERE id IN (SELECT MAX(id) FROM priser GROUP BY stasjon_id)
               ) p ON p.stasjon_id = s.id'''
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
                'pris_tidspunkt': row['tidspunkt'],
                'avstand_m': round(dist),
            })

    result.sort(key=lambda x: x['avstand_m'])
    return result[:limit]
