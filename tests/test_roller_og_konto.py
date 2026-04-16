"""Tester for roller (DB) og brukerselvbetjening (min-konto, slett-meg)."""

import db as db_mod
from werkzeug.security import generate_password_hash


# ── Roller — DB-funksjoner ─────────────────────────

class TestSettRollerBruker:
    def test_setter_rolle(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['moderator'])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert 'moderator' in oppdatert['roller'].split()

    def test_admin_rolle_setter_er_admin_flagg(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['admin'])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert oppdatert['er_admin'] == 1

    def test_ikke_admin_rolle_nullstiller_er_admin_flagg(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'), er_admin=True)
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['moderator'])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert oppdatert['er_admin'] == 0

    def test_flere_roller(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['moderator', 'kamera'])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        roller = oppdatert['roller'].split()
        assert 'moderator' in roller
        assert 'kamera' in roller

    def test_duplikater_dedupliseres(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['kamera', 'kamera'])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert oppdatert['roller'].split().count('kamera') == 1

    def test_tom_liste_fjerner_roller(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['moderator'])
        db_mod.sett_roller_bruker(bruker['id'], [])
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert (oppdatert['roller'] or '').strip() == ''


class TestHarRolle:
    def test_eksplisitt_rolle(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['moderator'])
        bruker = db_mod.finn_bruker_id(bruker['id'])
        assert db_mod.har_rolle(bruker, 'moderator') is True

    def test_mangler_rolle(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        assert db_mod.har_rolle(bruker, 'moderator') is False

    def test_none_bruker(self):
        assert db_mod.har_rolle(None, 'moderator') is False

    def test_kamera_via_prisantall(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        stasjon_id, _ = db_mod.opprett_stasjon('Test', None, 60.0, 10.0, bruker['id'])
        for _ in range(20):
            db_mod.lagre_pris(stasjon_id, 20.0, None, bruker_id=bruker['id'], min_intervall=0)
        bruker = db_mod.finn_bruker_id(bruker['id'])
        assert db_mod.har_rolle(bruker, 'kamera') is True

    def test_kamera_under_grense_uten_eksplisitt_rolle(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        stasjon_id, _ = db_mod.opprett_stasjon('Test', None, 60.0, 10.0, bruker['id'])
        for _ in range(19):
            db_mod.lagre_pris(stasjon_id, bruker['id'], 20.0, None, None, None)
        bruker = db_mod.finn_bruker_id(bruker['id'])
        assert db_mod.har_rolle(bruker, 'kamera') is False

    def test_kamera_eksplisitt_rolle_uten_priser(self):
        db_mod.opprett_bruker('a@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@t.no')
        db_mod.sett_roller_bruker(bruker['id'], ['kamera'])
        bruker = db_mod.finn_bruker_id(bruker['id'])
        assert db_mod.har_rolle(bruker, 'kamera') is True


# ── Min konto ──────────────────────────────────────

class TestMinKonto:
    def test_krever_innlogging(self, client):
        resp = client.get('/auth/min-konto', follow_redirects=False)
        assert resp.status_code == 302
        assert '/auth/logg-inn' in resp.headers['Location']

    def test_vis_side(self, innlogget_client):
        resp = innlogget_client.get('/auth/min-konto')
        assert resp.status_code == 200
        assert 'Min konto' in resp.data.decode()

    def test_lagre_kallenavn(self, innlogget_client):
        resp = innlogget_client.post('/auth/min-konto', data={'kallenavn': 'Raskeste pumpe'})
        assert resp.status_code == 200
        assert 'Kallenavn lagret' in resp.data.decode()

        bruker = db_mod.finn_bruker('test@test.no')
        assert bruker['kallenavn'] == 'Raskeste pumpe'

    def test_kallenavn_vises_i_skjema(self, innlogget_client):
        innlogget_client.post('/auth/min-konto', data={'kallenavn': 'Testkallenavn'})
        resp = innlogget_client.get('/auth/min-konto')
        assert 'Testkallenavn' in resp.data.decode()


# ── Slett meg ──────────────────────────────────────

class TestSlettMeg:
    def test_krever_innlogging(self, client):
        resp = client.get('/auth/slett-meg', follow_redirects=False)
        assert resp.status_code == 302
        assert '/auth/logg-inn' in resp.headers['Location']

    def test_vis_side(self, innlogget_client):
        resp = innlogget_client.get('/auth/slett-meg')
        assert resp.status_code == 200
        assert 'Slett konto' in resp.data.decode()

    def test_feil_passord_sletter_ikke(self, innlogget_client):
        resp = innlogget_client.post('/auth/slett-meg', data={'passord': 'feil'})
        assert 'Feil passord' in resp.data.decode()
        assert db_mod.finn_bruker('test@test.no') is not None

    def test_riktig_passord_sletter_konto(self, innlogget_client):
        resp = innlogget_client.post('/auth/slett-meg', data={'passord': 'passord123'})
        assert resp.status_code == 200
        assert 'slettet' in resp.data.decode()
        assert db_mod.finn_bruker('test@test.no') is None

    def test_session_toemmes_etter_sletting(self, innlogget_client):
        innlogget_client.post('/auth/slett-meg', data={'passord': 'passord123'})
        meg = innlogget_client.get('/api/meg')
        assert meg.get_json()['innlogget'] is False
