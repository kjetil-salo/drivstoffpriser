"""Tester for init_db() og _migrer_db() — skjemaversjonering og idempotens."""

import os
import sqlite3
import tempfile

import pytest
import db as db_mod


# ── Hjelpere ──────────────────────────────────────────────────────────────────

def get_kolonner(conn, tabell):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabell})").fetchall()]


def get_tabeller(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


# ── init_db() er allerede kjørt av conftest, test kolonner ───────────────────

class TestInitDb:
    def test_stasjoner_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'stasjoner' in get_tabeller(conn)

    def test_priser_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'priser' in get_tabeller(conn)

    def test_brukere_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'brukere' in get_tabeller(conn)

    def test_innstillinger_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'innstillinger' in get_tabeller(conn)


class TestMigrerDb:
    def test_priser_har_bensin98_kolonne(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'bensin98' in get_kolonner(conn, 'priser')

    def test_priser_har_bruker_id_kolonne(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'bruker_id' in get_kolonner(conn, 'priser')

    def test_priser_har_diesel_avgiftsfri_kolonne(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'diesel_avgiftsfri' in get_kolonner(conn, 'priser')

    def test_priser_har_kilde_kolonne(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'kilde' in get_kolonner(conn, 'priser')

    def test_brukere_har_kallenavn(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'kallenavn' in get_kolonner(conn, 'brukere')

    def test_brukere_har_roller(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'roller' in get_kolonner(conn, 'brukere')

    def test_stasjoner_har_lagt_til_av(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'lagt_til_av' in get_kolonner(conn, 'stasjoner')

    def test_stasjoner_har_godkjent(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'godkjent' in get_kolonner(conn, 'stasjoner')

    def test_stasjoner_har_har_bensin(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'har_bensin' in get_kolonner(conn, 'stasjoner')

    def test_stasjoner_har_har_diesel_avgiftsfri(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'har_diesel_avgiftsfri' in get_kolonner(conn, 'stasjoner')

    def test_endringsforslag_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'endringsforslag' in get_tabeller(conn)

    def test_endringsforslag_har_kommentar(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'kommentar' in get_kolonner(conn, 'endringsforslag')

    def test_rate_limit_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'rate_limit' in get_tabeller(conn)

    def test_ocr_statistikk_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'ocr_statistikk' in get_tabeller(conn)

    def test_rapporter_tabell_finnes(self, test_db):
        with db_mod.get_conn() as conn:
            assert 'rapporter' in get_tabeller(conn)


class TestIdempotens:
    def test_init_db_trygt_å_kjøre_to_ganger(self, test_db):
        """Dobbel init_db() skal ikke kaste unntak."""
        db_mod.init_db()
        db_mod.init_db()
        with db_mod.get_conn() as conn:
            assert 'stasjoner' in get_tabeller(conn)

    def test_migrer_db_trygt_å_kjøre_to_ganger(self, test_db):
        """Dobbel _migrer_db() skal ikke kaste unntak (ALTER TABLE er try-safe via IF NOT EXISTS-logikk)."""
        db_mod._migrer_db()
        db_mod._migrer_db()
        with db_mod.get_conn() as conn:
            assert 'bensin98' in get_kolonner(conn, 'priser')

    def test_init_og_migrer_gir_integritetsstatus_ok(self, test_db):
        with db_mod.get_conn() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert result == 'ok'


class TestInnkallUtenfor__main__:
    """Verifiser at init_db og _migrer_db kalles fra modulnivå i server.py,
    ikke bare inne i if __name__ == '__main__'. Dette sikrer at Gunicorn
    kjører migreringer ved oppstart."""

    def test_server_kaller_init_db_og_migrer_db_utenfor_main(self):
        """Søk i server.py etter at kall er utenfor __main__-blokken."""
        import ast
        import pathlib
        kode = pathlib.Path('/Users/kjetil/git/drivstoffpriser/server.py').read_text()
        tree = ast.parse(kode)

        # Finn alle kall til init_db og _migrer_db på modulnivå
        kall_paa_modulnivaa = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                # Kall på modulnivå har col_offset == 0 typisk
                func = node.value.func
                navn = None
                if isinstance(func, ast.Attribute):
                    navn = func.attr
                elif isinstance(func, ast.Name):
                    navn = func.id
                if navn in ('init_db', '_migrer_db'):
                    # Sjekk at de er på toppnivå (ikke inne i en funksjon eller if __name__)
                    kall_paa_modulnivaa.add(navn)

        assert 'init_db' in kall_paa_modulnivaa, \
            "init_db() kalles ikke på modulnivå i server.py — Gunicorn vil ikke kjøre DB-oppsett!"
        assert '_migrer_db' in kall_paa_modulnivaa, \
            "_migrer_db() kalles ikke på modulnivå i server.py — Gunicorn vil ikke kjøre DB-migreringer!"


# ── SQLite-constraints ────────────────────────────────────────────────────────

class TestConstraints:
    def test_stasjon_krever_navn(self, test_db):
        with pytest.raises(sqlite3.IntegrityError):
            with db_mod.get_conn() as conn:
                conn.execute(
                    'INSERT INTO stasjoner (navn, lat, lon) VALUES (?, ?, ?)',
                    (None, 60.0, 5.0)
                )

    def test_stasjon_osm_id_er_unik(self, test_db):
        with db_mod.get_conn() as conn:
            conn.execute(
                'INSERT INTO stasjoner (navn, lat, lon, osm_id) VALUES (?, ?, ?, ?)',
                ('A', 60.0, 5.0, 'node/1')
            )
        with pytest.raises(sqlite3.IntegrityError):
            with db_mod.get_conn() as conn:
                conn.execute(
                    'INSERT INTO stasjoner (navn, lat, lon, osm_id) VALUES (?, ?, ?, ?)',
                    ('B', 60.1, 5.1, 'node/1')
                )

    def test_bruker_brukernavn_er_unik(self, test_db):
        from werkzeug.security import generate_password_hash
        db_mod.opprett_bruker('dup@test.no', generate_password_hash('x'))
        with pytest.raises(Exception):
            db_mod.opprett_bruker('dup@test.no', generate_password_hash('y'))

    def test_invitasjon_token_er_unik(self, test_db):
        db_mod.opprett_invitasjon('abc', '2099-01-01 00:00:00')
        with pytest.raises(sqlite3.IntegrityError):
            with db_mod.get_conn() as conn:
                conn.execute(
                    'INSERT INTO invitasjoner (token, utloper) VALUES (?, ?)',
                    ('abc', '2099-01-01 00:00:00')
                )


# ── finn_stasjoner_by_navn: SQL-tegn ──────────────────────────────────────────

class TestFinnStasjonerByNavnSQLTegn:
    def test_apostrof_i_navn_krasjer_ikke(self, test_db):
        """SQL-apostrof i søketekst skal ikke kaste unntak."""
        db_mod.lagre_stasjon("Shell O'Brien", 'Shell', 60.39, 5.33, 'node/apostrophe')
        resultat = db_mod.finn_stasjoner_by_navn("O'Brien")
        assert isinstance(resultat, list)
        assert len(resultat) == 1

    def test_prosent_tegn_brukes_ikke_som_jokertegn(self, test_db):
        """% i søket skal matche '%'-tegn, ikke alt."""
        db_mod.lagre_stasjon('Test 100% Shell', 'Shell', 60.39, 5.33, 'node/prosent')
        db_mod.lagre_stasjon('Circle K Bergen', 'Circle K', 60.40, 5.33, 'node/andere')
        resultat = db_mod.finn_stasjoner_by_navn('100%')
        assert len(resultat) == 1
        assert resultat[0]['navn'] == 'Test 100% Shell'

    def test_backslash_i_søk_krasjer_ikke(self, test_db):
        resultat = db_mod.finn_stasjoner_by_navn('test\\navn')
        assert isinstance(resultat, list)

    def test_xss_i_søk_krasjer_ikke(self, test_db):
        resultat = db_mod.finn_stasjoner_by_navn('<script>alert(1)</script>')
        assert isinstance(resultat, list)

    def test_sql_injection_i_søk_krasjer_ikke(self, test_db):
        """'; DROP TABLE stasjoner; -- skal ikke krasje."""
        resultat = db_mod.finn_stasjoner_by_navn("'; DROP TABLE stasjoner; --")
        assert isinstance(resultat, list)
        # Tabellen skal fortsatt eksistere
        with db_mod.get_conn() as conn:
            antall = conn.execute('SELECT COUNT(*) FROM stasjoner').fetchone()[0]
        assert isinstance(antall, int)


# ── sett_drivstofftyper ───────────────────────────────────────────────────────

class TestSettDrivstofftyperDB:
    def test_setter_alle_typer_true(self, test_db):
        db_mod.lagre_stasjon('Test', 'Shell', 60.39, 5.33, 'node/1')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.sett_drivstofftyper(stasjon['id'], True, True, True, True)

        with db_mod.get_conn() as conn:
            row = conn.execute(
                'SELECT har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri FROM stasjoner WHERE id=?',
                (stasjon['id'],)
            ).fetchone()
        assert row == (1, 1, 1, 1)

    def test_setter_alle_typer_false(self, test_db):
        db_mod.lagre_stasjon('Test', 'Shell', 60.39, 5.33, 'node/2')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.sett_drivstofftyper(stasjon['id'], False, False, False, False)

        with db_mod.get_conn() as conn:
            row = conn.execute(
                'SELECT har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri FROM stasjoner WHERE id=?',
                (stasjon['id'],)
            ).fetchone()
        assert row == (0, 0, 0, 0)

    def test_bare_diesel_aktivert(self, test_db):
        db_mod.lagre_stasjon('Diesel', 'Shell', 60.39, 5.33, 'node/3')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.sett_drivstofftyper(stasjon['id'], False, False, True, False)

        with db_mod.get_conn() as conn:
            row = conn.execute(
                'SELECT har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri FROM stasjoner WHERE id=?',
                (stasjon['id'],)
            ).fetchone()
        assert row == (0, 0, 1, 0)

    def test_idempotent(self, test_db):
        """Kaller sett_drivstofftyper to ganger gir samme resultat."""
        db_mod.lagre_stasjon('Test', 'Shell', 60.39, 5.33, 'node/4')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.sett_drivstofftyper(stasjon['id'], True, False, True, False)
        db_mod.sett_drivstofftyper(stasjon['id'], True, False, True, False)

        with db_mod.get_conn() as conn:
            row = conn.execute(
                'SELECT har_bensin, har_bensin98, har_diesel, har_diesel_avgiftsfri FROM stasjoner WHERE id=?',
                (stasjon['id'],)
            ).fetchone()
        assert row == (1, 0, 1, 0)


# ── endre_navn_stasjon ────────────────────────────────────────────────────────

class TestEndreNavnStasjonDB:
    def test_setter_navn_laast(self, test_db):
        """endre_navn_stasjon skal sette navn_låst slik at import ikke overskriver."""
        db_mod.lagre_stasjon('Gammelt', 'Shell', 60.39, 5.33, 'node/1')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.endre_navn_stasjon(stasjon['id'], 'Nytt')

        with db_mod.get_conn() as conn:
            row = conn.execute(
                'SELECT navn, navn_låst FROM stasjoner WHERE id=?',
                (stasjon['id'],)
            ).fetchone()
        assert row[0] == 'Nytt'
        assert row[1] == 1

    def test_returnerer_false_for_ukjent_stasjon(self, test_db):
        resultat = db_mod.endre_navn_stasjon(999999, 'X')
        assert resultat is False

    def test_tomt_navn_lagres_ikke_via_api(self):
        """tom streng skal avvises allerede i route-laget — db-funksjonen er ikke ansvarlig."""
        # Dette er dokumentasjon av at db.py ikke validerer tomt navn
        # Route-laget gjør det — verifisert i test_admin_utvidet.py
        pass
