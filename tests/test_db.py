"""Tester for database-laget."""

import db as db_mod
from werkzeug.security import generate_password_hash, check_password_hash


# ── Stasjoner og priser ───────────────────────────

class TestStasjoner:
    def test_lagre_og_hent_stasjon(self):
        db_mod.lagre_stasjon('Circle K Bergen', 'Circle K', 60.39, 5.33, 'node/123')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert len(result) == 1
        assert result[0]['navn'] == 'Circle K Bergen'
        assert result[0]['kjede'] == 'Circle K'

    def test_upsert_stasjon_med_samme_osm_id(self):
        db_mod.lagre_stasjon('Gammel navn', 'Shell', 60.0, 5.0, 'node/1')
        db_mod.lagre_stasjon('Nytt navn', 'Shell', 60.0, 5.0, 'node/1')
        result = db_mod.get_stasjoner_med_priser(60.0, 5.0)
        assert len(result) == 1
        assert result[0]['navn'] == 'Nytt navn'

    def test_stasjoner_filtreres_pa_radius(self):
        # Bergen sentrum
        db_mod.lagre_stasjon('Nær', 'Test', 60.39, 5.33, 'node/1')
        # Oslo — langt unna
        db_mod.lagre_stasjon('Langt', 'Test', 59.91, 10.75, 'node/2')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33, radius_m=30000)
        assert all(s['navn'] != 'Langt' for s in result)

    def test_stasjoner_sortert_pa_avstand(self):
        db_mod.lagre_stasjon('Lengre', 'Test', 60.40, 5.40, 'node/1')
        db_mod.lagre_stasjon('Nær', 'Test', 60.391, 5.331, 'node/2')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['navn'] == 'Nær'
        assert result[1]['navn'] == 'Lengre'

    def test_stasjoner_limit(self):
        for i in range(5):
            db_mod.lagre_stasjon(f'Stasjon {i}', 'Test', 60.39 + i * 0.001, 5.33, f'node/{i}')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33, limit=3)
        assert len(result) == 3

    def test_avstand_m_er_med(self):
        db_mod.lagre_stasjon('Test', 'Test', 60.391, 5.331, 'node/1')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert 'avstand_m' in result[0]
        assert result[0]['avstand_m'] > 0

    def test_kjede_null_blir_tom_streng(self):
        db_mod.lagre_stasjon('Ukjent', None, 60.39, 5.33, 'node/1')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['kjede'] == ''


class TestPriser:
    def test_lagre_og_hent_pris(self):
        db_mod.lagre_stasjon('Test', 'Test', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        db_mod.lagre_pris(stasjoner[0]['id'], 21.35, 20.50, 22.10)
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] == 21.35
        assert result[0]['diesel'] == 20.50
        assert result[0]['bensin98'] == 22.10

    def test_siste_pris_vinner(self):
        db_mod.lagre_stasjon('Test', 'Test', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        sid = stasjoner[0]['id']
        db_mod.lagre_pris(sid, 20.00, 19.00)
        db_mod.lagre_pris(sid, 22.00, 21.00)
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] == 22.00
        assert result[0]['diesel'] == 21.00

    def test_stasjon_uten_pris(self):
        db_mod.lagre_stasjon('Uten pris', 'Test', 60.39, 5.33, 'node/1')
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] is None
        assert result[0]['diesel'] is None
        assert result[0]['pris_tidspunkt'] is None

    def test_antall_stasjoner_med_pris(self):
        db_mod.lagre_stasjon('Med', 'Test', 60.39, 5.33, 'node/1')
        db_mod.lagre_stasjon('Uten', 'Test', 60.391, 5.331, 'node/2')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        db_mod.lagre_pris(stasjoner[0]['id'], 21.0, 20.0)
        assert db_mod.antall_stasjoner_med_pris() == 1

    def test_prisoppdateringer_med_bruker(self):
        db_mod.opprett_bruker('test@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('test@t.no')
        db_mod.lagre_stasjon('S', 'T', 60.39, 5.33, 'node/1')
        stasjoner = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        db_mod.lagre_pris(stasjoner[0]['id'], 21.0, 20.0, bruker_id=bruker['id'])
        oppdateringer = db_mod.hent_siste_prisoppdateringer(limit=10)
        assert len(oppdateringer) == 1
        assert oppdateringer[0]['brukernavn'] == 'test@t.no'


class TestHaversine:
    def test_samme_punkt_gir_null(self):
        assert db_mod._haversine(60.0, 5.0, 60.0, 5.0) == 0.0

    def test_kjent_avstand(self):
        # Bergen–Stavanger er ca. 160 km
        dist = db_mod._haversine(60.39, 5.33, 58.97, 5.73)
        assert 155_000 < dist < 165_000

    def test_ferske_stasjoner(self):
        db_mod.lagre_stasjon('Test', 'T', 60.39, 5.33, 'node/1')
        assert db_mod.har_ferske_stasjoner(60.39, 5.33)

    def test_ingen_ferske_stasjoner_langt_unna(self):
        db_mod.lagre_stasjon('Test', 'T', 60.39, 5.33, 'node/1')
        # Oslo er langt unna Bergen
        assert not db_mod.har_ferske_stasjoner(59.91, 10.75)


# ── Brukere ────────────────────────────────────────

class TestBrukere:
    def test_opprett_og_finn(self):
        db_mod.opprett_bruker('kjetil@test.no', generate_password_hash('hei123'))
        bruker = db_mod.finn_bruker('kjetil@test.no')
        assert bruker is not None
        assert bruker['brukernavn'] == 'kjetil@test.no'
        assert check_password_hash(bruker['passord_hash'], 'hei123')

    def test_finn_bruker_id(self):
        db_mod.opprett_bruker('a@b.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('a@b.no')
        assert db_mod.finn_bruker_id(bruker['id']) is not None

    def test_finn_ikke_eksisterende(self):
        assert db_mod.finn_bruker('finnes@ikke.no') is None
        assert db_mod.finn_bruker_id(9999) is None

    def test_admin_bruker(self):
        db_mod.opprett_bruker('admin@t.no', generate_password_hash('x'), er_admin=True)
        bruker = db_mod.finn_bruker('admin@t.no')
        assert bruker['er_admin'] == 1

    def test_slett_bruker(self):
        db_mod.opprett_bruker('slett@t.no', generate_password_hash('x'))
        bruker = db_mod.finn_bruker('slett@t.no')
        db_mod.slett_bruker(bruker['id'])
        assert db_mod.finn_bruker('slett@t.no') is None

    def test_antall_brukere(self):
        assert db_mod.antall_brukere() == 0
        db_mod.opprett_bruker('a@b.no', generate_password_hash('x'))
        assert db_mod.antall_brukere() == 1

    def test_hent_alle_brukere(self):
        db_mod.opprett_bruker('a@b.no', generate_password_hash('x'))
        db_mod.opprett_bruker('b@b.no', generate_password_hash('x'), er_admin=True)
        alle = db_mod.hent_alle_brukere()
        assert len(alle) == 2

    def test_oppdater_passord(self):
        db_mod.opprett_bruker('pass@t.no', generate_password_hash('gammelt'))
        db_mod.oppdater_passord('pass@t.no', generate_password_hash('nytt'))
        bruker = db_mod.finn_bruker('pass@t.no')
        assert check_password_hash(bruker['passord_hash'], 'nytt')


# ── Invitasjoner ───────────────────────────────────

class TestInvitasjoner:
    def test_opprett_og_hent(self):
        db_mod.opprett_invitasjon('abc123', '2099-01-01 00:00:00')
        inv = db_mod.hent_invitasjon('abc123')
        assert inv is not None

    def test_utlopt_invitasjon(self):
        db_mod.opprett_invitasjon('gammel', '2020-01-01 00:00:00')
        assert db_mod.hent_invitasjon('gammel') is None

    def test_brukt_invitasjon(self):
        db_mod.opprett_invitasjon('brukes', '2099-01-01 00:00:00')
        db_mod.merk_invitasjon_brukt('brukes')
        assert db_mod.hent_invitasjon('brukes') is None

    def test_ugyldig_token(self):
        assert db_mod.hent_invitasjon('finnes-ikke') is None


# ── Tilbakestilling ────────────────────────────────

class TestTilbakestilling:
    def test_opprett_og_hent(self):
        db_mod.opprett_tilbakestilling('tok123', 'test@t.no', '2099-01-01 00:00:00')
        ts = db_mod.hent_tilbakestilling('tok123')
        assert ts is not None
        assert ts['epost'] == 'test@t.no'

    def test_utlopt(self):
        db_mod.opprett_tilbakestilling('old', 'x@t.no', '2020-01-01 00:00:00')
        assert db_mod.hent_tilbakestilling('old') is None

    def test_brukt(self):
        db_mod.opprett_tilbakestilling('b', 'x@t.no', '2099-01-01 00:00:00')
        db_mod.merk_tilbakestilling_brukt('b')
        assert db_mod.hent_tilbakestilling('b') is None


# ── Visninger / statistikk ────────────────────────

class TestVisninger:
    def test_logg_visning(self):
        db_mod.logg_visning('1.2.3.4', 'device-1', 'Mozilla/5.0')
        stats = db_mod.get_statistikk()
        assert stats['totalt'] == 1
        assert stats['unike_enheter'] == 1

    def test_statistikk_struktur(self):
        stats = db_mod.get_statistikk()
        assert 'prisendringer' in stats
        assert 'totalt' in stats
        assert 'unike_enheter' in stats
        assert 'unike_ips' in stats
        assert 'trend_30d' in stats
        assert 'besok_per_time' in stats
        assert len(stats['trend_30d']) == 30
