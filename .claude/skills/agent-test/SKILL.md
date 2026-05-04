---
name: test
description: Teststrategi og kvalitetssikring for drivstoffprisene.no. Kjøres som agent i feature-lifecycle steg 3c. pytest-testing, Playwright E2E, grenseverdier og borderline-caser.
user-invocable: false
context: fork
---

# Test – drivstoffprisene.no

Verifiser at implementert kode faktisk fungerer — ikke bare at det kompilerer. Test grenseverdier og feilhåndtering, ikke bare happy path.

## Testnivåer

Velg basert på hva som ble implementert:

### Nivå 1: Statisk sjekk (alltid)
- Ingen syntax-feil i endrede filer: `python -m py_compile <fil.py>`
- Ingen åpenbare importfeil

### Nivå 2: pytest (ved backend-endringer)

```bash
python -m pytest tests/ -v
```

**Relevante testfiler:**
- `tests/test_api.py` / `tests/test_api_utvidet.py` — API-endepunkter, statuskoder, JSON-format
- `tests/test_auth.py` / `tests/test_roller_og_konto.py` — innlogging, roller, tilgangskontroll
- `tests/test_db.py` / `tests/test_db_utvidet.py` — databasemigreringer, constraints
- `tests/test_ocr.py` — OCR-pipeline og Gemini-respons-parsing
- `tests/test_rate_limit.py` — rate limiting på innlegging og OCR

**Testoppsett (`conftest.py`):**
- Automatisk temp-DB per test (`tmp_path / 'test.db'`)
- `SECRET_KEY=test-secret`, `STATS_KEY=testkey` satt i env
- Ikke hardkod test-data — bruk fixtures

**Skriv nye tester** hvis ny funksjonalitet ikke er dekket. Plasser i riktig testfil basert på tema.

### Nivå 3: E2E med Playwright (ved brukerflyt-endringer)

Bruk kun ved endringer som påvirker navigasjon, skjemaer, kart-interaksjon, eller visuell tilstand.

**Oppsett:**
- Config: `playwright.config.js` — port 7342, webkit-iphone + chromium
- Server: `.venv/bin/python3 server.py`
- Testfiler: `tests/sheet.spec.js` (eksempel)

```bash
npx playwright test --project=webkit-iphone
npx playwright test --project=chromium
```

**Skriv E2E-tester i `tests/` med `.spec.js`-suffix.**

---

## Borderline-caser

De fleste bugs lever i grenseland. For HVER implementert funksjon, identifiser og test:

### Input-grenser
- **Tom input**: tom streng, None/null, tom liste
- **Ugyldig type**: streng der int forventes, negativt tall for pris
- **Grenseverdier for priser**: 0 kr, 99 kr, negative priser (alle skal avvises)
- **Spesialtegn i navn**: `<script>`, `'; DROP TABLE`, emoji, null-bytes
- **For lang streng**: stasjons- og brukernavn over maks lengde

### Tilgangskontroll
- **Uautentisert**: kall uten innlogging → 401 eller redirect
- **Feil rolle**: vanlig bruker på admin-endepunkt → 403
- **Andres data**: bruker prøver å endre annen brukers stasjon

### Tilstandsgrenser
- **Tomt datasett**: ingen stasjoner i DB, ingen priser
- **Konkurrerende innsending**: to priser fra samme bruker på samme stasjon samtidig
- **Session**: utløpt cookie, korrupt cookie, manglende cookie

### Tidsmessige grenser
- **Rask gjentakelse**: dobbel-submit av pris → rate limit eller deduplisering
- **Gammel pris**: stasjon med pris eldre enn 24t — riktig visning i liste

---

## Prosjektspesifikke sjekklister

### Prissending (API)
- [ ] Riktig pris lagres med riktig `bruker_id` og tidspunkt
- [ ] Ugyldig pris (negativ, 0, > 99) avvises med forklarende feil
- [ ] Rate limit utløses ved for mange innsendinger
- [ ] Duplikat (samme stasjon + bruker + minutt) håndteres

### OCR-pipeline
- [ ] Riktig pris ekstraheres fra testbilde
- [ ] Uleselig bilde → meningsfull feil, ikke 500
- [ ] Gemini-timeout → feil kastes, ikke hengende request
- [ ] Prisen som ekstraheres er innenfor gyldige grenser før lagring

### Autentisering og roller
- [ ] Innlogging med feil passord → 401
- [ ] Utlogget bruker omdirigeres til login
- [ ] Admin-endepunkt utilgjengelig for vanlig bruker
- [ ] Moderator-endepunkt tilgjengelig for moderator, ikke vanlig bruker

### Database og migreringer
- [ ] Ny kolonne migreres riktig ved oppstart
- [ ] Migrering er idempotent (trygt å kjøre to ganger)
- [ ] `init_db()` og `_migrer_db()` kjøres utenfor `if __name__ == '__main__'`
- [ ] SQLite constraints håndheves (NOT NULL, CHECK, UNIQUE)

### Flask-ruter
- [ ] Alle nye ruter svarer med riktig HTTP-statuskode
- [ ] Feilresponser returnerer JSON, ikke HTML 500
- [ ] Nye `/api/`-ruter er prefiks-korrekte

---

## Resultatformat

```markdown
## Testresultat: [feature-navn]
**Status:** BESTATT / FEILET

### Funn
| # | Beskrivelse | Alvorlighet | Detaljer |
|---|-------------|-------------|----------|
| T1 | Negativ pris aksepteres | Alvorlig | POST /api/pris med -5.0 gir 200 |
```

Rapporter kun funn — ikke list tester som bestod. Fiks ikke bugs, rapporter dem.
