"""Tester for rate limiting — db-funksjonene og auth-integrasjon."""

import db as db_mod
from werkzeug.security import generate_password_hash


# ── DB-funksjoner ──────────────────────────────────

class TestSjekkRateLimit:
    def test_under_grensen(self):
        db_mod.logg_rate_limit('test', '1.2.3.4')
        db_mod.logg_rate_limit('test', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is False

    def test_paa_grensen(self):
        for _ in range(3):
            db_mod.logg_rate_limit('test', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is True

    def test_over_grensen(self):
        for _ in range(5):
            db_mod.logg_rate_limit('test', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is True

    def test_ulik_nokkel_pavirker_ikke(self):
        for _ in range(5):
            db_mod.logg_rate_limit('test', '9.9.9.9')
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is False

    def test_ulik_type_pavirker_ikke(self):
        for _ in range(5):
            db_mod.logg_rate_limit('annen_type', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is False

    def test_tom_database(self):
        assert db_mod.sjekk_rate_limit('test', '1.2.3.4', maks=3, vindu_sekunder=60) is False


class TestSlettRateLimit:
    def test_sletter_hendelser(self):
        for _ in range(5):
            db_mod.logg_rate_limit('innlogging', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('innlogging', '1.2.3.4', maks=3, vindu_sekunder=60) is True

        db_mod.slett_rate_limit('innlogging', '1.2.3.4')
        assert db_mod.sjekk_rate_limit('innlogging', '1.2.3.4', maks=3, vindu_sekunder=60) is False

    def test_sletter_kun_riktig_nokkel(self):
        for _ in range(5):
            db_mod.logg_rate_limit('innlogging', '1.2.3.4')
            db_mod.logg_rate_limit('innlogging', '5.6.7.8')

        db_mod.slett_rate_limit('innlogging', '1.2.3.4')

        assert db_mod.sjekk_rate_limit('innlogging', '1.2.3.4', maks=3, vindu_sekunder=60) is False
        assert db_mod.sjekk_rate_limit('innlogging', '5.6.7.8', maks=3, vindu_sekunder=60) is True

    def test_sletter_kun_riktig_type(self):
        for _ in range(5):
            db_mod.logg_rate_limit('innlogging', '1.2.3.4')
            db_mod.logg_rate_limit('registrering', '1.2.3.4')

        db_mod.slett_rate_limit('innlogging', '1.2.3.4')

        assert db_mod.sjekk_rate_limit('innlogging', '1.2.3.4', maks=3, vindu_sekunder=60) is False
        assert db_mod.sjekk_rate_limit('registrering', '1.2.3.4', maks=3, vindu_sekunder=60) is True

    def test_slett_ikke_eksisterende_er_ok(self):
        db_mod.slett_rate_limit('innlogging', '1.2.3.4')  # skal ikke kaste


# ── Auth-integrasjon ───────────────────────────────

class TestInnloggingRateLimit:
    def test_blokkert_etter_for_mange_feil(self, client):
        db_mod.opprett_bruker('bruker@t.no', generate_password_hash('riktig'))

        for _ in range(10):
            client.post('/auth/logg-inn', data={
                'brukernavn': 'bruker@t.no', 'passord': 'feil',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'bruker@t.no', 'passord': 'feil',
        }, environ_base={'REMOTE_ADDR': '1.2.3.4'})
        assert 'For mange feil forsøk' in resp.data.decode()

    def test_vellykket_innlogging_nullstiller_rate_limit(self, client):
        db_mod.opprett_bruker('bruker@t.no', generate_password_hash('riktig'))

        for _ in range(9):
            client.post('/auth/logg-inn', data={
                'brukernavn': 'bruker@t.no', 'passord': 'feil',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        # Vellykket innlogging skal slette rate limit-loggene
        client.post('/auth/logg-inn', data={
            'brukernavn': 'bruker@t.no', 'passord': 'riktig',
        }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        assert db_mod.sjekk_rate_limit('innlogging', '1.2.3.4', maks=10, vindu_sekunder=900) is False

    def test_ulik_ip_ikke_blokkert(self, client):
        db_mod.opprett_bruker('bruker@t.no', generate_password_hash('riktig'))

        for _ in range(10):
            client.post('/auth/logg-inn', data={
                'brukernavn': 'bruker@t.no', 'passord': 'feil',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        # Annen IP skal ikke være blokkert
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'bruker@t.no', 'passord': 'riktig',
        }, environ_base={'REMOTE_ADDR': '5.6.7.8'}, follow_redirects=False)
        assert resp.status_code == 302


class TestRegistreringRateLimit:
    def test_blokkert_etter_for_mange_registreringer(self, client):
        for i in range(5):
            client.post('/registrer', data={
                'epost': f'ny{i}@t.no', 'passord': 'passord123',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        resp = client.post('/registrer', data={
            'epost': 'ekstra@t.no', 'passord': 'passord123',
        }, environ_base={'REMOTE_ADDR': '1.2.3.4'})
        assert 'For mange registreringer' in resp.data.decode()

    def test_ulik_ip_ikke_blokkert(self, client):
        for i in range(5):
            client.post('/registrer', data={
                'epost': f'ny{i}@t.no', 'passord': 'passord123',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        resp = client.post('/registrer', data={
            'epost': 'annen@t.no', 'passord': 'passord123',
        }, environ_base={'REMOTE_ADDR': '5.6.7.8'}, follow_redirects=False)
        assert resp.status_code == 302


class TestTilbakestillingRateLimit:
    def test_blokkert_etter_for_mange_forsok(self, client):
        db_mod.opprett_bruker('bruker@t.no', generate_password_hash('riktig'))

        for _ in range(3):
            client.post('/auth/tilbakestill', data={
                'epost': 'bruker@t.no',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        # 4. forsøk skal gi samme nøytrale svar (avslører ikke at IP er blokkert)
        resp = client.post('/auth/tilbakestill', data={
            'epost': 'bruker@t.no',
        }, environ_base={'REMOTE_ADDR': '1.2.3.4'})
        assert 'Sjekk innboksen' in resp.data.decode()

    def test_ulik_ip_ikke_blokkert(self, client):
        db_mod.opprett_bruker('bruker@t.no', generate_password_hash('riktig'))

        for _ in range(3):
            client.post('/auth/tilbakestill', data={
                'epost': 'bruker@t.no',
            }, environ_base={'REMOTE_ADDR': '1.2.3.4'})

        resp = client.post('/auth/tilbakestill', data={
            'epost': 'bruker@t.no',
        }, environ_base={'REMOTE_ADDR': '5.6.7.8'})
        assert resp.status_code == 200
