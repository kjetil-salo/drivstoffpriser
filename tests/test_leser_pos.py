"""Tester for logg_leser_pos (db.py) og logg-kall fra /api/stasjoner."""

import math
import pytest
import db as db_mod


GYLDIG_LAT = 60.39
GYLDIG_LON = 5.33
DEVICE_ID = "enhet-abc123"


def _antall_loggede(device_id=DEVICE_ID):
    with db_mod.get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM leser_posisjoner WHERE device_id = ?", (device_id,)
        ).fetchone()[0]


def _rydd_rate_limit(device_id=DEVICE_ID):
    with db_mod.get_conn() as conn:
        conn.execute(
            "DELETE FROM rate_limit WHERE type='leser_pos' AND nokkel=?", (device_id,)
        )


# ── DB-funksjon: logg_leser_pos ───────────────────────────────────────────────

class TestLoggLeserPosDB:

    def test_normal_posisjon_lagres(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, GYLDIG_LAT, GYLDIG_LON)
        assert _antall_loggede() == 1

    def test_posisjon_avrundes_til_to_desimaler(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, 60.391234, 5.337891)
        with db_mod.get_conn() as conn:
            row = conn.execute(
                "SELECT lat, lon FROM leser_posisjoner WHERE device_id = ?", (DEVICE_ID,)
            ).fetchone()
        assert row[0] == pytest.approx(60.39)
        assert row[1] == pytest.approx(5.34)

    def test_tom_device_id_ignoreres(self, test_db):
        db_mod.logg_leser_pos("", GYLDIG_LAT, GYLDIG_LON)
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 0

    def test_none_device_id_ignoreres(self, test_db):
        # None er ikke tom streng, men sjekk at det ikke krasjer
        try:
            db_mod.logg_leser_pos(None, GYLDIG_LAT, GYLDIG_LON)
        except Exception as exc:
            pytest.fail(f"logg_leser_pos(None, ...) krasjet: {exc}")
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 0

    def test_nan_lat_ignoreres(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, math.nan, GYLDIG_LON)
        assert _antall_loggede() == 0

    def test_inf_lat_ignoreres(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, math.inf, GYLDIG_LON)
        assert _antall_loggede() == 0

    def test_neg_inf_lon_ignoreres(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, GYLDIG_LAT, -math.inf)
        assert _antall_loggede() == 0

    def test_nan_lon_ignoreres(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, GYLDIG_LAT, math.nan)
        assert _antall_loggede() == 0

    def test_rate_limit_blokkerer_andre_kall_samme_time(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, GYLDIG_LAT, GYLDIG_LON)
        db_mod.logg_leser_pos(DEVICE_ID, 59.91, 10.75)
        # Kun første kall skal lagres
        assert _antall_loggede() == 1

    def test_ulik_device_id_ikke_blokkert(self, test_db):
        db_mod.logg_leser_pos("enhet-A", GYLDIG_LAT, GYLDIG_LON)
        db_mod.logg_leser_pos("enhet-B", GYLDIG_LAT, GYLDIG_LON)
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 2

    def test_andre_kall_tillatt_etter_rate_limit_reset(self, test_db):
        db_mod.logg_leser_pos(DEVICE_ID, GYLDIG_LAT, GYLDIG_LON)
        _rydd_rate_limit()
        db_mod.logg_leser_pos(DEVICE_ID, 59.91, 10.75)
        assert _antall_loggede() == 2

    def test_device_id_trunkeres_ikke_i_db_funksjon(self, test_db):
        """Langt device_id kan passere logg_leser_pos (trunkering gjøres i API-laget)."""
        lang_id = "x" * 200
        db_mod.logg_leser_pos(lang_id, GYLDIG_LAT, GYLDIG_LON)
        with db_mod.get_conn() as conn:
            antall = conn.execute(
                "SELECT COUNT(*) FROM leser_posisjoner WHERE device_id = ?", (lang_id,)
            ).fetchone()[0]
        assert antall == 1


# ── API: /api/stasjoner logger posisjon ──────────────────────────────────────

class TestStasjonerLoggLeserPos:

    def _opprett_stasjon(self):
        db_mod.lagre_stasjon("Testasjon", "YX", GYLDIG_LAT, GYLDIG_LON, "node/9999")

    def test_stasjoner_returnerer_200_med_gyldig_pos(self, client, test_db):
        self._opprett_stasjon()
        resp = client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        assert resp.status_code == 200
        assert "stasjoner" in resp.get_json()

    def test_logg_leser_pos_kalles_ved_gyldig_kall(self, client, test_db):
        self._opprett_stasjon()
        client.set_cookie("device_id", DEVICE_ID)
        client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        assert _antall_loggede() == 1

    def test_feil_i_logg_leser_pos_krasjer_ikke_endepunktet(self, client, test_db, monkeypatch):
        """try/except i ruten skal absorbere unntak fra logg_leser_pos."""
        import routes_api as ra
        def _krasj(*args, **kwargs):
            raise RuntimeError("simulert DB-feil")
        monkeypatch.setattr(ra, "logg_leser_pos", _krasj)
        self._opprett_stasjon()
        resp = client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        assert resp.status_code == 200

    def test_uten_device_id_cookie_logger_ingenting(self, client, test_db):
        self._opprett_stasjon()
        # Ingen cookie satt – device_id blir tom streng
        client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 0

    def test_device_id_cookie_trunkeres_til_64_tegn(self, client, test_db):
        self._opprett_stasjon()
        lang_id = "z" * 100
        client.set_cookie("device_id", lang_id)
        client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        with db_mod.get_conn() as conn:
            row = conn.execute(
                "SELECT device_id FROM leser_posisjoner LIMIT 1"
            ).fetchone()
        assert row is not None
        assert len(row[0]) == 64

    def test_retur_er_korrekt_json_struktur(self, client, test_db):
        self._opprett_stasjon()
        resp = client.get(f"/api/stasjoner?lat={GYLDIG_LAT}&lon={GYLDIG_LON}")
        data = resp.get_json()
        assert isinstance(data.get("stasjoner"), list)

    def test_manglende_lat_gir_400_og_logger_ikke(self, client, test_db):
        resp = client.get(f"/api/stasjoner?lon={GYLDIG_LON}")
        assert resp.status_code == 400
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 0

    def test_koordinat_utenfor_norge_gir_400_og_logger_ikke(self, client, test_db):
        resp = client.get("/api/stasjoner?lat=56.0&lon=5.33")
        assert resp.status_code == 400
        with db_mod.get_conn() as conn:
            antall = conn.execute("SELECT COUNT(*) FROM leser_posisjoner").fetchone()[0]
        assert antall == 0
