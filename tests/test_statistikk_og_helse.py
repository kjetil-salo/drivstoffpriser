"""Tester for statistikk- og helse-endepunkter."""

import db as db_mod


def lag_stasjon(navn='Test', lat=60.39, lon=5.33):
    db_mod.lagre_stasjon(navn, 'Shell', lat, lon, f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


# ── /health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returnerer_ok(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'


# ── /api/instance ──────────────────────────────────────────────────────────────

class TestInstance:
    def test_returnerer_backup_flagg(self, client):
        resp = client.get('/api/instance')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'backup' in data
        assert isinstance(data['backup'], bool)


# ── /api/statistikk ────────────────────────────────────────────────────────────

class TestStatistikk:
    def test_tom_database(self, client):
        resp = client.get('/api/statistikk')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['billigst']['bensin'] is None
        assert data['billigst']['diesel'] is None
        assert data['dyrest']['bensin'] is None
        assert data['antall_oppdateringer_24t'] == 0

    def test_med_priser(self, client):
        s1 = lag_stasjon('Billig', 60.39, 5.33)
        s2 = lag_stasjon('Dyr', 60.40, 5.34)
        db_mod.lagre_pris(s1['id'], 20.50, 19.80)
        db_mod.lagre_pris(s2['id'], 22.99, 21.50)

        resp = client.get('/api/statistikk')
        data = resp.get_json()

        assert data['billigst']['bensin']['pris'] == 20.50
        assert data['billigst']['bensin']['stasjon'] == 'Billig'
        assert data['dyrest']['bensin']['pris'] == 22.99
        assert data['dyrest']['bensin']['stasjon'] == 'Dyr'
        assert data['billigst']['diesel']['pris'] == 19.80
        assert data['antall_oppdateringer_24t'] == 2

    def test_med_radius_parameter(self, client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        resp = client.get('/api/statistikk?lat=60.39&lon=5.33&radius=50')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['billigst']['bensin'] is not None

    def test_diesel_avgiftsfri_inkludert(self, client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], None, None, diesel_avgiftsfri=15.50)

        resp = client.get('/api/statistikk')
        data = resp.get_json()
        assert data['billigst']['diesel_avgiftsfri']['pris'] == 15.50
        assert data['dyrest']['diesel_avgiftsfri']['pris'] == 15.50

    def test_en_stasjon_er_billigst_og_dyrest(self, client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        resp = client.get('/api/statistikk')
        data = resp.get_json()
        # Med én stasjon skal billigst == dyrest
        assert data['billigst']['bensin']['pris'] == data['dyrest']['bensin']['pris']


# ── /api/kjede-snitt ───────────────────────────────────────────────────────────

class TestKjedeSnitt:
    def test_tom_database(self, client):
        resp = client.get('/api/kjede-snitt')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_med_priser(self, client):
        db_mod.lagre_stasjon('Circle K Test', 'Circle K', 60.39, 5.33, 'node/ck1')
        s = db_mod.get_stasjoner_med_priser(60.39, 5.33)[0]
        db_mod.lagre_pris(s['id'], 21.0, 20.0)

        resp = client.get('/api/kjede-snitt')
        data = resp.get_json()
        assert isinstance(data, list)


# ── /api/prisregistreringer-per-time ──────────────────────────────────────────

class TestPrisregistreringerPerTime:
    def test_tom_database(self, client):
        resp = client.get('/api/prisregistreringer-per-time')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_format_er_korrekt(self, client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0)

        resp = client.get('/api/prisregistreringer-per-time')
        data = resp.get_json()
        assert isinstance(data, list)
        if data:
            assert 'time' in data[0]
            assert 'antall' in data[0]


# ── /api/prisregistreringer-uke ────────────────────────────────────────────────

class TestPrisregistreringerUke:
    def test_returnerer_liste(self, client):
        resp = client.get('/api/prisregistreringer-uke')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


# ── /api/enheter-per-dag ───────────────────────────────────────────────────────

class TestEnheterPerDag:
    def test_returnerer_liste(self, client):
        resp = client.get('/api/enheter-per-dag')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)
