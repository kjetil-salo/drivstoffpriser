"""Tester for auth-ruter."""

import db as db_mod
from werkzeug.security import generate_password_hash


# ── Innlogging ─────────────────────────────────────

class TestInnlogging:
    def test_vis_logg_inn_side(self, client):
        db_mod.opprett_bruker('x@t.no', generate_password_hash('x'))
        resp = client.get('/auth/logg-inn')
        assert resp.status_code == 200
        assert 'Logg inn' in resp.data.decode()

    def test_vellykket_innlogging(self, client):
        db_mod.opprett_bruker('test@t.no', generate_password_hash('hemlig'))
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'test@t.no', 'passord': 'hemlig',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['Location'] == '/'

    def test_feil_passord(self, client):
        db_mod.opprett_bruker('test@t.no', generate_password_hash('riktig'))
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'test@t.no', 'passord': 'feil',
        })
        assert 'Feil brukernavn eller passord' in resp.data.decode()

    def test_ukjent_bruker(self, client):
        db_mod.opprett_bruker('x@t.no', generate_password_hash('x'))
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'finnes@ikke.no', 'passord': 'test',
        })
        assert 'Feil brukernavn eller passord' in resp.data.decode()

    def test_allerede_innlogget_redirect(self, innlogget_client):
        resp = innlogget_client.get('/auth/logg-inn', follow_redirects=False)
        assert resp.status_code == 302

    def test_logg_ut(self, innlogget_client):
        resp = innlogget_client.get('/auth/logg-ut', follow_redirects=False)
        assert resp.status_code == 302
        # Sjekk at session er tømt
        meg = innlogget_client.get('/api/meg')
        assert meg.get_json()['innlogget'] is False


# ── Første admin ───────────────────────────────────

class TestForsteAdmin:
    def test_vis_opprett_admin_nar_ingen_brukere(self, client):
        resp = client.get('/auth/logg-inn')
        assert 'Opprett admin' in resp.data.decode()

    def test_opprett_admin(self, client):
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': 'admin@t.no', 'passord': 'admin123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        bruker = db_mod.finn_bruker('admin@t.no')
        assert bruker is not None
        assert bruker['er_admin'] == 1

    def test_opprett_admin_uten_data(self, client):
        resp = client.post('/auth/logg-inn', data={
            'brukernavn': '', 'passord': '',
        })
        assert 'Fyll inn' in resp.data.decode()


# ── Registrering ───────────────────────────────────

class TestRegistrering:
    def test_vis_registrering(self, client):
        resp = client.get('/registrer')
        assert resp.status_code == 200
        assert 'Registrer deg' in resp.data.decode()

    def test_vellykket_registrering(self, client):
        resp = client.post('/registrer', data={
            'epost': 'ny@bruker.no', 'passord': 'passord123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.finn_bruker('ny@bruker.no') is not None

    def test_ugyldig_epost(self, client):
        resp = client.post('/registrer', data={
            'epost': 'ugyldig', 'passord': 'passord123',
        })
        assert 'Ugyldig e-postadresse' in resp.data.decode()

    def test_for_kort_passord(self, client):
        resp = client.post('/registrer', data={
            'epost': 'ny@bruker.no', 'passord': '123',
        })
        assert 'minst 6 tegn' in resp.data.decode()

    def test_duplikat_epost(self, client):
        db_mod.opprett_bruker('dup@t.no', generate_password_hash('x'))
        resp = client.post('/registrer', data={
            'epost': 'dup@t.no', 'passord': 'passord123',
        })
        assert 'allerede i bruk' in resp.data.decode()

    def test_stoppet_registrering(self, client):
        db_mod.sett_innstilling('registrering_stoppet', '1')
        resp = client.get('/registrer')
        assert 'midlertidig stengt' in resp.data.decode()
        db_mod.sett_innstilling('registrering_stoppet', '0')


# ── Invitasjoner ───────────────────────────────────

class TestInvitasjoner:
    def test_gyldig_invitasjon_viser_skjema(self, client):
        db_mod.opprett_invitasjon('gyldig-token', '2099-01-01 00:00:00')
        resp = client.get('/invitasjon?token=gyldig-token')
        assert resp.status_code == 200
        assert 'Opprett konto' in resp.data.decode()

    def test_ugyldig_invitasjon(self, client):
        resp = client.get('/invitasjon?token=ugyldig')
        assert 'ugyldig eller utl' in resp.data.decode().lower()

    def test_bruk_invitasjon(self, client):
        db_mod.opprett_invitasjon('bruk-meg', '2099-01-01 00:00:00')
        resp = client.post('/invitasjon?token=bruk-meg', data={
            'token': 'bruk-meg', 'brukernavn': 'invitert@t.no', 'passord': 'passord123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.finn_bruker('invitert@t.no') is not None
        assert db_mod.hent_invitasjon('bruk-meg') is None  # Brukt opp

    def test_invitasjon_for_kort_passord(self, client):
        db_mod.opprett_invitasjon('tok', '2099-01-01 00:00:00')
        resp = client.post('/invitasjon?token=tok', data={
            'token': 'tok', 'brukernavn': 'ny@t.no', 'passord': '12',
        })
        assert 'minst 6 tegn' in resp.data.decode()


# ── Passord-tilbakestilling ────────────────────────

class TestTilbakestilling:
    def test_vis_tilbakestill_side(self, client):
        resp = client.get('/auth/tilbakestill')
        assert resp.status_code == 200
        assert 'tilbakestillingslenke' in resp.data.decode().lower()

    def test_tilbakestill_gir_alltid_samme_melding(self, client):
        # Uansett om e-post finnes eller ikke
        resp = client.post('/auth/tilbakestill', data={'epost': 'finnes@ikke.no'})
        assert 'Sjekk innboksen' in resp.data.decode()

    def test_nytt_passord_ugyldig_token(self, client):
        resp = client.get('/auth/nytt-passord?token=ugyldig')
        assert 'ugyldig eller utl' in resp.data.decode().lower()

    def test_nytt_passord_sett(self, client):
        db_mod.opprett_bruker('reset@t.no', generate_password_hash('gammelt'))
        db_mod.opprett_tilbakestilling('reset-tok', 'reset@t.no', '2099-01-01 00:00:00')
        resp = client.post('/auth/nytt-passord?token=reset-tok', data={
            'token': 'reset-tok', 'passord': 'nyttpassord',
        }, follow_redirects=False)
        assert resp.status_code == 302
        # Token er brukt opp
        assert db_mod.hent_tilbakestilling('reset-tok') is None

    def test_nytt_passord_for_kort(self, client):
        db_mod.opprett_tilbakestilling('tok2', 'x@t.no', '2099-01-01 00:00:00')
        resp = client.post('/auth/nytt-passord?token=tok2', data={
            'token': 'tok2', 'passord': '12',
        })
        assert 'minst 6 tegn' in resp.data.decode()
