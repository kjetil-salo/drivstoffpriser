"""Tester for admin-ruter."""

import db as db_mod
from werkzeug.security import generate_password_hash


class TestAdminTilgang:
    def test_krever_innlogging(self, client):
        resp = client.get('/admin', follow_redirects=False)
        assert resp.status_code == 302
        assert 'logg-inn' in resp.headers['Location']

    def test_vanlig_bruker_far_403(self, innlogget_client):
        resp = innlogget_client.get('/admin')
        assert resp.status_code == 403

    def test_admin_far_tilgang(self, admin_client):
        resp = admin_client.get('/admin')
        assert resp.status_code == 200
        assert 'Admin' in resp.data.decode()


class TestAdminDashboard:
    def test_viser_tiles(self, admin_client):
        resp = admin_client.get('/admin')
        html = resp.data.decode()
        assert 'Brukere' in html
        assert 'Steder' in html
        assert 'Statistikk' in html
        assert 'Prislogg' in html
        assert 'Kart' in html


class TestAdminBrukere:
    def test_viser_brukere(self, admin_client):
        resp = admin_client.get('/admin/brukere')
        assert 'admin@test.no' in resp.data.decode()

    def test_slett_bruker(self, admin_client):
        db_mod.opprett_bruker('slett@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('slett@t.no')
        resp = admin_client.post('/admin/slett-bruker', data={
            'bruker_id': bruker['id'],
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.finn_bruker('slett@t.no') is None

    def test_generer_invitasjon(self, admin_client):
        resp = admin_client.post('/admin/invitasjon')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'url' in data
        assert 'invitasjon?token=' in data['url']


class TestPrislogg:
    def test_krever_admin(self, innlogget_client):
        resp = innlogget_client.get('/admin/prislogg')
        assert resp.status_code == 403

    def test_viser_prislogg(self, admin_client):
        resp = admin_client.get('/admin/prislogg')
        assert resp.status_code == 200
        assert 'Prislogg' in resp.data.decode()

    def test_viser_prisoppdateringer(self, admin_client):
        db_mod.lagre_stasjon('S', 'Shell', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        bruker = db_mod.finn_bruker('admin@test.no')
        db_mod.lagre_pris(stasjoner[0]['id'], 21.0, 20.0, bruker_id=bruker['id'])
        resp = admin_client.get('/admin/prislogg')
        html = resp.data.decode()
        assert 'Shell' in html
        assert 'admin@test.no' in html
