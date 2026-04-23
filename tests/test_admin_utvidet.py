"""Tester for admin-ruter som mangler dekning: rollekontroll, stasjonskontroll,
endringsforslag-flyt, deaktivering/reaktivering, nyhet og slett-operasjoner."""

import sqlite3

import db as db_mod
from werkzeug.security import generate_password_hash
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def moderator_client(app, test_db):
    """Test-klient innlogget som moderator (ikke admin)."""
    db_mod.opprett_bruker('mod@test.no', generate_password_hash('mod123'))
    bruker = db_mod.finn_bruker('mod@test.no')
    db_mod.sett_roller_bruker(bruker['id'], ['moderator'])

    client = app.test_client()
    client.post('/auth/logg-inn', data={
        'brukernavn': 'mod@test.no',
        'passord': 'mod123',
    })
    return client


def lag_stasjon(navn='Test', kjede='Shell', lat=60.39, lon=5.33, osm_id=None):
    db_mod.lagre_stasjon(navn, kjede, lat, lon, osm_id or f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


def lag_bruker(epost='bruker@test.no', er_admin=False):
    db_mod.opprett_bruker(epost, generate_password_hash('passord123'), er_admin=er_admin)
    return db_mod.finn_bruker(epost)


# ── Moderator vs. admin tilgangskontroll ──────────────────────────────────────

class TestRollekontrollAdmin:
    """Endepunkter med @krever_admin skal avvise moderator."""

    def test_brukersiden_krever_admin(self, moderator_client):
        resp = moderator_client.get('/admin/brukere')
        assert resp.status_code == 403

    def test_slett_bruker_krever_admin(self, moderator_client):
        resp = moderator_client.post('/admin/slett-bruker', data={'bruker_id': 1})
        assert resp.status_code == 403

    def test_slett_stasjon_krever_admin(self, moderator_client):
        resp = moderator_client.post('/admin/slett-stasjon', data={'stasjon_id': 1})
        assert resp.status_code == 403

    def test_godkjenn_stasjon_krever_admin(self, moderator_client):
        resp = moderator_client.post('/admin/godkjenn-stasjon', data={'stasjon_id': 1})
        assert resp.status_code == 403

    def test_toggle_registrering_krever_admin(self, moderator_client):
        resp = moderator_client.post('/admin/toggle-registrering', data={'verdi': '1'})
        assert resp.status_code == 403

    def test_nyhet_krever_admin(self, moderator_client):
        resp = moderator_client.get('/admin/nyhet')
        assert resp.status_code == 403

    def test_invitasjon_krever_admin(self, moderator_client):
        resp = moderator_client.post('/admin/invitasjon')
        assert resp.status_code == 403



class TestRollekontrollModerator:
    """Endepunkter med @krever_moderator skal tillate moderator."""

    def test_prislogg_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/prislogg')
        assert resp.status_code == 200

    def test_rapporter_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/rapporter')
        assert resp.status_code == 200

    def test_endringsforslag_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/endringsforslag')
        assert resp.status_code == 200

    def test_drivstofftyper_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/drivstofftyper')
        assert resp.status_code == 200

    def test_deaktiverte_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/deaktiverte')
        assert resp.status_code == 200

    def test_steder_tilgjengelig_for_moderator(self, moderator_client):
        resp = moderator_client.get('/admin/steder')
        assert resp.status_code == 200

    def test_admin_er_ogsaa_moderator(self, admin_client):
        """Admin-rollen skal gi tilgang til alle moderator-endepunkter."""
        resp = admin_client.get('/admin/rapporter')
        assert resp.status_code == 200


class TestRollekontrollUinnlogget:
    """Uinnloggede brukere skal redirectes til innlogging."""

    def test_admin_redirecter(self, client):
        resp = client.get('/admin', follow_redirects=False)
        assert resp.status_code == 302

    def test_prislogg_redirecter(self, client):
        resp = client.get('/admin/prislogg', follow_redirects=False)
        assert resp.status_code == 302

    def test_steder_redirecter(self, client):
        resp = client.get('/admin/steder', follow_redirects=False)
        assert resp.status_code == 302


# ── Slett-operasjoner ─────────────────────────────────────────────────────────

class TestSlettBruker:
    def test_slett_eksisterende_bruker(self, admin_client):
        lag_bruker('slett@t.no')
        bruker = db_mod.finn_bruker('slett@t.no')
        resp = admin_client.post('/admin/slett-bruker',
                                  data={'bruker_id': bruker['id']},
                                  follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.finn_bruker('slett@t.no') is None

    def test_slett_ikke_eksisterende_id_er_trygt(self, admin_client):
        """Sletting av ikke-eksisterende bruker skal ikke kaste unntak."""
        resp = admin_client.post('/admin/slett-bruker', data={'bruker_id': 99999},
                                  follow_redirects=False)
        assert resp.status_code == 302

    def test_slett_mangler_id_er_trygt(self, admin_client):
        resp = admin_client.post('/admin/slett-bruker', data={}, follow_redirects=False)
        assert resp.status_code == 302


class TestSlettStasjon:
    def test_slett_brukeropprettet_stasjon(self, admin_client):
        bruker = lag_bruker('b@t.no')
        stasjon_id, _ = db_mod.opprett_stasjon('SlettMeg', 'Shell', 60.39, 5.33, bruker['id'])
        resp = admin_client.post('/admin/slett-stasjon',
                                  data={'stasjon_id': stasjon_id},
                                  follow_redirects=False)
        assert resp.status_code == 302
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert not any(s['id'] == stasjon_id for s in stasjoner)

    def test_slett_stasjon_fjerner_priser(self, admin_client):
        bruker = lag_bruker('b@t.no')
        stasjon_id, _ = db_mod.opprett_stasjon('SlettMedPris', 'Shell', 60.39, 5.33, bruker['id'])
        db_mod.lagre_pris(stasjon_id, 21.0, 20.0, bruker_id=bruker['id'])
        admin_client.post('/admin/slett-stasjon', data={'stasjon_id': stasjon_id})
        with db_mod.get_conn() as conn:
            antall = conn.execute('SELECT COUNT(*) FROM priser WHERE stasjon_id = ?', (stasjon_id,)).fetchone()[0]
        assert antall == 0


class TestSlettPrisloggRad:
    def test_slett_prisrad(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'])
        oppdateringer = db_mod.hent_siste_prisoppdateringer(limit=1)
        pris_id = oppdateringer[0]['id']

        resp = admin_client.delete(f'/admin/prislogg/{pris_id}')
        assert resp.status_code == 204

    def test_slett_ikke_eksisterende_prisrad(self, admin_client):
        resp = admin_client.delete('/admin/prislogg/999999')
        assert resp.status_code == 404

    def test_moderator_kan_slette_prisrad(self, moderator_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'])
        oppdateringer = db_mod.hent_siste_prisoppdateringer(limit=1)
        pris_id = oppdateringer[0]['id']
        resp = moderator_client.delete(f'/admin/prislogg/{pris_id}')
        assert resp.status_code == 204

    def test_vanlig_bruker_kan_ikke_slette_prisrad(self, innlogget_client):
        resp = innlogget_client.delete('/admin/prislogg/1')
        assert resp.status_code == 403


# ── Stasjonskontroll: godkjenn og deaktiver ───────────────────────────────────

class TestGodkjennStasjon:
    def test_godkjenn_ventende_stasjon(self, admin_client):
        bruker = lag_bruker('b@t.no')
        stasjon_id, _ = db_mod.opprett_stasjon('Ventende', 'Shell', 60.39, 5.33, bruker['id'])
        # Sett stasjon som ikke godkjent (ventende)
        with db_mod.get_conn() as conn:
            conn.execute('UPDATE stasjoner SET godkjent = 0 WHERE id = ?', (stasjon_id,))

        resp = admin_client.post('/admin/godkjenn-stasjon',
                                  data={'stasjon_id': stasjon_id},
                                  follow_redirects=False)
        assert resp.status_code == 302

        with db_mod.get_conn() as conn:
            row = conn.execute('SELECT godkjent FROM stasjoner WHERE id = ?', (stasjon_id,)).fetchone()
        assert row[0] == 1

    def test_moderator_kan_ikke_godkjenne_stasjon(self, moderator_client):
        resp = moderator_client.post('/admin/godkjenn-stasjon', data={'stasjon_id': 1})
        assert resp.status_code == 403


class TestDeaktiverStasjon:
    def test_deaktiver_stasjon_via_rapport_flyt(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])

        resp = admin_client.post('/admin/deaktiver-stasjon',
                                  data={'stasjon_id': stasjon['id']},
                                  follow_redirects=False)
        assert resp.status_code == 302

        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert not any(s['id'] == stasjon['id'] for s in stasjoner)

    def test_reaktiver_stasjon(self, admin_client):
        stasjon = lag_stasjon()
        db_mod.deaktiver_stasjon(stasjon['id'])

        resp = admin_client.post('/admin/reaktiver-stasjon',
                                  data={'stasjon_id': stasjon['id']},
                                  follow_redirects=False)
        assert resp.status_code == 302

        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert any(s['id'] == stasjon['id'] for s in stasjoner)

    def test_moderator_kan_deaktivere(self, moderator_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])
        resp = moderator_client.post('/admin/deaktiver-stasjon',
                                      data={'stasjon_id': stasjon['id']},
                                      follow_redirects=False)
        assert resp.status_code == 302


# ── Endringsforslag-flyt ───────────────────────────────────────────────────────

class TestEndringsforslag:
    def test_innsendt_forslag_vises_i_admin(self, innlogget_client, admin_client):
        stasjon = lag_stasjon()
        innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Nytt navn',
        })
        forslag = db_mod.hent_endringsforslag()
        assert len(forslag) == 1
        assert forslag[0]['foreslatt_navn'] == 'Nytt navn'

    def test_godkjenn_endringsforslag_oppdaterer_navn(self, admin_client):
        stasjon = lag_stasjon('Gammelt')
        bruker = lag_bruker()
        db_mod.legg_til_endringsforslag(stasjon['id'], bruker['id'], 'Oppdatert', None)
        forslag = db_mod.hent_endringsforslag()
        forslag_id = forslag[0]['id']

        admin_client.post('/admin/godkjenn-endringsforslag', data={
            'forslag_id': forslag_id,
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Oppdatert',
            'foreslatt_kjede': '',
            'bruker_id': bruker['id'],
            'stasjon_navn': 'Gammelt',
            'ekstra_melding': '',
        })

        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert stasjoner[0]['navn'] == 'Oppdatert'
        assert db_mod.hent_endringsforslag() == []

    def test_avvis_endringsforslag_sletter_forslaget(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.legg_til_endringsforslag(stasjon['id'], bruker['id'], 'Annet', None)
        forslag = db_mod.hent_endringsforslag()
        forslag_id = forslag[0]['id']

        admin_client.post('/admin/avvis-endringsforslag', data={
            'forslag_id': forslag_id,
            'bruker_id': bruker['id'],
            'stasjon_navn': stasjon['navn'],
            'ekstra_melding': '',
        })

        assert db_mod.hent_endringsforslag() == []
        # Stasjonsnavn skal IKKE ha endret seg
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert stasjoner[0]['navn'] == stasjon['navn']

    def test_moderator_kan_godkjenne_endringsforslag(self, moderator_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.legg_til_endringsforslag(stasjon['id'], bruker['id'], 'Moderatornavn', None)
        forslag = db_mod.hent_endringsforslag()

        resp = moderator_client.post('/admin/godkjenn-endringsforslag', data={
            'forslag_id': forslag[0]['id'],
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Moderatornavn',
            'foreslatt_kjede': '',
            'bruker_id': bruker['id'],
            'stasjon_navn': stasjon['navn'],
            'ekstra_melding': '',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_vanlig_bruker_kan_ikke_godkjenne_endringsforslag(self, innlogget_client):
        resp = innlogget_client.post('/admin/godkjenn-endringsforslag', data={
            'forslag_id': 1, 'stasjon_id': 1,
        })
        assert resp.status_code == 403

    def test_antall_ubehandlede_teller_korrekt(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.legg_til_endringsforslag(stasjon['id'], bruker['id'], 'X', None)
        db_mod.legg_til_endringsforslag(stasjon['id'], bruker['id'], None, 'CircleK')
        assert db_mod.antall_ubehandlede_endringsforslag() == 2


# ── Admin-nyhet ───────────────────────────────────────────────────────────────

class TestAdminNyhet:
    def test_publiser_nyhet(self, admin_client):
        resp = admin_client.post('/admin/nyhet', data={
            'tekst': 'Viktig beskjed!',
            'utloper': '2099-12-31T23:59',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.hent_innstilling('nyhet_tekst') == 'Viktig beskjed!'

    def test_fjern_nyhet(self, admin_client):
        db_mod.sett_innstilling('nyhet_tekst', 'Gammel')
        db_mod.sett_innstilling('nyhet_utloper', '2099-12-31T23:59')

        admin_client.post('/admin/nyhet', data={'action': 'fjern'})
        assert db_mod.hent_innstilling('nyhet_tekst') == ''

    def test_moderator_kan_ikke_publisere_nyhet(self, moderator_client):
        resp = moderator_client.post('/admin/nyhet', data={
            'tekst': 'X', 'utloper': '2099-12-31T23:59',
        })
        assert resp.status_code == 403

    def test_tom_tekst_lagres_ikke(self, admin_client):
        admin_client.post('/admin/nyhet', data={'tekst': '', 'utloper': '2099-12-31T23:59'})
        # Tekst er tom — skal ikke overskrive
        assert (db_mod.hent_innstilling('nyhet_tekst') or '') == ''


# ── Sett-kjede og endre-navn via JSON-API ─────────────────────────────────────

class TestAdminSettKjedeJSON:
    def test_sett_kjede(self, admin_client):
        stasjon = lag_stasjon('Ukjent', kjede=None)
        resp = admin_client.post('/admin/sett-kjede', json={
            'stasjon_id': stasjon['id'],
            'kjede': 'YX',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert stasjoner[0]['kjede'] == 'YX'

    def test_sett_kjede_mangler_stasjon_id(self, admin_client):
        resp = admin_client.post('/admin/sett-kjede', json={'kjede': 'Shell'})
        assert resp.status_code == 400

    def test_moderator_kan_sette_kjede(self, moderator_client):
        stasjon = lag_stasjon()
        resp = moderator_client.post('/admin/sett-kjede', json={
            'stasjon_id': stasjon['id'], 'kjede': 'Esso',
        })
        assert resp.status_code == 200

    def test_vanlig_bruker_kan_ikke_sette_kjede(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/admin/sett-kjede', json={
            'stasjon_id': stasjon['id'], 'kjede': 'Esso',
        })
        assert resp.status_code == 403


class TestAdminEndreNavnJSON:
    def test_endre_navn(self, admin_client):
        stasjon = lag_stasjon('Gammelt')
        resp = admin_client.post('/admin/endre-navn', json={
            'stasjon_id': stasjon['id'],
            'navn': 'Nytt',
        })
        assert resp.status_code == 200
        assert resp.get_json()['navn'] == 'Nytt'

    def test_mangler_navn_gir_400(self, admin_client):
        stasjon = lag_stasjon()
        resp = admin_client.post('/admin/endre-navn', json={
            'stasjon_id': stasjon['id'], 'navn': '',
        })
        assert resp.status_code == 400

    def test_ukjent_stasjon_gir_404(self, admin_client):
        resp = admin_client.post('/admin/endre-navn', json={
            'stasjon_id': 99999, 'navn': 'X',
        })
        assert resp.status_code == 404

    def test_moderator_kan_endre_navn(self, moderator_client):
        stasjon = lag_stasjon('Navn1')
        resp = moderator_client.post('/admin/endre-navn', json={
            'stasjon_id': stasjon['id'], 'navn': 'Navn2',
        })
        assert resp.status_code == 200


# ── Toggle-registrering ───────────────────────────────────────────────────────

class TestToggleRegistrering:
    def test_stopp_registrering(self, admin_client):
        admin_client.post('/admin/toggle-registrering', data={'verdi': '1'})
        assert db_mod.hent_innstilling('registrering_stoppet') == '1'

    def test_aapne_registrering(self, admin_client):
        db_mod.sett_innstilling('registrering_stoppet', '1')
        admin_client.post('/admin/toggle-registrering', data={'verdi': '0'})
        assert db_mod.hent_innstilling('registrering_stoppet') == '0'


# ── Avvis-rapport ─────────────────────────────────────────────────────────────

class TestAvvisRapport:
    def test_avvis_rapport_sletter_rapporter(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])

        resp = admin_client.post('/admin/avvis-rapport',
                                  data={'stasjon_id': stasjon['id']},
                                  follow_redirects=False)
        assert resp.status_code == 302
        assert db_mod.antall_ubehandlede_rapporter() == 0

    def test_stasjon_forblir_aktiv_etter_avvis(self, admin_client):
        stasjon = lag_stasjon()
        bruker = lag_bruker()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])
        admin_client.post('/admin/avvis-rapport', data={'stasjon_id': stasjon['id']})

        # Stasjonen skal fortsatt vises
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert any(s['id'] == stasjon['id'] for s in stasjoner)
