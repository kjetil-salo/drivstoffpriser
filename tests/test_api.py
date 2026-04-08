"""Tester for API-endepunkter."""

import db as db_mod


# ── /api/stasjoner ─────────────────────────────────

class TestStasjonerAPI:
    def test_hent_stasjoner(self, client):
        db_mod.lagre_stasjon('Test', 'Shell', 60.39, 5.33, 'node/1')
        resp = client.get('/api/stasjoner?lat=60.39&lon=5.33')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['stasjoner']) == 1
        assert data['stasjoner'][0]['navn'] == 'Test'

    def test_mangler_koordinater(self, client):
        resp = client.get('/api/stasjoner')
        assert resp.status_code == 400

    def test_mangler_lon(self, client):
        resp = client.get('/api/stasjoner?lat=60.39')
        assert resp.status_code == 400

    def test_utenfor_norge(self, client):
        resp = client.get('/api/stasjoner?lat=48.0&lon=2.0')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['utenfor'] is True

    def test_grense_norge_nord(self, client):
        resp = client.get('/api/stasjoner?lat=71.0&lon=25.0')
        assert resp.status_code == 200

    def test_grense_norge_sor(self, client):
        resp = client.get('/api/stasjoner?lat=57.5&lon=7.0')
        assert resp.status_code == 200


# ── /api/pris ──────────────────────────────────────

class TestPrisAPI:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/pris', json={'stasjon_id': 1, 'bensin': 21.0})
        assert resp.status_code == 401

    def test_lagre_pris(self, innlogget_client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        sid = stasjoner[0]['id']
        resp = innlogget_client.post('/api/pris', json={
            'stasjon_id': sid, 'bensin': 21.35, 'diesel': 20.50, 'bensin98': 22.10,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] == 21.35

    def test_mangler_stasjon_id(self, innlogget_client):
        resp = innlogget_client.post('/api/pris', json={'bensin': 21.0})
        assert resp.status_code == 400

    def test_komma_som_desimaltegn(self, innlogget_client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        resp = innlogget_client.post('/api/pris', json={
            'stasjon_id': stasjoner[0]['id'], 'bensin': '21,35',
        })
        assert resp.status_code == 200
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] == 21.35

    def test_tom_pris_blir_none(self, innlogget_client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        resp = innlogget_client.post('/api/pris', json={
            'stasjon_id': stasjoner[0]['id'], 'bensin': '', 'diesel': None,
        })
        assert resp.status_code == 200

    def test_null_pris_blir_none(self, innlogget_client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        resp = innlogget_client.post('/api/pris', json={
            'stasjon_id': stasjoner[0]['id'], 'bensin': 0,
        })
        assert resp.status_code == 200
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        # 0 skal tolkes som "ikke oppgitt"
        assert result[0]['bensin'] is None

    def test_lagre_diesel_avgiftsfri(self, innlogget_client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        resp = innlogget_client.post('/api/pris', json={
            'stasjon_id': stasjoner[0]['id'], 'diesel_avgiftsfri': 14.50,
        })
        assert resp.status_code == 200
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['diesel_avgiftsfri'] == 14.50

    def test_statistikk_inkluderer_diesel_avgiftsfri(self, client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        db_mod.lagre_pris(stasjoner[0]['id'], None, None, diesel_avgiftsfri=14.50)
        resp = client.get('/api/statistikk')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'diesel_avgiftsfri' in data['billigst']
        assert 'diesel_avgiftsfri' in data['dyrest']
        assert data['billigst']['diesel_avgiftsfri']['pris'] == 14.50


# ── /api/meg ───────────────────────────────────────

class TestMegAPI:
    def test_ikke_innlogget(self, client):
        resp = client.get('/api/meg')
        data = resp.get_json()
        assert data['innlogget'] is False

    def test_innlogget(self, innlogget_client):
        resp = innlogget_client.get('/api/meg')
        data = resp.get_json()
        assert data['innlogget'] is True
        assert data['brukernavn'] == 'test@test.no'

    def test_admin_flagg(self, admin_client):
        resp = admin_client.get('/api/meg')
        data = resp.get_json()
        assert data['er_admin'] is True


# ── /api/totalt-med-pris ───────────────────────────

class TestTotaltMedPris:
    def test_ingen_priser(self, client):
        resp = client.get('/api/totalt-med-pris')
        assert resp.get_json()['totalt'] == 0

    def test_med_priser(self, client):
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        db_mod.lagre_pris(stasjoner[0]['id'], 21.0, 20.0)
        resp = client.get('/api/totalt-med-pris')
        assert resp.get_json()['totalt'] == 1


# ── /api/logview ───────────────────────────────────

class TestLogview:
    def test_logview_setter_cookie(self, client):
        resp = client.post('/api/logview')
        assert resp.status_code == 200
        assert 'device_id' in resp.headers.get('Set-Cookie', '')

    def test_logview_med_eksisterende_cookie(self, client):
        client.set_cookie('device_id', 'existing-id', domain='localhost')
        resp = client.post('/api/logview')
        assert resp.status_code == 200
        # Skal ikke sette ny cookie
        assert 'device_id' not in (resp.headers.get('Set-Cookie') or '')


# ── /api/stedssok ──────────────────────────────────

class TestStedssok:
    def test_for_kort_sok(self, client):
        resp = client.get('/api/stedssok?q=a')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_tomt_sok(self, client):
        resp = client.get('/api/stedssok?q=')
        assert resp.get_json() == []


# ── /bidrag ────────────────────────────────────────

class TestBidragSide:
    def test_siden_finnes(self, client):
        resp = client.get('/bidrag')
        assert resp.status_code == 200
        assert b'bidrag' in resp.data.lower()

    def test_bidrag_btn_er_skjult_i_html(self, client):
        """bidrag-btn må ha hidden-attributt i HTML-kilden — JS viser den kun ved opt-in."""
        resp = client.get('/')
        html = resp.data.decode()
        import re
        match = re.search(r'id="bidrag-btn"[^>]*>', html)
        assert match, 'bidrag-btn ikke funnet i index.html'
        assert 'hidden' in match.group(), 'bidrag-btn mangler hidden-attributt i HTML'

    def test_bidrag_btn_hidden_css_override(self, client):
        """CSS må overstyre display:flex med display:none når hidden er satt."""
        resp = client.get('/css/app.css')
        assert b'#bidrag-btn[hidden]' in resp.data


# ── /admin/oversikt ────────────────────────────────

class TestOversikt:
    def test_krever_innlogging(self, client):
        resp = client.get('/admin/oversikt')
        assert resp.status_code == 302

    def test_krever_admin(self, innlogget_client):
        resp = innlogget_client.get('/admin/oversikt')
        assert resp.status_code == 403

    def test_admin_far_tilgang(self, admin_client):
        resp = admin_client.get('/admin/oversikt')
        assert resp.status_code == 200
        assert 'statistikk' in resp.data.decode().lower()
