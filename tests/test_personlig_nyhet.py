"""Tester for personlig nyhet/splash (/api/nyhet med personlig_splash)."""

import db as db_mod
from werkzeug.security import generate_password_hash


def lag_bruker(epost='bruker@test.no'):
    db_mod.opprett_bruker(epost, generate_password_hash('passord123'))
    return db_mod.finn_bruker(epost)


def logg_inn(client, epost='bruker@test.no', passord='passord123'):
    client.post('/auth/logg-inn', data={'brukernavn': epost, 'passord': passord})


# ── personlig_splash deaktivert (standard) ─────────────────────────────────────

class TestPersonligNyhetDeaktivert:
    def test_ingen_personlig_nyhet_nar_deaktivert(self, client):
        """Uten personlig_splash='1' og uten admin-nyhet: tekst er None."""
        resp = client.get('/api/nyhet')
        assert resp.status_code == 200
        assert resp.get_json()['tekst'] is None

    def test_admin_nyhet_overskriver_uansett(self, client):
        """Admin-nyhet skal alltid vises uavhengig av personlig_splash."""
        db_mod.sett_innstilling('nyhet_tekst', 'Viktig melding!')
        db_mod.sett_innstilling('nyhet_utloper', '2099-12-31T23:59:59')

        resp = client.get('/api/nyhet')
        assert resp.get_json()['tekst'] == 'Viktig melding!'


# ── personlig_splash aktivert ──────────────────────────────────────────────────

class TestPersonligNyhetAktivert:
    def setup_method(self):
        db_mod.sett_innstilling('personlig_splash', '1')

    def test_uinnlogget_far_velkomst_melding(self, client):
        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['tekst'] is not None
        assert data['id'] is not None
        assert data['id'].startswith('pers_')
        assert 'anon' in data['id']

    def test_uinnlogget_melding_inneholder_info(self, client):
        resp = client.get('/api/nyhet')
        tekst = resp.get_json()['tekst']
        assert len(tekst) > 10

    def test_uinnlogget_har_utloper(self, client):
        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['utloper'] is not None

    def test_innlogget_ingen_priser_siste_uke(self, client, app):
        bruker = lag_bruker()
        logg_inn(client)

        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['tekst'] is not None
        assert data['id'] is not None
        assert 'anon' not in data['id']

    def test_innlogget_med_fa_priser(self, client):
        """Bruker med 1-19 priser siste uke skal få takke-melding."""
        bruker = lag_bruker()
        db_mod.lagre_stasjon('TestSt', 'Shell', 60.39, 5.33, 'node/test')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]

        for i in range(5):
            db_mod.lagre_pris(stasjon['id'], 21.0 + i * 0.1, None,
                               bruker_id=bruker['id'], min_intervall=0)

        logg_inn(client)
        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['tekst'] is not None
        assert '5' in data['tekst']  # antall priser skal stå i teksten

    def test_innlogget_med_mange_priser(self, client):
        """Bruker med >= 20 priser siste uke skal få wow-melding."""
        bruker = lag_bruker()
        db_mod.lagre_stasjon('TestSt', 'Shell', 60.39, 5.33, 'node/test')
        stasjon = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]

        for i in range(20):
            db_mod.lagre_pris(stasjon['id'], 21.0 + i * 0.01, None,
                               bruker_id=bruker['id'], min_intervall=0)

        logg_inn(client)
        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['tekst'] is not None
        assert '20' in data['tekst']

    def test_personlig_splash_id_er_unikt_per_uke(self, client):
        """ID-en skal inneholde år og ukenummer, ikke kun en tilfeldige streng."""
        logg_inn_bruker = lag_bruker()
        logg_inn(client)

        resp = client.get('/api/nyhet')
        splash_id = resp.get_json()['id']
        from datetime import datetime
        uke = datetime.now().isocalendar()[1]
        aar = datetime.now().year
        assert str(aar) in splash_id
        assert f'w{uke}' in splash_id

    def test_admin_nyhet_slaar_gjennom_personlig_splash(self, client):
        """Admin-nyhet tar alltid prioritet, selv med personlig_splash aktiv."""
        db_mod.sett_innstilling('nyhet_tekst', 'Viktig! Server-vedlikehold')
        db_mod.sett_innstilling('nyhet_utloper', '2099-12-31T23:59:59')

        resp = client.get('/api/nyhet')
        assert resp.get_json()['tekst'] == 'Viktig! Server-vedlikehold'
