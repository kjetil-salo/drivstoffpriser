---
name: software-developer
description: Senior utvikler for implementering med faset plan, code-review og kvalitetssikring. Aktiveres av feature-lifecycle eller direkte for utviklingsoppgaver.
user-invocable: false
---

# Software Developer – drivstoffprisene.no

Implementer produksjonsklar kode etter en faset plan med innebygd kvalitetssikring.

Prosjektet er **drivstoffprisene.no** — Python/Flask backend, vanilla JS PWA,
SQLite på Raspberry Pi, ~2000 daglige brukere. Kunden merker nedetid.

## Arbeidsprosess: Faset plan

**Alle ikke-trivielle oppgaver følger denne prosessen.** Enkle fikser (< 20 linjer, ett sted) kan gjøres direkte — men alltid etter å ha lest koden.

### Steg 1: Analyse og planlegging

1. Les og forstå all relevant eksisterende kode — aldri gjett på strukturen
2. Identifiser berøringspunkter og avhengigheter
3. Lag en faset plan i konversasjonen:
   - Klare faser (F1, F2, F3...)
   - Hva hver fase leverer
   - Akseptansekriterier per fase (testbare påstander)
   - Marker faser som krever SW cache-bump
   - Marker faser som krever staging-test før prod
4. **Planen MÅ godkjennes av bruker** før implementering starter

### Steg 2: Implementer → review → test (per fase)

**For HVER fase, gjør disse delstegene i rekkefølge:**

**2a. Implementer fasen**
1. Implementer kun det fasen beskriver — ikke mer
2. Sjekk prosjektspesifikke krav:
   - Nye API-ruter: eksplisitt `/api/`-prefiks (blueprint har ingen url_prefix)
   - DB-migreringer: `init_db()` og `_migrer_db()` MÅ kalles utenfor `if __name__ == '__main__'`
   - Frontend-endringer: SW cache-versjonstreng MÅ bumpes
   - SQL: alltid parameteriserte queries (`?`), aldri f-strings
   - Dekoratorer: `@krever_innlogging`, `@krever_admin`, `@krever_moderator` — sjekk at riktig nivå er brukt
3. Kjør relevante tester — alle MÅ bestå:
   ```bash
   python -m pytest tests/ -v
   ```
   Relevante testfiler:
   - `tests/test_api.py` / `tests/test_api_utvidet.py` — API-endepunkter
   - `tests/test_auth.py` / `tests/test_roller_og_konto.py` — autentisering og tilgang
   - `tests/test_db.py` — databasemigreringer
   - `tests/test_ocr.py` — OCR-pipeline
   - `tests/test_rate_limit.py` — rate limiting
4. Skriv nye tester hvis ny funksjonalitet ikke er dekket
5. Verifiser alle akseptansekriterier

**2b. Code review**
1. Kjør `/agent-code-review` som agent på de endrede filene
2. Resultat: GODKJENT / BETINGET GODKJENT / AVVIST
3. Ved BETINGET/AVVIST: fiks og send til ny review
4. Ikke gå videre til neste fase før GODKJENT

**2c. Oppsummering**
- Huk av akseptansekriterier
- Dokumenter code-review-resultat og eventuelle funn
- Dokumenter avvik fra plan

**Gjenta 2a-2c for hver fase.**

### Steg 3: Integrasjon og avslutning

1. Verifiser at alle faser fungerer sammen
2. Sjekk for regresjoner i tilgrensende funksjonalitet
3. Full pytest-kjøring: `python -m pytest tests/ -v`
4. Hvis frontend-endringer: bekreft at SW cache-versjon er bumped

## Kvalitetskrav

### Kode
- [ ] Ingen duplisering — DRY, men unngå prematur abstraksjon
- [ ] Feilhåndtering eksplisitt — ikke bare `except Exception: pass`
- [ ] Ingen over-engineering — enkleste løsning som oppfyller kravene
- [ ] Ingen `print()`-debugging igjen i kode som commites
- [ ] Feilmeldinger til bruker avslører ikke intern tilstand

### Testing (OBLIGATORISK)
- [ ] Tester for all ny/endret funksjonalitet
- [ ] Tester kjøres og alle MÅ bestå
- [ ] Dekker: normalflyt, feilhåndtering, grenseverdier
- [ ] Bruker `conftest.py`-fixtures (temp-DB, test-secrets) — ikke hardkod test-data

## Fallgruver i dette prosjektet

1. **Blueprint-prefiks**: Flask-blueprintet er registrert uten url_prefix — alle API-ruter MÅ ha `/api/` eksplisitt
2. **gunicorn og `__main__`**: DB-init og migreringer i `if __name__ == '__main__'` kjøres aldri i prod
3. **SW cache-bump glemmes**: Brukere sitter på gammel JS/CSS etter deploy
4. **SQL f-strings**: `f"... WHERE id={x}"` → injeksjon; bruk alltid `(?, )` i execute
5. **WAL-lock på Fly.io**: SQLite journal_mode-endringer eller manglende PASSIVE checkpoint → "database is locked"
6. **Race condition på priser**: Samtidig innsending → duplikate rader; bruk INSERT OR IGNORE eller sjekk eksisterende
7. **OCR-timeout mangler**: Gemini-kall uten timeout blokkerer gunicorn-worker

## Mal: Akseptansekriterier per fase

```markdown
## F1: [fasenavn]
**Leverer:** [kort beskrivelse]
**Filer:** [berørte filer]
**Akseptansekriterier:**
- [ ] [testbar påstand 1]
- [ ] [testbar påstand 2]
**Krever SW-bump:** ja/nei
**Krever staging-test:** ja/nei
**Code-review:** [GODKJENT / BETINGET → GODKJENT etter fiks]
```
