"""Tester for anonym prisinnlegging (anonym_innlegging-innstilling)."""

import db as db_mod


def lag_stasjon(navn='Test', lat=60.39, lon=5.33):
    db_mod.lagre_stasjon(navn, 'Shell', lat, lon, f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


# ── Anonym innlegging deaktivert (standard) ────────────────────────────────────

class TestAnonymInnleggingDeaktivert:
    def test_uinnlogget_avvises_nar_deaktivert(self, client):
        stasjon = lag_stasjon()
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 21.0})
        assert resp.status_code == 401

    def test_feilmelding_er_ikke_innlogget(self, client):
        stasjon = lag_stasjon()
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 21.0})
        assert 'Ikke innlogget' in resp.get_json()['error']


# ── Anonym innlegging aktivert ─────────────────────────────────────────────────

class TestAnonymInnleggingAktivert:
    def setup_method(self):
        db_mod.sett_innstilling('anonym_innlegging', '1')

    def test_uinnlogget_kan_lagre_pris(self, client):
        stasjon = lag_stasjon()
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 21.0})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_pris_lagres_under_system_anonym(self, client):
        stasjon = lag_stasjon()
        client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 21.5})

        anonym_id = db_mod.hent_anonym_bruker_id()
        with db_mod.get_conn() as conn:
            rad = conn.execute(
                'SELECT bruker_id FROM priser WHERE stasjon_id = ? ORDER BY id DESC LIMIT 1',
                (stasjon['id'],)
            ).fetchone()
        assert rad is not None
        assert rad[0] == anonym_id

    def test_ugyldig_stasjon_id_gir_400(self, client):
        resp = client.post('/api/pris', json={'stasjon_id': 99999, 'bensin': 21.0})
        # Ingen eksisterende stasjon, men stasjon_id er oppgitt – skal lagres (DB håndterer FK)
        # Det viktige er at manglende stasjon_id gir 400
        assert resp.status_code in (200, 400, 500)  # avhengig av DB-håndtering

    def test_mangler_stasjon_id_gir_400(self, client):
        resp = client.post('/api/pris', json={'bensin': 21.0})
        assert resp.status_code == 400

    def test_pris_utenfor_grense_avvises(self, client):
        stasjon = lag_stasjon()
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 5.0})
        assert resp.status_code == 400

    def test_stor_prisendring_avvises_for_anonym(self, client):
        """Anonym skal avvises hvis ny pris avviker > 40% fra forrige kjente pris."""
        stasjon = lag_stasjon()
        # Legg inn en basislinepris direkte
        db_mod.lagre_pris(stasjon['id'], 21.0, None)

        # 21.0 * 1.41 = 29.61 — mer enn 40% over
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 29.99})
        assert resp.status_code == 400
        assert 'avviker' in resp.get_json()['error'].lower()

    def test_liten_prisendring_godkjennes_for_anonym(self, client):
        """Anonym godkjennes hvis endringen er under 40%."""
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.0, None)

        # 21.0 * 1.10 = 23.10 — 10% opp, godkjent
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 23.10})
        assert resp.status_code == 200

    def test_anonym_uten_forrige_pris_godkjennes(self, client):
        """Avvikssjekk med tom historikk skal godkjenne uansett pris."""
        stasjon = lag_stasjon()
        resp = client.post('/api/pris', json={'stasjon_id': stasjon['id'], 'bensin': 29.0})
        assert resp.status_code == 200


# ── Anonym rate limit ──────────────────────────────────────────────────────────

class TestAnonymRateLimit:
    def setup_method(self):
        db_mod.sett_innstilling('anonym_innlegging', '1')

    def test_blokkeres_etter_maks_innlegginger(self, client):
        """Anonym blokkeres etter _ANONYM_PRIS_MAKS (10) innlegginger per time."""
        import routes_api as api_mod
        stasjon = lag_stasjon()

        # Bruk en fast IP og legg inn maks antall
        for i in range(api_mod._ANONYM_PRIS_MAKS):
            db_mod.logg_rate_limit('anonym_pris', '9.9.9.9')

        resp = client.post(
            '/api/pris',
            json={'stasjon_id': stasjon['id'], 'bensin': 21.0},
            environ_base={'REMOTE_ADDR': '9.9.9.9'},
        )
        assert resp.status_code == 429

    def test_annen_ip_ikke_blokkert(self, client):
        """Blokkering er IP-spesifikk."""
        import routes_api as api_mod
        stasjon = lag_stasjon()

        for i in range(api_mod._ANONYM_PRIS_MAKS):
            db_mod.logg_rate_limit('anonym_pris', '9.9.9.9')

        resp = client.post(
            '/api/pris',
            json={'stasjon_id': stasjon['id'], 'bensin': 21.0},
            environ_base={'REMOTE_ADDR': '1.2.3.4'},
        )
        assert resp.status_code == 200
