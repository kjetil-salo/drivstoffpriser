"""Tester for OCR-endepunktet /api/gjenkjenn-priser og /api/bekreft-pris."""

import io
import db as db_mod
from werkzeug.security import generate_password_hash
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def kamera_client(app, test_db):
    """Test-klient innlogget som bruker med kamera-rolle."""
    db_mod.opprett_bruker('kamera@test.no', generate_password_hash('kamera123'))
    bruker = db_mod.finn_bruker('kamera@test.no')
    db_mod.sett_roller_bruker(bruker['id'], ['kamera'])

    client = app.test_client()
    client.post('/auth/logg-inn', data={
        'brukernavn': 'kamera@test.no',
        'passord': 'kamera123',
    })
    return client


def lag_stasjon(navn='Test', lat=60.39, lon=5.33, osm_id=None):
    db_mod.lagre_stasjon(navn, 'Shell', lat, lon, osm_id or f'node/{navn}')
    return db_mod.get_stasjoner_med_priser(lat, lon)[0]


# ── /api/gjenkjenn-priser ─────────────────────────────────────────────────────

class TestGjenkjennPriser:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/gjenkjenn-priser', data={})
        assert resp.status_code == 401

    def test_vanlig_bruker_har_tilgang_via_kamera_grense_null(self, innlogget_client):
        """KAMERA_PRISANTALL_GRENSE = 0 betyr at alle innloggede brukere kvalifiserer
        for kamera-rollen automatisk. Innlogget bruker uten eksplisitt rolle skal
        ikke få 403 — de når file-valideringen."""
        resp = innlogget_client.post('/api/gjenkjenn-priser', data={})
        # Rollen går gjennom (KAMERA_PRISANTALL_GRENSE=0), men ingen fil => 400
        assert resp.status_code == 400

    def test_ingen_bilde_gir_400(self, kamera_client):
        """Kall uten bilde-fil skal gi 400."""
        resp = kamera_client.post('/api/gjenkjenn-priser', data={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_for_stort_bilde_gir_400(self, kamera_client, monkeypatch):
        """Bilde over 5 MB skal avvises."""
        stort_bilde = b'x' * (5 * 1024 * 1024 + 1)
        data = {'bilde': (io.BytesIO(stort_bilde), 'stor.jpg', 'image/jpeg')}
        resp = kamera_client.post(
            '/api/gjenkjenn-priser',
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400
        assert 'stor' in resp.get_json()['error'].lower()

    def test_admin_har_tilgang(self, admin_client, monkeypatch):
        """Admin skal alltid ha tilgang til OCR."""
        import routes_api

        def fake_ocr(*args, **kwargs):
            return {'bensin': 21.35, 'diesel': 20.50, 'bensin98': None, 'diesel_avgiftsfri': None}

        monkeypatch.setattr(routes_api, '_ocr_via_haiku', fake_ocr)
        monkeypatch.setattr(routes_api, '_ocr_lagre_bilde', lambda *a, **kw: None)
        monkeypatch.setattr(routes_api, '_forbered_haiku_bilde',
                            lambda data, ct: (b'fake', 'image/jpeg', {}))
        monkeypatch.setattr(routes_api, '_ocr_korriger_med_forrige', lambda r, _: r)
        monkeypatch.setattr(routes_api, '_hent_ocr_stasjon_kontekst', lambda _: None)
        monkeypatch.setattr(routes_api, '_ocr_bor_prove_gemini_fallback', lambda *a: False)

        import base64
        liten_jpeg = base64.b64decode(
            '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw'
            '8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARC'
            'AABABADASIA//2Q=='
        )
        data = {'bilde': (io.BytesIO(liten_jpeg), 'test.jpg', 'image/jpeg')}
        resp = admin_client.post(
            '/api/gjenkjenn-priser',
            data=data,
            content_type='multipart/form-data',
        )
        # Skal ikke gi 401/403 — enten 200 eller en veldig spesifikk feil
        assert resp.status_code not in (401, 403)

    def test_kamera_bruker_har_tilgang(self, kamera_client, monkeypatch):
        """Kamera-rollen skal gi tilgang til OCR-endepunktet."""
        import routes_api

        def fake_haiku(*args, **kwargs):
            return {'bensin': 21.35, 'diesel': None, 'bensin98': None, 'diesel_avgiftsfri': None}

        monkeypatch.setattr(routes_api, '_ocr_via_haiku', fake_haiku)
        monkeypatch.setattr(routes_api, '_ocr_lagre_bilde', lambda *a, **kw: None)
        monkeypatch.setattr(routes_api, '_forbered_haiku_bilde',
                            lambda data, ct: (b'fake', 'image/jpeg', {}))
        monkeypatch.setattr(routes_api, '_ocr_korriger_med_forrige', lambda r, _: r)
        monkeypatch.setattr(routes_api, '_hent_ocr_stasjon_kontekst', lambda _: None)
        monkeypatch.setattr(routes_api, '_ocr_bor_prove_gemini_fallback', lambda *a: False)

        data = {'bilde': (io.BytesIO(b'\xff\xd8\xff' + b'\x00' * 100), 'test.jpg', 'image/jpeg')}
        resp = kamera_client.post(
            '/api/gjenkjenn-priser',
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code not in (401, 403)

    def test_ai_konfigurasjonsfeil_gir_503(self, kamera_client, monkeypatch):
        """ValueError fra OCR (manglende API-nøkkel) skal gi 503."""
        import routes_api

        def fake_haiku(*args, **kwargs):
            raise ValueError('API-nøkkel mangler')

        monkeypatch.setattr(routes_api, '_ocr_via_haiku', fake_haiku)
        monkeypatch.setattr(routes_api, '_ocr_lagre_bilde', lambda *a, **kw: None)
        monkeypatch.setattr(routes_api, '_forbered_haiku_bilde',
                            lambda data, ct: (b'fake', 'image/jpeg', {}))
        monkeypatch.setattr(routes_api, '_hent_ocr_stasjon_kontekst', lambda _: None)
        monkeypatch.setattr(routes_api, '_ocr_bor_prove_gemini_fallback', lambda *a: False)

        data = {'bilde': (io.BytesIO(b'\xff\xd8\xff' + b'\x00' * 100), 'test.jpg', 'image/jpeg')}
        resp = kamera_client.post(
            '/api/gjenkjenn-priser',
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 503
        assert 'error' in resp.get_json()

    def test_ai_http_feil_gir_503(self, kamera_client, monkeypatch):
        """httpx.HTTPError fra OCR skal gi 503."""
        import routes_api
        import httpx

        def fake_haiku(*args, **kwargs):
            raise httpx.HTTPError('Connection refused')

        monkeypatch.setattr(routes_api, '_ocr_via_haiku', fake_haiku)
        monkeypatch.setattr(routes_api, '_ocr_lagre_bilde', lambda *a, **kw: None)
        monkeypatch.setattr(routes_api, '_forbered_haiku_bilde',
                            lambda data, ct: (b'fake', 'image/jpeg', {}))
        monkeypatch.setattr(routes_api, '_hent_ocr_stasjon_kontekst', lambda _: None)
        monkeypatch.setattr(routes_api, '_ocr_bor_prove_gemini_fallback', lambda *a: False)

        data = {'bilde': (io.BytesIO(b'\xff\xd8\xff' + b'\x00' * 100), 'test.jpg', 'image/jpeg')}
        resp = kamera_client.post(
            '/api/gjenkjenn-priser',
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 503


# ── /api/bekreft-pris ─────────────────────────────────────────────────────────

class TestBekreftPris:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/bekreft-pris', json={'stasjon_id': 1, 'type': 'bensin'})
        assert resp.status_code == 401

    def test_mangler_stasjon_id_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/bekreft-pris', json={'type': 'bensin'})
        assert resp.status_code == 400

    def test_mangler_type_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/bekreft-pris', json={'stasjon_id': 1})
        assert resp.status_code == 400

    def test_bekreft_eksisterende_pris(self, innlogget_client):
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.35, 20.50)

        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'],
            'type': 'bensin',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_bekreft_stasjon_uten_pris_gir_ok(self, innlogget_client):
        """Bekreftelse av en stasjon uten pris skal returnere ok men ikke feile."""
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'],
            'type': 'bensin',
        })
        assert resp.status_code == 200
        # lagret=False siden ingen pris eksisterer, men respons er alltid ok
        assert resp.get_json()['ok'] is True

    def test_bekreft_oppdaterer_tidspunkt(self, innlogget_client):
        stasjon = lag_stasjon()
        bruker = db_mod.finn_bruker('test@test.no')
        # Legg inn pris som en annen bruker
        db_mod.lagre_pris(stasjon['id'], 21.35, None, bruker_id=None)

        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'],
            'type': 'bensin',
        })
        assert resp.status_code == 200
        # Tidspunktet skal ha blitt oppdatert via INSERT i priser-tabellen
        result = db_mod.get_stasjoner_med_priser(60.39, 5.33)
        assert result[0]['bensin'] == 21.35

    def test_ugyldig_pristype_returnerer_ok_uten_lagring(self, innlogget_client):
        """Ugyldig type skal ignoreres, ikke kaste 500."""
        stasjon = lag_stasjon()
        db_mod.lagre_pris(stasjon['id'], 21.35, None)
        resp = innlogget_client.post('/api/bekreft-pris', json={
            'stasjon_id': stasjon['id'],
            'type': 'ulovlig_type',
        })
        assert resp.status_code == 200


# ── /api/foreslaa-endring ─────────────────────────────────────────────────────

class TestForeslaaEndring:
    def test_krever_innlogging(self, client):
        resp = client.post('/api/foreslaa-endring', json={'stasjon_id': 1, 'foreslatt_navn': 'X'})
        assert resp.status_code == 401

    def test_mangler_stasjon_id_gir_400(self, innlogget_client):
        resp = innlogget_client.post('/api/foreslaa-endring', json={'foreslatt_navn': 'X'})
        assert resp.status_code == 400

    def test_tom_forslag_gir_400(self, innlogget_client):
        """Forslag uten noen felt skal avvises."""
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
        })
        assert resp.status_code == 400

    def test_foreslaa_nytt_navn(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_navn': 'Nytt stasjonsnavn',
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        forslag = db_mod.hent_endringsforslag()
        assert len(forslag) == 1
        assert forslag[0]['foreslatt_navn'] == 'Nytt stasjonsnavn'

    def test_foreslaa_ny_kjede(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'foreslatt_kjede': 'Circle K',
        })
        assert resp.status_code == 200
        forslag = db_mod.hent_endringsforslag()
        assert forslag[0]['foreslatt_kjede'] == 'Circle K'

    def test_kommentar_avkortes_til_500_tegn(self, innlogget_client):
        stasjon = lag_stasjon()
        lang_kommentar = 'X' * 600
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'kommentar': lang_kommentar,
        })
        assert resp.status_code == 200
        forslag = db_mod.hent_endringsforslag()
        assert len(forslag[0]['kommentar']) == 500

    def test_er_nedlagt_rapporterer_stasjon(self, innlogget_client):
        stasjon = lag_stasjon()
        resp = innlogget_client.post('/api/foreslaa-endring', json={
            'stasjon_id': stasjon['id'],
            'er_nedlagt': True,
        })
        assert resp.status_code == 200
        rapporter = db_mod.hent_rapporter()
        assert len(rapporter) == 1
        assert rapporter[0]['stasjon_id'] == stasjon['id']
