---
name: feature-lifecycle
description: Orkestrerer hele feature-livssyklusen for drivstoffprisene.no — analyse, faset implementering, code-review, test og deploy. Bruk for nye features som krever flere steg.
user-invocable: true
argument-hint: "[feature-beskrivelse]"
---

# Feature-livssyklus – drivstoffprisene.no

Orkestrerer hele livssyklusen for en ny feature — fra analyse via faset implementering til deployet kode. Koordinerer code-review og test i riktig rekkefølge og sikrer at ingenting hoppes over.

Prosjektet er **drivstoffprisene.no** — Python/Flask backend, vanilla JS PWA,
SQLite på Raspberry Pi, ~2000 daglige brukere. Kunden merker nedetid. Vær konservativ.

---

## Prosess

### Steg 1: Analyse

Gjøres i konversasjonen — ikke opprett dokumenter med mindre featuren er kompleks.

1. Les relevant eksisterende kode før du foreslår noe
2. Utred problemet med minst 2 tilnærminger
3. Vurder mot prosjektets prinsipper:
   - Enkel, pragmatisk løsning — ikke over-engineer
   - Public-facing kode er konservativ — admin-sider kan brekke
   - Staging før prod ved dialog- og SW-endringer
   - Nye DB-kolonner krever migrering utenfor `if __name__ == '__main__'`
4. Anbefal én løsning med begrunnelse — ikke bare list alternativer
5. **Bruker MÅ godkjenne retningen** før implementering starter

### Steg 2: Faset plan

Lag en faset plan i konversasjonen:

- Del opp i logiske faser (F1, F2, F3...)
- Hver fase har klare akseptansekriterier
- Typisk faseinndeling:
  - **Backend-endringer** (DB-migrering, nye ruter, logikk)
  - **Frontend-endringer** (HTML/CSS/JS, SW-bump ved behov)
  - **Integrasjon og edge cases**
- Marker om SW cache-bump er nødvendig (frontend-endringer = alltid bump)
- Marker om endringer krever staging-test før prod

**Bruker MÅ godkjenne planen** før implementering starter.

### Steg 2.5: UX-sjekk (betinget)

Kun hvis featuren berører noe brukeren ser — bruk `ux-guidelines`-skillen som referanse:

- Farger kun fra tokens (`public/css/tokens.css`) — aldri hardkodede hex
- Touch-targets ≥ 44x44px
- Ny UI fungerer fra 320px til desktop
- 401/nettverksfeil håndteres gracefully i JS
- Spinner/feedback ved asynkrone operasjoner
- Kamera-flyt: preview, feil, suksess
- Radius, spacing og z-index fra tokens — ikke nye verdier

### Steg 3: Implementering per fase

For HVER fase, gjenta dette mønsteret:

**3a. Implementer**
- Implementer kun det fasen beskriver — ikke mer
- Husk: `init_db()` og `_migrer_db()` MÅ kalles utenfor `if __name__ == '__main__'`
- Husk: nye API-ruter MÅ ha eksplisitt `/api/`-prefiks i Flask-blueprintet
- Verifiser akseptansekriteriene fra planen

**3b. Code review**
- Kjør `/agent-code-review` som agent på de endrede filene
- Resultat: GODKJENT / BETINGET GODKJENT / AVVIST
- Ved BETINGET/AVVIST: fiks og send til ny review
- Ikke gå videre til neste fase før GODKJENT

**3c. Test**
- Kjør `agent-test`-skillen som agent
- Velger riktig nivå (pytest / Playwright) basert på hva som ble endret
- Rapporterer funn — fikser dem ikke
- Ved FEILET: fiks og kjør ny test-agent

**3d. Oppsummering**
- Kort notis om hva som ble gjort og eventuelle avvik fra planen
- Marker fasen som fullført

**Gjenta 3a-3d for hver fase.**

### Steg 4: Integrasjon

1. Verifiser at alle faser fungerer sammen
2. Sjekk for regresjoner i tilgrensende funksjonalitet
3. Hvis frontend-endringer: bekreft at SW cache-versjon er bumped
4. Full pytest-kjøring: `python -m pytest tests/ -v`

### Steg 5: Deploy

Bruk `/ops-deploy`-skillen:

1. **Staging først** hvis endringen berører:
   - Service Worker eller PWA-manifest
   - Dialog/modal-flyt
   - Innlogging, sesjon eller tilgangskontroll
2. **Direkte til prod** er OK for:
   - Rene backend-endringer uten frontend
   - Admin-sider og interne verktøy
   - Retting av aktive bugs

### Steg 6: Commit

Norske commit-meldinger. Temabaserte commits:
1. DB-migrering (hvis separat)
2. Backend-implementering
3. Frontend-implementering (hvis separat)

---

## Kvalitetsporter

| Port | Hvem | Hva |
|------|------|-----|
| Etter analyse | Bruker | Riktig forstått? Anbefaling fornuftig? |
| Etter plan | Bruker | Faser OK? Noe mangler? |
| Etter 3b per fase | Code-review agent | Kode-kvalitet, sikkerhet, Flask-konvensjoner |
| Etter 3c per fase | pytest | Funksjonalitet, grenseverdier, regresjon |
| Etter steg 5 | Bruker | Staging OK? Klart for prod? |

---

## Anti-patterns

1. **Implementere før analyse**: Les koden først — ikke gjett på eksisterende struktur
2. **Hoppe over code-review**: Hver fase MÅ gjennom `/agent-code-review` — ingen unntak
3. **Droppe SW-bump**: Frontend-endringer uten SW-bump → brukere sitter på gammel kode
4. **Migrering i `__main__`**: Gunicorn kjører ikke `__main__` — migreringen skjer aldri i prod
5. **Direkte til prod på SW-endringer**: Tvungen SW-reload mistet 75 brukere (skjedde 14.04)
6. **Over-engineering**: Dette er et hobby-prosjekt — enkle løsninger er bedre
7. **Implementere utover plan**: Lever det som ble planlagt, ikke mer
