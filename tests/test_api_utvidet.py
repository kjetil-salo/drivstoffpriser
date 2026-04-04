"""Tester for API-endepunkter som mangler dekning."""

import os
import sqlite3
import tempfile

import db as db_mod
from werkzeug.security import generate_password_hash


# ── Hjelpefunksjoner ───────────────────────────────

def lag_stasjon(navn='Test', lat=60.39, lon=5.33, osm_id=None):
    db_mod.lagre_stasjon(navn, 'Shell', lat, lon, osm_id or f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


def lag_bruker(epost='bruker@test.no'):
    db_mod.opprett_bruker(epost, generate_password_hash('passord123'))
    return db_mod.finn_bruker(epost)


def lag_gyldig_db_bytes(test_db_path):
    """Eksporter gjeldende test-DB til bytes via sqlite3.backup()."""
    fd, tmp = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    src = sqlite3.connect(test_db_path)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    src.close()
    dst.close()
    with open(tmp, 'rb') as f:
        data = f.read()
    os.unlink(tmp)
    return data


# ── /api/sync-db ───────────────────────────────────

class TestSyncDb:
    def test_mangler_nøkkel_gir_403(self, client):
        resp = client.put('/api/sync-db', data=b'data')
        assert resp.status_code == 403

    def test_feil_nøkkel_gir_403(self, client):
        os.environ['SYNC_KEY'] = 'riktig-nøkkel'
        resp = client.put('/api/sync-db', data=b'data',
                          headers={'X-Sync-Key': 'feil-nøkkel'})
        assert resp.status_code == 403

    def test_tom_body_gir_400(self, client):
        os.environ['SYNC_KEY'] = 'test-sync-key'
        resp = client.put('/api/sync-db', data=b'',
                          headers={'X-Sync-Key': 'test-sync-key'})
        assert resp.status_code == 400

    def test_korrupt_db_gir_400(self, client):
        os.environ['SYNC_KEY'] = 'test-sync-key'
        resp = client.put('/api/sync-db', data=b'dette er ikke en sqlite-fil',
                          headers={'X-Sync-Key': 'test-sync-key'})
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'Korrupt' in data['error'] or 'error' in data

    def test_gyldig_db_synkroniseres(self, client, test_db):
        os.environ['SYNC_KEY'] = 'test-sync-key'
        # Legg til en stasjon i test-DB
        db_mod.lagre_stasjon('SyncStasjon', 'Shell', 60.39, 5.33, 'node/sync1')

        db_bytes = lag_gyldig_db_bytes(test_db)
        resp = client.put('/api/sync-db', data=db_bytes,
                          headers={'X-Sync-Key': 'test-sync-key',
                                   'Content-Type': 'application/octet-stream'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['bytes'] == len(db_bytes)

    def test_tom_sync_key_env_gir_403(self, client):
        os.environ['SYNC_KEY'] = ''
        resp = client.put('/api/sync-db', data=b'noe',
                          headers={'X-Sync-Key': ''})
        assert resp.status_code == 403


# ── /api/stasjon (POST) ────────────────────────────

class TestNyStasjonAPI:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/stasjon', json={
            'navn': 'Shell Sentrum', 'lat': 60.39, 'lon': 5.33
        })
        assert resp.status_code == 401

    def test_opprett_stasjon(self, innlogget_client):
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'Shell Sentrum', 'lat': 60.39, 'lon': 5.33
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['stasjon']['navn'] == 'Shell Sentrum'
        assert 'id' in data['stasjon']

    def test_mangler_navn_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/stasjon', json={
            'lat': 60.39, 'lon': 5.33
        })
        assert resp.status_code == 400

    def test_for_langt_navn_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'X' * 101, 'lat': 60.39, 'lon': 5.33
        })
        assert resp.status_code == 400

    def test_ugyldig_koordinat_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'Test', 'lat': 'ikke-tall', 'lon': 5.33
        })
        assert resp.status_code == 400

    def test_utenfor_norge_gir_400(self, innlogget_client):
        # Paris er utenfor Norges bbox (lat < 57)
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'Paris', 'lat': 48.85, 'lon': 2.35
        })
        assert resp.status_code == 400

    def test_duplikat_gir_409(self, innlogget_client):
        # Legg til en stasjon
        innlogget_client.post('/api/stasjon', json={
            'navn': 'Shell Sentrum', 'lat': 60.39, 'lon': 5.33
        })
        # Prøv å legge til noe like ved
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'Shell Kopi', 'lat': 60.39001, 'lon': 5.33001
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert 'duplikat' in data

    def test_kjede_lagres(self, innlogget_client):
        resp = innlogget_client.post('/api/stasjon', json={
            'navn': 'Circle K Sentrum', 'kjede': 'Circle K', 'lat': 60.39, 'lon': 5.33
        })
        assert resp.status_code == 200
        assert resp.get_json()['stasjon']['kjede'] == 'Circle K'


# ── /api/rapporter-nedlagt ─────────────────────────

class TestRapporterNedlagt:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/rapporter-nedlagt', json={'stasjon_id': 1})
        assert resp.status_code == 401

    def test_mangler_stasjon_id_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/rapporter-nedlagt', json={})
        assert resp.status_code == 400

    def test_rapporter_stasjon(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/rapporter-nedlagt',
                                     json={'stasjon_id': stasjon['id']})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

        rapporter = db_mod.hent_rapporter()
        assert len(rapporter) == 1
        assert rapporter[0]['stasjon_id'] == stasjon['id']


# ── /api/nyhet ─────────────────────────────────────

class TestNyhet:
    def test_ingen_nyhet(self, client):
        resp = client.get('/api/nyhet')
        assert resp.status_code == 200
        assert resp.get_json()['tekst'] is None

    def test_aktiv_nyhet(self, client):
        db_mod.sett_innstilling('nyhet_tekst', 'Velkommen!')
        db_mod.sett_innstilling('nyhet_utloper', '2099-12-31T23:59:59')
        resp = client.get('/api/nyhet')
        data = resp.get_json()
        assert data['tekst'] == 'Velkommen!'
        assert data['id'] is not None

    def test_utløpt_nyhet_gir_none(self, client):
        db_mod.sett_innstilling('nyhet_tekst', 'Gammel nyhet')
        db_mod.sett_innstilling('nyhet_utloper', '2000-01-01T00:00:00')
        resp = client.get('/api/nyhet')
        assert resp.get_json()['tekst'] is None

    def test_ugyldig_dato_gir_none(self, client):
        db_mod.sett_innstilling('nyhet_tekst', 'Test')
        db_mod.sett_innstilling('nyhet_utloper', 'ikke-en-dato')
        resp = client.get('/api/nyhet')
        assert resp.get_json()['tekst'] is None

    def test_nyhet_id_er_deterministisk(self, client):
        db_mod.sett_innstilling('nyhet_tekst', 'Samme tekst')
        db_mod.sett_innstilling('nyhet_utloper', '2099-12-31T23:59:59')
        r1 = client.get('/api/nyhet').get_json()
        r2 = client.get('/api/nyhet').get_json()
        assert r1['id'] == r2['id']


# ── /api/toppliste ─────────────────────────────────

class TestToppliste:
    def test_tom_liste(self, client):
        resp = client.get('/api/toppliste')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['liste'] == []
        assert data['min_plass'] is None

    def test_liste_med_brukere(self, client):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'])

        resp = client.get('/api/toppliste')
        data = resp.get_json()
        assert len(data['liste']) == 1
        assert data['liste'][0]['antall'] == 1
        assert data['liste'][0]['er_meg'] is False

    def test_er_meg_flagg_for_innlogget(self, innlogget_client):
        bruker = db_mod.finn_bruker('test@test.no')
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'])

        resp = innlogget_client.get('/api/toppliste')
        data = resp.get_json()
        assert data['liste'][0]['er_meg'] is True

    def test_min_plass_utenfor_topp20(self, innlogget_client):
        meg = db_mod.finn_bruker('test@test.no')
        stasjon = lag_stasjon()
        # Lag 20 brukere med mer enn meg
        for i in range(20):
            b = lag_bruker(f'stor{i}@test.no')
            for _ in range(i + 2):
                db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=b['id'])
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=meg['id'])

        resp = innlogget_client.get('/api/toppliste')
        data = resp.get_json()
        assert data['min_plass'] is not None
        assert data['min_plass']['plass'] > 20
