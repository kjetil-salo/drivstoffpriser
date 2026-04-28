# drivstoffpriser – TODO og prioriteringsliste

> Oppdatert: 2026-04-05

---

## Prioriteringsliste

### 🔴 Høy prioritet

| # | Oppgave | Begrunnelse |
|---|---------|-------------|
| 1 | **Admin-kart: default kun ferske priser** | Viktigste filter for adminbruk — i dag vises alle farger, default bør være kun stasjoner med pris sist 24t (grønne/gule) |
| 2 | **Filtrer bort utenlandske stasjoner** | ~4800 svenske/finske/russiske stasjoner i DB er støy. Forvirrer brukere og skaper feil kjedetreff |
| 2 | **Fiks seed_stasjoner bakgrunnsfeil** | Bakgrunnsoppdatering av stasjoner feiler stille med "No module named 'seed_stasjoner'" |
| 3 | **Datasamarbeid – API-design** | Partner venter. Symmetrisk synk av prisdata med 1–2 andre apputviklere |
| 4 | **AdBlue-støtte** | Etterspurt av flere brukere. Naturlig utvidelse av eksisterende priskategorier |
| 5 | **Rate limit – deploy** | DB-basert rate limit klar lokalt, ikke deployet ennå |

### 🟡 Middels prioritet

| # | Oppgave | Begrunnelse |
|---|---------|-------------|
| 6 | **Godkjenn-knapp på steder (etterkontroll)** | Beholde etterkontroll-modellen, men legge til eksplisitt godkjenn per stasjon for bedre kontroll |
| 7 | **Topplister med expand-knapp** | Gamification: ukens topp 5 (→10), totalt topp 10 (→20). Motiverer bidragsytere |
| 7 | **Kjede-dropdown refaktorering** | 4 hardkodede HTML-dropdowns → generer fra `KJEDE_NAVN` i kjede.js. Én plass å vedlikeholde |
| 8 | **Brukerside paginering og søk** | Admin-brukersiden er ubrukelig med mange brukere |
| 9 | **Innstillinger: drivstoffvalg** | Brukere vil bare se relevante pristyper (95/98/diesel). localStorage-løsning, ingen innlogging |
| 10 | **Periodisk synk av stasjoner (cron)** | Kjente områder oppdateres ikke uten brukeraktivitet. Cron-jobb for norske bounding boxes |
| 11 | **Blogg med ukentlig prisanalyse** | Halvautomatisk med Claude. Gjør appen mer engasjerende |
| 12 | **Zombie-stasjoner** | Stasjoner fjernet fra OSM lever videre i DB. "Sist sett i OSM"-felt + filtrer gamle |
| 12 | **Fjern LNG/CNG/gass-stasjoner** | OSM-import kan ha tatt inn Gasum/CNG/LNG-stasjoner som ikke er relevante for appen. Filtrer dem bort fra import/søk og rydd eksisterende treff |
| 13 | **Delta-sync til Fly.io** | I dag sendes full DB (~28MB) hvert 6. time. Bytt til kun nye rader siden siste sync |
| 14 | **Kamera: fiks tidspunkt i OCR-statistikk** | `ocr_statistikk.tidspunkt` blir ikke lagret i dag, så kamerabruk kan ikke analyseres per dag/siste 24t. Trengs for å måle Gemini/Haiku-treff over tid |
| 15 | **Slett `kart2`-siden** | `/kart2` ser ut til å være en eldre/alternativ variant av forsiden som ikke er i aktiv bruk. Bør fjernes sammen med route og eventuell død kode for å unngå forvirring og feilretting i feil fil |

### 🟢 Lav prioritet / når tid tillater

| # | Oppgave | Begrunnelse |
|---|---------|-------------|
| 16 | **SSD-migrering på Pi** ⬅️ neste | Planlagt 2026-04-06. Fase 1: flytt kun DB-volum til T5, ingen reboot. Test staging først. |
| 17 | **DB-ytelse: indekser og cache_size** | SSD hjelper litt, men flaskehalsen er trolig manglende indekser + Flask single-thread. Profiler med EXPLAIN QUERY PLAN og vurder PRAGMA cache_size. |
| 18 | **Zero-downtime deploy (Caddy + blue/green)** | ~5–30 sek nedetid per deploy. Ikke kritisk ennå, men vokser med trafikk |
| 19 | **Følg-bilen kart-modus** | Kartet følger posisjonen mens du kjører. Ikke etterspurt ennå, drenerer batteri |
| 20 | **Statistikk-cron (forhåndsberegning)** | Periodisk beregning av prissnitt, billigst per region etc. Kobling til blogg-analyse |
| 21 | **OSM-bidrag** | Bidra nye stasjoner tilbake til OSM. Tung prosess (6-stegs godkjenning), ikke nå |
| 22 | **Failover Cloudflare Worker deploy** | Siste steg i Pi→Fly.io failover: `npx wrangler deploy` + DNS CNAME |
| 23 | **Admin logg-side** | `/admin/logg` viser siste linjer fra app.log. Workaround: ssh + docker exec tail |
| 24 | **Pi-overvåking: installer btop** | Anbefalt førstesteg for SSH-feilsøking. Viser CPU, minne, disk, nettverk og prosesser på selve Pi-en, og er trolig verktøyet som var ment (ikke ptop). Temperatur kan allerede sjekkes enkelt med `vcgencmd measure_temp`; måling 2026-04-22 viste ca. 53–55°C, som ser sunt ut for Pi i fri luft. |
| 25 | **logs.efugl.no: vis tilgjengelig minne på Pi** | Dozzle dekker primært logger/container-visning. Legg til enkel host-status i drift/loggvisning: minne, disk og gjerne temperatur, hentet fra Pi-en uten å være avhengig av interaktiv TUI. |
| 26 | **Netdata eller Glances som web-overvåking (vurder)** | Hvis behovet blir større enn Dozzle + btop: vurder Netdata som fullverdig web-dashboard med historikk/alarmer, eller Glances som lettere alt-i-ett-løsning for web + terminal. |
| 27 | **Pentest** | Sikkerhetstest av appen. Utsatt fra 2026-03-31 |

### 💡 Idéstadiet

| # | Idé | Notat |
|---|-----|-------|
| A | **Ambassadørrekruttering – geografiske hull** | Kjør bynivå-analyse (Bergen, Haugesund/Rogaland nord, Kristiansand, Fredrikstad, Hamar). Rekrutter via lokale FB-grupper/Reddit — 1–3 pers per region er nok til å sette i gang nettverkseffekten. Se hull-analyse-2026-04-08.md |
| B | **Artikkel: PWA vs App Store** | LinkedIn/Medium. 25k brukere uten App Store, one-man show + AI, zero App Store-friksjon |
| B | **Kommentarfelt ved rapportering** | Brukere kan legge til fritekst når de melder stasjon nedlagt. Gjør det lettere å skille brukerfeil fra reelle meldinger |
| C | **Manuell stasjonregistrering** | Stasjoner som ikke finnes i OSM. Admin-grensesnitt med navn, kjede, koordinater |
| C | **Billigste stasjon på veien** | Bruker skriver hvor han/hun skal. Hent rute fra Google/OSRM/Mapbox, finn stasjoner innenfor en smal korridor langs ruten, og ranger på pris + liten omvei. Trenger trolig ikke AI; dette er mer rutegeometri + egne prisdata. |
| C | **Kamera: automatisk 2× zoom** | Bruk `getUserMedia` med zoom-constraints for å sette 2× zoom automatisk. Fungerer kun Android/Chrome — iOS/Safari støtter ikke zoom-constraints. Fallback til fil-input. |
| C | **Kamera: Haiku som siste fallback** | Hvis alle Gemini-modeller feiler eller er overbelastet, prøv Haiku før brukeren må taste manuelt. Viktig for robusthet, men kostnad må vurderes siden Gemini er gratis og Haiku ikke er det. |
| C | **Kamera: A/B-testing haiku vs. gemini** | Velg modell tilfeldig (50/50) per OCR-kall i stedet for `OCR_MODELL`-env. Logg `kilde` i `ocr_statistikk` og bruk `/kamerastatus` for å sammenligne suksessrate, snitt-ms og brukertilfredshet over tid. |
| C | **Dataverdi / kommersialisering** | Unikt datasett, ingen offentlig konkurrent. Vent til basen er større |

---

## Gjennomført ✅

- Stedssøk via Photon API
- Auth: Flask-session, admin-panel, invitasjonslenker, passordreset
- Rate limiting på prisoppdateringer (DB-basert, klar lokalt)
- Rød pin for priser eldre enn 24t
- Korriger pris innen 5 min → oppdaterer eksisterende rad (ikke blokkert)
- OSM-sync overskriver ikke manuelt låste navn/kjede
- Meld nedlagt og Foreslå endring slått sammen til én modal
- Endringsforslag fra brukere (kjede og navn)
- Fly.io failover (Pi → Fly.io synk hvert 6. time)
- R2 backup (Cloudflare, daglig kl. 03:00, 30 dagers rullerende)
- UU/tilgjengelighet-gjennomgang
- Vipps donasjon
- PWA (installerbar, service worker, offline-støtte)
- Topplister for bidragsytere (grunnversjon)
- Trønder Oil som kjede

---

## Driftsnotater

- 2026-04-22: Pi-temperatur målt via `vcgencmd measure_temp` lå rundt 53-55°C.
- Pi-en er headless, uten kabinett, og henger i fri luft. For dagens last ser dette ut til å gi tilstrekkelig passiv kjøling.
- Samme sjekk viste lav last (`0.12, 0.06, 0.06`), god minnemargin (`2.8 GiB tilgjengelig`) og god diskmargin på `/` (`23%` brukt).
- Tailscale + SSH dekker hovedbehovet for driftstilgang. Raspberry Pi Connect vurderes foreløpig ikke som nødvendig for dette oppsettet.
