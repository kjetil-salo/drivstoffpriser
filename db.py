import sqlite3
import math
import os
import threading
from contextlib import contextmanager
from datetime import datetime

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivstoff.db')
DB_PATH = os.environ.get('DB_PATH', _default_db)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    try:
        conn_test = sqlite3.connect(DB_PATH, timeout=5)
        integrity = conn_test.execute("PRAGMA integrity_check").fetchone()[0]
        conn_test.close()
        if integrity != 'ok':
            raise sqlite3.DatabaseError(f'integrity_check feilet: {integrity}')
    except sqlite3.DatabaseError as e:
        import logging
        logging.getLogger('drivstoff').warning(f'DB korrupt ved oppstart, nullstiller: {e}')
        for path in [DB_PATH, DB_PATH + '-wal', DB_PATH + '-shm']:
            if os.path.exists(path):
                os.remove(path)
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
            CREATE TABLE IF NOT EXISTS innstillinger (
                noekkel  TEXT PRIMARY KEY,
                verdi    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_nøkler (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                partner   TEXT NOT NULL,
                nøkkel    TEXT NOT NULL UNIQUE,
                aktiv     INTEGER NOT NULL DEFAULT 1,
                opprettet TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS api_logg (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                partner    TEXT NOT NULL,
                antall     INTEGER NOT NULL,
                tidspunkt  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS rapporter (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                stasjon_id INTEGER NOT NULL,
                bruker_id  INTEGER NOT NULL,
                tidspunkt  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (stasjon_id) REFERENCES stasjoner(id),
                FOREIGN KEY (bruker_id) REFERENCES brukere(id)
            );
            CREATE TABLE IF NOT EXISTS rate_limit (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                type      TEXT NOT NULL,
                nokkel    TEXT NOT NULL,
                tidspunkt TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_rate_limit ON rate_limit(type, nokkel, tidspunkt);
        ''')


def _migrer_db():
    with get_conn() as conn:
        kolonner = [r[1] for r in conn.execute("PRAGMA table_info(priser)").fetchall()]
        if 'bensin98' not in kolonner:
            conn.execute("ALTER TABLE priser ADD COLUMN bensin98 REAL")
        if 'bruker_id' not in kolonner:
            conn.execute("ALTER TABLE priser ADD COLUMN bruker_id INTEGER REFERENCES brukere(id)")
        if 'diesel_avgiftsfri' not in kolonner:
            conn.execute("ALTER TABLE priser ADD COLUMN diesel_avgiftsfri REAL")

        bruker_kolonner = [r[1] for r in conn.execute("PRAGMA table_info(brukere)").fetchall()]
        if 'kallenavn' not in bruker_kolonner:
            conn.execute("ALTER TABLE brukere ADD COLUMN kallenavn TEXT")
        if 'roller' not in bruker_kolonner:
            conn.execute("ALTER TABLE brukere ADD COLUMN roller TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE brukere SET roller='admin' WHERE er_admin=1")

        stasjon_kolonner = [r[1] for r in conn.execute("PRAGMA table_info(stasjoner)").fetchall()]
        if 'lagt_til_av' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN lagt_til_av INTEGER REFERENCES brukere(id)")
        if 'godkjent' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN godkjent INTEGER DEFAULT 1")
        if 'land' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN land TEXT")
        if 'navn_låst' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN navn_låst INTEGER NOT NULL DEFAULT 0")
        if 'kjede_låst' not in stasjon_kolonner:
            conn.execute("ALTER TABLE stasjoner ADD COLUMN kjede_låst INTEGER NOT NULL DEFAULT 0")

        # Rapporter-tabell og blogg_visninger (migrering)
        tabeller = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'blogg_visninger' not in tabeller:
            conn.execute('''CREATE TABLE blogg_visninger (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                ts   TEXT DEFAULT (datetime('now'))
            )''')
            conn.execute("CREATE INDEX idx_blogg_visninger_slug ON blogg_visninger(slug)")
        if 'rapporter' not in tabeller:
            conn.execute('''CREATE TABLE rapporter (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                stasjon_id INTEGER NOT NULL,
                bruker_id  INTEGER NOT NULL,
                tidspunkt  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (stasjon_id) REFERENCES stasjoner(id),
                FOREIGN KEY (bruker_id) REFERENCES brukere(id)
            )''')
        if 'endringsforslag' not in tabeller:
            conn.execute('''CREATE TABLE endringsforslag (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                stasjon_id       INTEGER NOT NULL,
                bruker_id        INTEGER,
                foreslatt_navn   TEXT,
                foreslatt_kjede  TEXT,
                tidspunkt        TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (stasjon_id) REFERENCES stasjoner(id),
                FOREIGN KEY (bruker_id) REFERENCES brukere(id)
            )''')
        if 'rate_limit' not in tabeller:
            conn.execute('''CREATE TABLE rate_limit (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                type      TEXT NOT NULL,
                nokkel    TEXT NOT NULL,
                tidspunkt TEXT DEFAULT (datetime('now'))
            )''')
            conn.execute('CREATE INDEX idx_rate_limit ON rate_limit(type, nokkel, tidspunkt)')


def sjekk_rate_limit(type: str, nokkel: str, maks: int, vindu_sekunder: int) -> bool:
    """Returner True hvis nokkel har nådd maks antall hendelser i vindu_sekunder."""
    with get_conn() as conn:
        antall = conn.execute(
            "SELECT COUNT(*) FROM rate_limit WHERE type=? AND nokkel=? "
            "AND tidspunkt > datetime('now', ? || ' seconds')",
            (type, nokkel, f'-{vindu_sekunder}')
        ).fetchone()[0]
    return antall >= maks


def logg_rate_limit(type: str, nokkel: str):
    """Registrer én hendelse for nokkel."""
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO rate_limit (type, nokkel) VALUES (?, ?)',
            (type, nokkel)
        )
        # Rydd bort rader eldre enn 2 timer løpende
        conn.execute(
            "DELETE FROM rate_limit WHERE tidspunkt < datetime('now', '-2 hours')"
        )


def slett_rate_limit(type: str, nokkel: str):
    """Fjern alle hendelser for nokkel (brukes ved vellykket innlogging)."""
    with get_conn() as conn:
        conn.execute('DELETE FROM rate_limit WHERE type=? AND nokkel=?', (type, nokkel))


def hent_innstilling(noekkel, standard=None):
    with get_conn() as conn:
        row = conn.execute('SELECT verdi FROM innstillinger WHERE noekkel = ?', (noekkel,)).fetchone()
        return row[0] if row else standard


def sett_innstilling(noekkel, verdi):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO innstillinger (noekkel, verdi) VALUES (?, ?) ON CONFLICT(noekkel) DO UPDATE SET verdi=excluded.verdi',
            (noekkel, str(verdi))
        )


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371e3
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))



def lagre_stasjon(navn, kjede, lat, lon, osm_id, land=None):
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO stasjoner (navn, kjede, lat, lon, osm_id, land)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(osm_id) DO UPDATE SET
                 navn=CASE WHEN stasjoner.navn_låst=1 THEN stasjoner.navn ELSE excluded.navn END,
                 kjede=CASE WHEN stasjoner.kjede_låst=1 THEN stasjoner.kjede ELSE COALESCE(excluded.kjede, stasjoner.kjede) END,
                 lat=excluded.lat, lon=excluded.lon,
                 land=COALESCE(excluded.land, stasjoner.land),
                 sist_oppdatert=datetime('now')''',
            (navn, kjede, lat, lon, osm_id, land)
        )


_pris_lock = threading.Lock()


def lagre_pris(stasjon_id, bensin, diesel, bensin98=None, bruker_id=None, diesel_avgiftsfri=None, min_intervall=300):
    """Lagrer pris. Oppdaterer siste rad hvis bruker korrigerer innen intervallet, ellers insert."""
    with _pris_lock:
        with get_conn() as conn:
            if bruker_id is not None:
                sist = conn.execute(
                    "SELECT id, tidspunkt FROM priser WHERE bruker_id=? AND stasjon_id=? ORDER BY tidspunkt DESC LIMIT 1",
                    (bruker_id, stasjon_id)
                ).fetchone()
                if sist:
                    sekunder_siden = (datetime.now() - datetime.strptime(sist[1], '%Y-%m-%d %H:%M:%S')).total_seconds()
                    if sekunder_siden < min_intervall:
                        conn.execute(
                            'UPDATE priser SET bensin=?, diesel=?, bensin98=?, diesel_avgiftsfri=?, tidspunkt=datetime("now") WHERE id=?',
                            (bensin, diesel, bensin98, diesel_avgiftsfri, sist[0])
                        )
                        return True
            conn.execute(
                'INSERT INTO priser (stasjon_id, bensin, diesel, bensin98, bruker_id, diesel_avgiftsfri) VALUES (?, ?, ?, ?, ?, ?)',
                (stasjon_id, bensin, diesel, bensin98, bruker_id, diesel_avgiftsfri)
            )
    return True


def hent_siste_prisoppdateringer(limit=100) -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT p.id, p.bensin, p.diesel, p.bensin98, p.diesel_avgiftsfri, p.tidspunkt,
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


def unike_enheter_per_dag(dager: int = 30) -> list[dict]:
    from datetime import date, timedelta
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        today = date.today()
        dato_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(dager - 1, -1, -1)}
        for row in conn.execute(
            "SELECT DATE(ts) AS dato, COUNT(DISTINCT device_id) AS antall "
            "FROM visninger WHERE device_id != '' AND ts >= DATE('now', ?) "
            "GROUP BY dato",
            (f'-{dager - 1} days',)
        ).fetchall():
            if row['dato'] in dato_map:
                dato_map[row['dato']] = row['antall']
        return [{'dato': d, 'antall': n} for d, n in dato_map.items()]


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
            "FROM visninger WHERE ts >= datetime('now', '-24 hours') "
            "GROUP BY time ORDER BY time"
        ).fetchall()

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    timer_map = {}
    for i in range(24, -1, -1):
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
            '''SELECT p.bensin, p.diesel, p.bensin98, p.diesel_avgiftsfri, p.tidspunkt,
                      s.id, s.navn, s.kjede, s.lat, s.lon
               FROM priser p
               JOIN stasjoner s ON s.id = p.stasjon_id
               WHERE s.godkjent != 0
                 AND (s.land IS NULL OR s.land = 'NO')
                 AND p.tidspunkt > datetime('now', '-24 hours')
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


def nye_brukere_per_time_48t() -> list:
    """Antall nye brukere per time siste 48 timer."""
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    timer_map = {}
    for i in range(48, -1, -1):
        t = (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00:00')
        timer_map[t] = 0
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00:00', opprettet) as time, COUNT(*) as cnt "
            "FROM brukere WHERE opprettet >= datetime('now', '-48 hours') "
            "GROUP BY time ORDER BY time"
        ).fetchall():
            if row['time'] in timer_map:
                timer_map[row['time']] = row['cnt']
    return list(timer_map.items())


def prisoppdateringer_rullende_24t_uke() -> list:
    """Rullende 24-timers sum per time, siste 10 dager (240 punkter)."""
    import bisect
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tidspunkt FROM priser "
            "WHERE tidspunkt >= datetime('now', '-11 days') ORDER BY tidspunkt"
        ).fetchall()
    timestamps = []
    for (ts_str,) in rows:
        t = datetime.fromisoformat(ts_str)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        timestamps.append(t.timestamp())
    result = []
    for i in range(10 * 24, -1, -1):
        slot = now - timedelta(hours=i)
        slot_end = slot.timestamp()
        slot_start = (slot - timedelta(hours=24)).timestamp()
        left = bisect.bisect_left(timestamps, slot_start)
        right = bisect.bisect_right(timestamps, slot_end)
        result.append((slot.strftime('%Y-%m-%d %H:00:00'), right - left))
    return result


def prisoppdateringer_per_time_24t() -> list:
    """Antall prisoppdateringer per time siste 24 timer."""
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    timer_map = {}
    for i in range(24, -1, -1):
        t = (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00:00')
        timer_map[t] = 0
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00:00', tidspunkt) as time, COUNT(*) as cnt "
            "FROM priser WHERE tidspunkt >= datetime('now', '-24 hours') "
            "GROUP BY time ORDER BY time"
        ).fetchall():
            if row['time'] in timer_map:
                timer_map[row['time']] = row['cnt']
    return list(timer_map.items())


def prisoppdateringer_per_time_48t() -> list:
    """Antall prisoppdateringer per time siste 48 timer."""
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    timer_map = {}
    for i in range(48, -1, -1):
        t = (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00:00')
        timer_map[t] = 0
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00:00', tidspunkt) as time, COUNT(*) as cnt "
            "FROM priser WHERE tidspunkt >= datetime('now', '-48 hours') "
            "GROUP BY time ORDER BY time"
        ).fetchall():
            if row['time'] in timer_map:
                timer_map[row['time']] = row['cnt']
    return list(timer_map.items())


def antall_prisoppdateringer_24t() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM priser WHERE tidspunkt > datetime('now', '-24 hours')"
        ).fetchone()[0]


def antall_stasjoner_med_pris() -> int:
    with get_conn() as conn:
        return conn.execute(
            '''SELECT COUNT(DISTINCT stasjon_id) FROM priser
               WHERE bensin IS NOT NULL OR diesel IS NOT NULL OR bensin98 IS NOT NULL OR diesel_avgiftsfri IS NOT NULL'''
        ).fetchone()[0]


def stasjoner_med_pris_koordinater() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            '''SELECT s.navn, s.kjede, s.lat, s.lon,
                      p.bensin, p.diesel, p.bensin98, p.diesel_avgiftsfri, p.tidspunkt
               FROM stasjoner s
               JOIN priser p ON p.stasjon_id = s.id
               WHERE p.id = (SELECT MAX(p2.id) FROM priser p2 WHERE p2.stasjon_id = s.id)
                 AND (p.bensin IS NOT NULL OR p.diesel IS NOT NULL OR p.bensin98 IS NOT NULL OR p.diesel_avgiftsfri IS NOT NULL)'''
        ).fetchall()]


def antall_brukere() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM brukere").fetchone()[0]


def har_rolle(bruker: dict, rolle: str) -> bool:
    if not bruker:
        return False
    return rolle in (bruker.get('roller') or '').split()


def sett_roller_bruker(bruker_id: int, roller: list[str]):
    roller_str = ' '.join(sorted(set(roller)))
    er_admin = 1 if 'admin' in roller else 0
    with get_conn() as conn:
        conn.execute(
            "UPDATE brukere SET roller=?, er_admin=? WHERE id=?",
            (roller_str, er_admin, bruker_id)
        )


def opprett_bruker(brukernavn: str, passord_hash: str, er_admin: bool = False):
    roller = 'admin' if er_admin else ''
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO brukere (brukernavn, passord_hash, er_admin, roller) VALUES (?, ?, ?, ?)",
            (brukernavn, passord_hash, 1 if er_admin else 0, roller)
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


def hent_alle_brukere(sok: str = '', side: int = 1, per_side: int = 50) -> tuple[list, int]:
    offset = (side - 1) * per_side
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        if sok:
            mønster = f'%{sok}%'
            totalt = conn.execute(
                "SELECT COUNT(*) FROM brukere WHERE brukernavn LIKE ?", (mønster,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT id, brukernavn, er_admin, roller, opprettet FROM brukere "
                "WHERE brukernavn LIKE ? ORDER BY opprettet DESC LIMIT ? OFFSET ?",
                (mønster, per_side, offset)
            ).fetchall()
        else:
            totalt = conn.execute("SELECT COUNT(*) FROM brukere").fetchone()[0]
            rows = conn.execute(
                "SELECT id, brukernavn, er_admin, roller, opprettet FROM brukere "
                "ORDER BY opprettet DESC LIMIT ? OFFSET ?",
                (per_side, offset)
            ).fetchall()
        return [dict(r) for r in rows], totalt


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


def sett_kallenavn(bruker_id: int, kallenavn: str):
    with get_conn() as conn:
        conn.execute("UPDATE brukere SET kallenavn = ? WHERE id = ?",
                     (kallenavn or None, bruker_id))


def sett_kjede_for_stasjon(stasjon_id: int, kjede: str):
    with get_conn() as conn:
        conn.execute("UPDATE stasjoner SET kjede = ?, kjede_låst = 1 WHERE id = ?",
                     (kjede or None, stasjon_id))


def oppdater_passord(epost: str, passord_hash: str):
    with get_conn() as conn:
        conn.execute("UPDATE brukere SET passord_hash = ? WHERE brukernavn = ?", (passord_hash, epost))


def logg_blogg_visning(slug: str):
    with get_conn() as conn:
        conn.execute('INSERT INTO blogg_visninger (slug) VALUES (?)', (slug,))


def hent_blogg_stats() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT slug, COUNT(*) as antall FROM blogg_visninger GROUP BY slug ORDER BY antall DESC'
        ).fetchall()
        return [dict(r) for r in rows]


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
               WHERE (godkjent = 1 OR (godkjent = 0 AND lagt_til_av IS NOT NULL))
               AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?''',
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


def deaktiver_stasjon(stasjon_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE stasjoner SET godkjent = 0 WHERE id = ?", (stasjon_id,))


def reaktiver_stasjon(stasjon_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE stasjoner SET godkjent = 1 WHERE id = ?", (stasjon_id,))


def hent_deaktiverte_stasjoner() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.sist_oppdatert
               FROM stasjoner s
               WHERE s.godkjent = 0 AND s.lagt_til_av IS NULL
               ORDER BY s.sist_oppdatert DESC'''
        ).fetchall()
        return [dict(r) for r in rows]


def hent_ventende_stasjoner(filter='alle') -> list:
    """Henter bruker-opprettede stasjoner. filter: 'ventende', 'idag', 'alle'"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        if filter == 'ventende':
            where = "s.lagt_til_av IS NOT NULL AND s.godkjent = 0"
        elif filter == 'idag':
            where = "s.lagt_til_av IS NOT NULL AND date(s.sist_oppdatert) = date('now')"
        else:
            where = "s.lagt_til_av IS NOT NULL"
        rows = conn.execute(
            f'''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.sist_oppdatert, s.godkjent,
                       b.brukernavn, b.kallenavn
                FROM stasjoner s
                LEFT JOIN brukere b ON b.id = s.lagt_til_av
                WHERE {where}
                ORDER BY s.sist_oppdatert DESC
                LIMIT 200'''
        ).fetchall()
        return [dict(r) for r in rows]


def antall_ventende_stasjoner() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM stasjoner WHERE lagt_til_av IS NOT NULL AND godkjent = 0"
        ).fetchone()
        return row[0]


def godkjenn_stasjon(stasjon_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE stasjoner SET godkjent = 1 WHERE id = ? AND lagt_til_av IS NOT NULL", (stasjon_id,))


def meld_stasjon_nedlagt(stasjon_id: int, bruker_id: int):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO rapporter (stasjon_id, bruker_id) VALUES (?, ?)',
            (stasjon_id, bruker_id)
        )


def hent_rapporter() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT r.id, r.stasjon_id, r.tidspunkt,
                      s.navn, s.kjede, s.lat, s.lon, s.godkjent,
                      b.brukernavn,
                      (SELECT COUNT(*) FROM rapporter r2 WHERE r2.stasjon_id = r.stasjon_id) as antall
               FROM rapporter r
               JOIN stasjoner s ON s.id = r.stasjon_id
               LEFT JOIN brukere b ON b.id = r.bruker_id
               WHERE s.godkjent != 0
               GROUP BY r.stasjon_id
               ORDER BY antall DESC, r.tidspunkt DESC'''
        ).fetchall()
        return [dict(r) for r in rows]


def hent_rapportorer_epost(stasjon_id: int) -> tuple[str, list[str]]:
    """Hent stasjonsnavn og unike e-poster for brukere som rapporterte stasjonen."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        navn = conn.execute(
            "SELECT navn FROM stasjoner WHERE id = ?", (stasjon_id,)
        ).fetchone()
        stasjonsnavn = dict(navn)['navn'] if navn else 'Ukjent stasjon'
        rows = conn.execute(
            '''SELECT DISTINCT b.brukernavn
               FROM rapporter r JOIN brukere b ON b.id = r.bruker_id
               WHERE r.stasjon_id = ?''',
            (stasjon_id,)
        ).fetchall()
        return stasjonsnavn, [dict(r)['brukernavn'] for r in rows]


def slett_rapporter_for_stasjon(stasjon_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM rapporter WHERE stasjon_id = ?", (stasjon_id,))


def antall_ubehandlede_rapporter() -> int:
    with get_conn() as conn:
        return conn.execute(
            '''SELECT COUNT(DISTINCT r.stasjon_id) FROM rapporter r
               JOIN stasjoner s ON s.id = r.stasjon_id WHERE s.godkjent != 0'''
        ).fetchone()[0]


def legg_til_endringsforslag(stasjon_id: int, bruker_id: int, foreslatt_navn: str | None, foreslatt_kjede: str | None):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO endringsforslag (stasjon_id, bruker_id, foreslatt_navn, foreslatt_kjede) VALUES (?, ?, ?, ?)',
            (stasjon_id, bruker_id, foreslatt_navn or None, foreslatt_kjede or None)
        )


def hent_endringsforslag() -> list:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT e.id, e.stasjon_id, e.foreslatt_navn, e.foreslatt_kjede, e.tidspunkt,
                      s.navn, s.kjede, s.lat, s.lon,
                      b.brukernavn
               FROM endringsforslag e
               JOIN stasjoner s ON s.id = e.stasjon_id
               LEFT JOIN brukere b ON b.id = e.bruker_id
               ORDER BY e.tidspunkt DESC'''
        ).fetchall()
        return [dict(r) for r in rows]


def slett_endringsforslag(forslag_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM endringsforslag WHERE id = ?", (forslag_id,))


def antall_ubehandlede_endringsforslag() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM endringsforslag").fetchone()[0]


def hent_toppliste(limit=50) -> list:
    """Antall prisregistreringer per bruker, ekskluderer partnere."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT b.id, b.kallenavn, COUNT(p.id) as antall
               FROM priser p
               JOIN brukere b ON b.id = p.bruker_id
               WHERE b.brukernavn NOT LIKE 'partner:%'
               GROUP BY p.bruker_id
               ORDER BY antall DESC
               LIMIT ?''',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def hent_toppliste_uke(limit=20) -> list:
    """Antall prisregistreringer per bruker siste 7 dager, ekskluderer partnere."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT b.id, b.kallenavn, COUNT(p.id) as antall
               FROM priser p
               JOIN brukere b ON b.id = p.bruker_id
               WHERE b.brukernavn NOT LIKE 'partner:%'
                 AND p.tidspunkt >= datetime('now', '-7 days')
               GROUP BY p.bruker_id
               ORDER BY antall DESC
               LIMIT ?''',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def hent_min_plassering(bruker_id) -> dict | None:
    """Hent plassering og antall for en bestemt bruker (ekskluderer partnere)."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rad = conn.execute(
            '''SELECT COUNT(p.id) as antall
               FROM priser p
               JOIN brukere b ON b.id = p.bruker_id
               WHERE p.bruker_id = ? AND b.brukernavn NOT LIKE 'partner:%' ''',
            (bruker_id,)
        ).fetchone()
        if not rad or rad['antall'] == 0:
            return None
        antall = rad['antall']
        plass_rad = conn.execute(
            '''SELECT COUNT(*) + 1 as plass
               FROM (
                   SELECT p2.bruker_id
                   FROM priser p2
                   JOIN brukere b2 ON b2.id = p2.bruker_id
                   WHERE b2.brukernavn NOT LIKE 'partner:%'
                   GROUP BY p2.bruker_id
                   HAVING COUNT(p2.id) > ?
               )''',
            (antall,)
        ).fetchone()
        return {'plass': plass_rad['plass'], 'antall': antall}


def hent_toppliste_admin(limit=50) -> list:
    """Toppliste med navn og epost, kun for admin-visning."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT b.id, b.brukernavn, b.kallenavn, COUNT(p.id) as antall
               FROM priser p
               JOIN brukere b ON b.id = p.bruker_id
               WHERE b.brukernavn NOT LIKE 'partner:%'
               GROUP BY p.bruker_id
               ORDER BY antall DESC
               LIMIT ?''',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def finn_stasjoner_by_navn(navn: str) -> list:
    """Søk etter stasjoner med navn som matcher (case-insensitive)."""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT id, navn, kjede, lat, lon FROM stasjoner
               WHERE godkjent != 0 AND LOWER(navn) LIKE ?
               LIMIT 5''',
            (f'%{navn.lower()}%',)
        ).fetchall()
        return [dict(r) for r in rows]


def endre_navn_stasjon(stasjon_id: int, nytt_navn: str) -> bool:
    """Endre navn på en stasjon. Returnerer True hvis stasjonen ble funnet og oppdatert."""
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE stasjoner SET navn = ?, navn_låst = 1 WHERE id = ?",
            (nytt_navn, stasjon_id)
        )
        return cursor.rowcount > 0


def hent_eller_opprett_partner(navn: str) -> int:
    """Hent bruker_id for partner, opprett hvis ikke finnes."""
    brukernavn = f'partner:{navn}'
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id FROM brukere WHERE brukernavn = ?', (brukernavn,)
        ).fetchone()
        if row:
            return row[0]
        cursor = conn.execute(
            "INSERT INTO brukere (brukernavn, passord_hash, er_admin) VALUES (?, '', 0)",
            (brukernavn,)
        )
        return cursor.lastrowid


def finn_stasjoner_by_osm_ids(osm_ids: list) -> dict:
    """Slå opp stasjoner via OSM-id-er. Returnerer {original_id: {id, navn, kjede, ...}}.
    Håndterer at vår DB bruker 'node/'-prefix mens partnere kan sende bare tallet."""
    if not osm_ids:
        return {}
    # Bygg oppslag med node/-prefix for id-er som mangler det
    søk_ids = []
    prefiks_map = {}  # node/123 -> 123 (original)
    for oid in osm_ids:
        if oid.startswith('node/') or oid.startswith('way/'):
            søk_ids.append(oid)
            prefiks_map[oid] = oid
        else:
            full_id = f'node/{oid}'
            søk_ids.append(full_id)
            prefiks_map[full_id] = oid
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ','.join('?' for _ in søk_ids)
        rows = conn.execute(
            f'''SELECT id, navn, kjede, lat, lon, osm_id FROM stasjoner
                WHERE godkjent != 0 AND osm_id IN ({placeholders})''',
            søk_ids
        ).fetchall()
        # Returner med original-id som nøkkel
        return {prefiks_map.get(r['osm_id'], r['osm_id']): dict(r) for r in rows}


def get_stasjoner_med_priser(user_lat, user_lon, radius_m=30000, limit=30):
    # Bounding box for å filtrere i SQL først (1 grad ≈ 111 km)
    delta_lat = radius_m / 111_000
    delta_lon = radius_m / (111_000 * max(math.cos(math.radians(user_lat)), 0.01))

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.lagt_til_av,
                      (SELECT NULLIF(bensin,   0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS bensin,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND bensin  IS NOT NULL AND bensin   > 0 ORDER BY id DESC LIMIT 1) AS bensin_tidspunkt,
                      (SELECT NULLIF(diesel,   0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS diesel,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND diesel  IS NOT NULL AND diesel   > 0 ORDER BY id DESC LIMIT 1) AS diesel_tidspunkt,
                      (SELECT NULLIF(bensin98, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS bensin98,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND bensin98 IS NOT NULL AND bensin98 > 0 ORDER BY id DESC LIMIT 1) AS bensin98_tidspunkt,
                      (SELECT NULLIF(diesel_avgiftsfri, 0) FROM priser WHERE stasjon_id=s.id ORDER BY id DESC LIMIT 1) AS diesel_avgiftsfri,
                      (SELECT tidspunkt FROM priser WHERE stasjon_id=s.id AND diesel_avgiftsfri IS NOT NULL AND diesel_avgiftsfri > 0 ORDER BY id DESC LIMIT 1) AS diesel_avgiftsfri_tidspunkt
               FROM stasjoner s
               WHERE s.godkjent != 0
                 AND s.lat BETWEEN ? AND ? AND s.lon BETWEEN ? AND ?''',
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
                'bensin_tidspunkt': row['bensin_tidspunkt'],
                'diesel': row['diesel'],
                'diesel_tidspunkt': row['diesel_tidspunkt'],
                'bensin98': row['bensin98'],
                'bensin98_tidspunkt': row['bensin98_tidspunkt'],
                'diesel_avgiftsfri': row['diesel_avgiftsfri'],
                'diesel_avgiftsfri_tidspunkt': row['diesel_avgiftsfri_tidspunkt'],
                'avstand_m': round(dist),
                'brukeropprettet': row['lagt_til_av'] is not None,
            })

    result.sort(key=lambda x: x['avstand_m'])
    return result[:limit]
