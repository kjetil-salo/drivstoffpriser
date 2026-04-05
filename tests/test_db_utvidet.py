"""Tester for db-funksjoner som mangler dekning."""

import db as db_mod
from werkzeug.security import generate_password_hash


# ── Hjelpefunksjoner ───────────────────────────────

def lag_stasjon(navn='Test', kjede='Shell', lat=60.39, lon=5.33, osm_id=None):
    db_mod.lagre_stasjon(navn, kjede, lat, lon, osm_id or f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


def lag_bruker(epost='bruker@test.no', er_admin=False):
    db_mod.opprett_bruker(epost, generate_password_hash('passord123'), er_admin=er_admin)
    return db_mod.finn_bruker(epost)


# ── Toppliste ──────────────────────────────────────

class TestToppliste:
    def test_tom_toppliste(self):
        resultat = db_mod.hent_toppliste()
        assert resultat == []

    def test_en_bruker_med_registreringer(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)
        db_mod.lagre_pris(stasjon['id'], 22.0, 21.0, bruker_id=bruker['id'], min_intervall=0)

        resultat = db_mod.hent_toppliste()
        assert len(resultat) == 1
        assert resultat[0]['antall'] == 2

    def test_sortert_etter_antall(self):
        b1 = lag_bruker('a@test.no')
        b2 = lag_bruker('b@test.no')
        s = lag_stasjon()
        db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=b1['id'], min_intervall=0)
        db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=b2['id'], min_intervall=0)
        db_mod.lagre_pris(s['id'], 22.0, 21.0, bruker_id=b2['id'], min_intervall=0)

        resultat = db_mod.hent_toppliste()
        assert resultat[0]['antall'] == 2  # b2 øverst
        assert resultat[1]['antall'] == 1

    def test_partner_ekskludert(self):
        partner_id = db_mod.hent_eller_opprett_partner('TestPartner')
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=partner_id, min_intervall=0)

        resultat = db_mod.hent_toppliste()
        assert resultat == []

    def test_limit(self):
        for i in range(5):
            b = lag_bruker(f'u{i}@test.no')
            s = lag_stasjon(f'Stasjon{i}', osm_id=f'node/{i}')
            db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=b['id'], min_intervall=0)

        resultat = db_mod.hent_toppliste(limit=3)
        assert len(resultat) == 3

    def test_kallenavn_i_resultat(self):
        bruker = lag_bruker()
        db_mod.sett_kallenavn(bruker['id'], 'Kjetil')
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)

        resultat = db_mod.hent_toppliste()
        assert resultat[0]['kallenavn'] == 'Kjetil'


class TestMinPlassering:
    def test_ingen_registreringer_gir_none(self):
        bruker = lag_bruker()
        assert db_mod.hent_min_plassering(bruker['id']) is None

    def test_eneste_bruker_er_plassering_1(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)

        plass = db_mod.hent_min_plassering(bruker['id'])
        assert plass['plass'] == 1
        assert plass['antall'] == 1

    def test_korrekt_plassering_med_konkurrenter(self):
        b1 = lag_bruker('a@test.no')
        b2 = lag_bruker('b@test.no')
        s = lag_stasjon()
        # b2 registrerer 3, b1 registrerer 1
        for _ in range(3):
            db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=b2['id'], min_intervall=0)
        db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=b1['id'], min_intervall=0)

        plass = db_mod.hent_min_plassering(b1['id'])
        assert plass['plass'] == 2

    def test_partner_teller_ikke_mot_plassering(self):
        bruker = lag_bruker()
        partner_id = db_mod.hent_eller_opprett_partner('XPartner')
        s = lag_stasjon()
        for _ in range(5):
            db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=partner_id, min_intervall=0)
        db_mod.lagre_pris(s['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)

        plass = db_mod.hent_min_plassering(bruker['id'])
        assert plass['plass'] == 1


class TestTopplisteAdmin:
    def test_inkluderer_brukernavn(self):
        bruker = lag_bruker('kjent@test.no')
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)

        resultat = db_mod.hent_toppliste_admin()
        assert len(resultat) == 1
        assert resultat[0]['brukernavn'] == 'kjent@test.no'

    def test_partner_ekskludert(self):
        partner_id = db_mod.hent_eller_opprett_partner('X')
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=partner_id, min_intervall=0)

        resultat = db_mod.hent_toppliste_admin()
        assert resultat == []


# ── Rapporter ──────────────────────────────────────

class TestRapporter:
    def test_meld_nedlagt_og_hent(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])

        rapporter = db_mod.hent_rapporter()
        assert len(rapporter) == 1
        assert rapporter[0]['stasjon_id'] == stasjon['id']
        assert rapporter[0]['brukernavn'] == bruker['brukernavn']

    def test_antall_i_rapport(self):
        b1 = lag_bruker('a@test.no')
        b2 = lag_bruker('b@test.no')
        stasjon = lag_stasjon()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], b1['id'])
        db_mod.meld_stasjon_nedlagt(stasjon['id'], b2['id'])

        rapporter = db_mod.hent_rapporter()
        assert rapporter[0]['antall'] == 2

    def test_deaktivert_stasjon_vises_ikke_i_rapporter(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])
        db_mod.deaktiver_stasjon(stasjon['id'])

        rapporter = db_mod.hent_rapporter()
        assert rapporter == []

    def test_antall_ubehandlede(self):
        bruker = lag_bruker()
        s1 = lag_stasjon('S1', osm_id='node/s1')
        s2 = lag_stasjon('S2', lat=60.40, osm_id='node/s2')
        db_mod.meld_stasjon_nedlagt(s1['id'], bruker['id'])
        db_mod.meld_stasjon_nedlagt(s2['id'], bruker['id'])

        assert db_mod.antall_ubehandlede_rapporter() == 2

    def test_hent_rapportorer_epost(self):
        b1 = lag_bruker('a@test.no')
        b2 = lag_bruker('b@test.no')
        stasjon = lag_stasjon('MinStasjon')
        db_mod.meld_stasjon_nedlagt(stasjon['id'], b1['id'])
        db_mod.meld_stasjon_nedlagt(stasjon['id'], b2['id'])

        navn, eposter = db_mod.hent_rapportorer_epost(stasjon['id'])
        assert navn == 'MinStasjon'
        assert set(eposter) == {'a@test.no', 'b@test.no'}

    def test_slett_rapporter_for_stasjon(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.meld_stasjon_nedlagt(stasjon['id'], bruker['id'])
        db_mod.slett_rapporter_for_stasjon(stasjon['id'])

        assert db_mod.antall_ubehandlede_rapporter() == 0


# ── Stasjon-livssyklus ─────────────────────────────

class TestFinnNaerStasjon:
    def test_finner_nær_stasjon(self):
        lag_stasjon(lat=60.39, lon=5.33, osm_id='node/a')
        naer = db_mod.finn_naer_stasjon(60.39001, 5.33001)
        assert naer is not None

    def test_ingen_treff_langt_unna(self):
        lag_stasjon(lat=60.39, lon=5.33, osm_id='node/a')
        naer = db_mod.finn_naer_stasjon(60.50, 5.50)
        assert naer is None

    def test_deaktivert_teller_ikke(self):
        stasjon = lag_stasjon(lat=60.39, lon=5.33, osm_id='node/a')
        db_mod.deaktiver_stasjon(stasjon['id'])
        naer = db_mod.finn_naer_stasjon(60.39001, 5.33001)
        assert naer is None


class TestOpprettStasjon:
    def test_opprett_ny_stasjon(self):
        bruker = lag_bruker()
        stasjon_id, duplikat = db_mod.opprett_stasjon('Ny Shell', 'Shell', 60.39, 5.33, bruker['id'])
        assert stasjon_id is not None
        assert duplikat is None

    def test_duplikat_blokkeres(self):
        bruker = lag_bruker()
        db_mod.opprett_stasjon('Eksisterende', 'Shell', 60.39, 5.33, bruker['id'])
        stasjon_id, duplikat = db_mod.opprett_stasjon('Kopi', 'Shell', 60.39001, 5.33001, bruker['id'])
        assert stasjon_id is None
        assert duplikat is not None
        assert duplikat['navn'] == 'Eksisterende'

    def test_opprettet_stasjon_venter_godkjenning(self):
        bruker = lag_bruker()
        stasjon_id, _ = db_mod.opprett_stasjon('Ny stasjon', 'Circle K', 60.39, 5.33, bruker['id'])
        assert stasjon_id is not None
        ventende = db_mod.hent_ventende_stasjoner('ventende')
        assert any(s['id'] == stasjon_id for s in ventende)
        # Ikke synlig på kart før godkjent
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert not any(s['navn'] == 'Ny stasjon' for s in stasjoner)
        # Godkjenn og sjekk at den dukker opp
        db_mod.godkjenn_stasjon(stasjon_id)
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert any(s['navn'] == 'Ny stasjon' for s in stasjoner)


class TestDeaktivering:
    def test_deaktiver_og_reaktiver(self):
        stasjon = lag_stasjon()
        db_mod.deaktiver_stasjon(stasjon['id'])

        deaktiverte = db_mod.hent_deaktiverte_stasjoner()
        assert any(s['id'] == stasjon['id'] for s in deaktiverte)

        db_mod.reaktiver_stasjon(stasjon['id'])
        deaktiverte = db_mod.hent_deaktiverte_stasjoner()
        assert not any(s['id'] == stasjon['id'] for s in deaktiverte)

    def test_deaktivert_vises_ikke_i_stasjonsøk(self):
        stasjon = lag_stasjon()
        db_mod.deaktiver_stasjon(stasjon['id'])
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert not any(s['id'] == stasjon['id'] for s in stasjoner)

    def test_reaktivert_vises_igjen(self):
        stasjon = lag_stasjon()
        db_mod.deaktiver_stasjon(stasjon['id'])
        db_mod.reaktiver_stasjon(stasjon['id'])
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert any(s['id'] == stasjon['id'] for s in stasjoner)


# ── Bruker-metadata ────────────────────────────────

class TestKallenavn:
    def test_sett_og_hent(self):
        bruker = lag_bruker()
        db_mod.sett_kallenavn(bruker['id'], 'Proff Sjåfør')
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert oppdatert['kallenavn'] == 'Proff Sjåfør'

    def test_overskrive_kallenavn(self):
        bruker = lag_bruker()
        db_mod.sett_kallenavn(bruker['id'], 'Gammelt')
        db_mod.sett_kallenavn(bruker['id'], 'Nytt')
        oppdatert = db_mod.finn_bruker_id(bruker['id'])
        assert oppdatert['kallenavn'] == 'Nytt'


class TestSettKjede:
    def test_sett_kjede(self):
        stasjon = lag_stasjon('Ukjent', kjede=None)
        db_mod.sett_kjede_for_stasjon(stasjon['id'], 'Circle K')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert stasjoner[0]['kjede'] == 'Circle K'


class TestEndreNavn:
    def test_endre_navn(self):
        stasjon = lag_stasjon('Gammelt navn')
        resultat = db_mod.endre_navn_stasjon(stasjon['id'], 'Nytt navn')
        assert resultat is True
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert stasjoner[0]['navn'] == 'Nytt navn'

    def test_ukjent_stasjon_gir_false(self):
        resultat = db_mod.endre_navn_stasjon(9999, 'Navn')
        assert resultat is False


# ── Partner ────────────────────────────────────────

class TestPartner:
    def test_opprett_ny_partner(self):
        partner_id = db_mod.hent_eller_opprett_partner('Fuelsync')
        assert isinstance(partner_id, int)

    def test_samme_partner_gir_samme_id(self):
        id1 = db_mod.hent_eller_opprett_partner('Fuelsync')
        id2 = db_mod.hent_eller_opprett_partner('Fuelsync')
        assert id1 == id2

    def test_ulike_partnere_gir_ulike_id(self):
        id1 = db_mod.hent_eller_opprett_partner('Partner A')
        id2 = db_mod.hent_eller_opprett_partner('Partner B')
        assert id1 != id2

    def test_partner_brukernavn_format(self):
        partner_id = db_mod.hent_eller_opprett_partner('Fuelsync')
        bruker = db_mod.finn_bruker_id(partner_id)
        assert bruker['brukernavn'] == 'partner:Fuelsync'


# ── Priser siste 24 timer ──────────────────────────

class TestBilligstePriser24t:
    def test_tom_uten_priser(self):
        assert db_mod.hent_billigste_priser_24t() == []

    def test_returnerer_pris(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)
        resultat = db_mod.hent_billigste_priser_24t()
        assert len(resultat) == 1
        assert resultat[0]['bensin'] == 21.0

    def test_deaktivert_stasjon_ekskludert(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)
        db_mod.deaktiver_stasjon(stasjon['id'])
        assert db_mod.hent_billigste_priser_24t() == []


class TestAntallPrisoppdateringer24t:
    def test_null_uten_priser(self):
        assert db_mod.antall_prisoppdateringer_24t() == 0

    def test_teller_korrekt(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)
        db_mod.lagre_pris(stasjon['id'], 22.0, 21.0, bruker_id=bruker['id'], min_intervall=0)
        assert db_mod.antall_prisoppdateringer_24t() == 2


# ── Trenddata ──────────────────────────────────────

class TestTrenddata:
    def test_prisoppdateringer_per_time_struktur(self):
        resultat = db_mod.prisoppdateringer_per_time_48t()
        assert len(resultat) == 49
        assert all(isinstance(t, str) and isinstance(n, int) for t, n in resultat)

    def test_nye_brukere_per_time_struktur(self):
        resultat = db_mod.nye_brukere_per_time_48t()
        assert len(resultat) == 49
        assert all(isinstance(t, str) and isinstance(n, int) for t, n in resultat)

    def test_prisoppdatering_telles_i_trend(self):
        bruker = lag_bruker()
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, 20.0, bruker_id=bruker['id'], min_intervall=0)
        resultat = db_mod.prisoppdateringer_per_time_48t()
        total = sum(n for _, n in resultat)
        assert total == 1
