"""Tester for /api/bekreft-pris og /api/foreslaa-endring."""

import db as db_mod
from werkzeug.security import generate_password_hash


def lag_stasjon(navn='Test', lat=60.39, lon=5.33):
    db_mod.lagre_stasjon(navn, 'Shell', lat, lon, f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


def lag_bruker(epost='bruker@test.no'):
    db_mod.opprett_bruker(epost, generate_password_hash('passord123'))
    return db_mod.finn_bruker(epost)


# ── /api/bekreft-pris ──────────────────────────────────────────────────────────

class TestBekreftPris:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/bekreft-pris', json={'stasjon_id': 1, 'type': 'bensin'})
        assert resp.status_code == 401

    def test_mangler_stasjon_id_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/bekreft-pris', json={'type': 'bensin'})
        assert resp.status_code == 400

    def test_mangler_type_gir_400(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/bekreft-pris', json={'stasjon_id': stasjon['id']})
        assert resp.status_code == 400

    def test_bekreft_eksisterende_pris(self, innlogget_client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'], 'type': 'bensin',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_bekreft_returnerer_lagret_flagg(self, innlogget_client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'], 'type': 'diesel',
        })
        assert 'lagret' in resp.get_json()

    def test_bekreft_respekterer_rate_limit(self, innlogget_client):
        """Andre bekreftelse innenfor 5 min skal ikke lagres."""
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'], 'type': 'bensin',
        })
        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'], 'type': 'bensin',
        })
        assert resp.status_code == 200
        assert resp.get_json()['lagret'] is False


# ── /api/foreslaa-endring ──────────────────────────────────────────────────────

class TestForeslaaEndring:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/foreslaa-endring', json={'stasjon_id': 1, 'foreslatt_navn': 'Nytt navn'})
        assert resp.status_code == 401

    def test_mangler_stasjon_id_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/foreslaa-endring', json={'foreslatt_navn': 'Test'})
        assert resp.status_code == 400

    def test_ingen_felt_gir_400(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={'stasjon_id': stasjon['id']})
        assert resp.status_code == 400
        assert 'Minst ett felt' in resp.get_json()['error']

    def test_foreslaa_nytt_navn(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Nytt og bedre navn',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_foreslaa_ny_kjede(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_kjede': 'Circle K',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_foreslaa_nedlagt(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'er_nedlagt': True,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

        rapporter = db_mod.hent_rapporter()
        assert any(r['stasjon_id'] == stasjon['id'] for r in rapporter)

    def test_foreslaa_med_kommentar(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'kommentar': 'Pumpen er ute av drift.',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_kommentar_trunkeres_til_500_tegn(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'kommentar': 'X' * 600,
        })
        # Skal ikke feile — kommentar trunkeres til 500 tegn
        assert resp.status_code == 200

    def test_foreslaa_alle_felt_samtidig(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Nytt navn',
            'foreslatt_kjede': 'Esso',
            'kommentar': 'Har skiftet kjede',
            'er_nedlagt': False,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
