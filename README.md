# Drivstoffpriser

Mobilapp/PWA for drivstoffpriser i Norge. Viser stasjoner fra OpenStreetMap på kart og i liste, med crowdsourcede priser fra innloggede brukere og moderatorverktøy for kvalitetssikring.

Tilgjengelig på [drivstoffprisene.no](https://drivstoffprisene.no)

---

## For brukere

### Kom i gang

1. Åpne siden i nettleseren på mobilen
2. Trykk **Hent posisjon** eller søk etter et sted
3. Se stasjoner på kartet eller i listeoversikten
4. Trykk på en stasjon for detaljer, priser og navigasjon

**Tips:** Legg siden til på hjemskjermen for best opplevelse (iOS: Del → Legg til på hjem-skjerm).

### Funksjoner

- **Kartvisning** — Interaktivt Leaflet-kart med fargekodede markører etter prisalder
- **Listevisning** — Sortering på avstand og drivstoffpris
- **Drivstofftyper** — 95 oktan, 98 oktan, diesel og avgiftsfri diesel
- **Statistikk** — Billigste og dyreste priser siste 24 timer, antall prisoppdateringer og toppliste
- **Bidragsmodus** — Egen visning for raske prisoppdateringer i felt
- **Stedssøk** — Søk etter by eller sted med tastaturnavigasjon
- **Navigasjon** — Åpne veibeskrivelse direkte fra stasjonskortet
- **Prisrapportering** — Logg inn og rapporter priser på dugnad
- **Legg til stasjon** — Mangler det en stasjon? Legg den til med kartpinne
- **Endringsforslag** — Foreslå nytt navn, kjede eller meld stasjon som nedlagt
- **Hurtigpris / OCR** — Kamera- og OCR-støtte for roller som har tilgang
- **Personlige splash-meldinger** — Ukentlige meldinger basert på aktivitet
- **Blogg og infosider** — Egne sider for blogg, om og personvern
- **Offline-støtte** — Fungerer uten nett med cachet data

### Pin-farger på kartet

| Farge | Betydning |
|-------|-----------|
| 🟢 Grønn | Fersk pris (under 8 timer) |
| 🟠 Oransje | Pris 8–48 timer gammel |
| 🟣 Lilla | Pris 2–7 dager gammel |
| ⚫ Grå | Eldre pris eller ingen pris |

### Innlogging og roller

Alle kan se priser. For å rapportere priser trenger du en konto.

- **Registrering** med e-post og passord
- **Glemt passord** med tilbakestillingslenke på e-post
- **Invitasjoner** kan genereres fra admin
- **Kallenavn** kan settes på "Min konto" og brukes i topplister
- **Roller** brukes for admin, moderator og spesialtilganger som kamera/OCR

---

## Teknisk

### Arkitektur

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│  Nettleser  │ ◄────────────► │ Cloudflare Tunnel│
│  (PWA)      │                └────────┬─────────┘
└─────────────┘                         │
                                        ▼
                    ┌──────────────────────────────────┐
                    │  Raspberry Pi (Docker)            │
                    │  Flask + SQLite + Service Worker  │
                    └──────────┬───────────────────────┘
                               │
                   ┌───────────┼───────────┐
                   ▼           ▼           ▼
               Overpass    Photon       Fly.io
               API (OSM)  (geocoding)  (failover)
                                          ▲
                                          │ DB-synk
                                          │ (systemd, hver 4. time)
                                          │
                                     Raspberry Pi
```

### Stack

| Lag | Teknologi |
|-----|-----------|
| Frontend | Vanilla JS (ES modules), Leaflet.js, OpenStreetMap |
| Backend | Python 3.13, Flask 3 |
| Database | SQLite med WAL-modus |
| Kartdata | OpenStreetMap via Overpass API (daglig bakgrunnsoppdatering) |
| Geocoding | Photon (komoot.io) |
| OCR | Gemini (primær) + Claude Haiku (fallback) via backend-endepunkt |
| Ruteplanlegging | GraphHopper (standard) med OSRM som fallback |
| E-post | Resend (passordreset og enkelte adminflyter) |
| Hosting | Raspberry Pi + Docker + Cloudflare Tunnel — se [docs/infrastruktur.md](docs/infrastruktur.md) |
| Failover | Fly.io — DB synkes automatisk fra Pi hver 4. time (kl 00, 04, 08, 12, 16, 20) |
| PWA | Service Worker, manifest, offline-støtte |
| Tester | pytest (enhetstester), Playwright (E2E) |

### Filstruktur

```
drivstoffpriser/
├── server.py              # Flask-app, oppstart, logging
├── routes_api.py          # API-endepunkter for stasjoner, priser, statistikk, OCR, blogg m.m.
├── routes_auth.py         # Innlogging, registrering, passordreset, min konto
├── routes_admin.py        # Admin-/moderatorpanel, moderering, import, toppliste
├── db.py                  # SQLite-modell, migreringer, rapporter, toppliste, rate limit
├── osm.py                 # Bakgrunnsoppdatering av stasjoner
├── seed_stasjoner.py      # Overpass API-integrasjon (hent alle stasjoner)
├── public/
│   ├── index.html         # Hovedapp med kart, liste, statistikk og dialoger
│   ├── sw.js              # Service Worker (cache-strategier)
│   ├── manifest.json      # PWA-konfigurasjon
│   ├── css/
│   │   ├── tokens.css     # Design-tokens (farger, spacing, radius)
│   │   └── app.css        # Komponentstiler
│   └── js/
│       ├── main.js        # Inngangspunkt, tab-navigasjon, tilstand
│       ├── map.js         # Leaflet-kart, markører, tooltips
│       ├── list.js        # Listevisning med sortering
│       ├── station-sheet.js  # Bunnark med detaljer og prisredigering
│       ├── location.js    # To-stegs GPS (nettverk → høy presisjon)
│       ├── search.js      # Stedssøk med Photon
│       ├── settings.js    # Drivstofftype-filter
│       ├── add-station.js # Legg til stasjon med kartpinne
│       ├── stats.js       # Statistikk, toppliste og promo
│       ├── kjede.js       # Kjedelogoer og farger
│       ├── hurtigpris.js  # Kamera-/hurtigprisflyt
│       ├── ocr.js         # OCR-klient og logging
│       ├── bidrag.js      # Bidragsmodus
│       └── api.js         # Fetch-wrapper mot backend
├── docs/
│   └── datasamarbeid.md   # Notater om partner-/datasamarbeid
├── tests/
│   ├── conftest.py        # Pytest-fixtures
│   ├── test_api.py        # API-endepunkt-tester
│   ├── test_auth.py       # Autentiserings-tester
│   ├── test_admin.py      # Admin-panel-tester
│   ├── test_db.py         # Databasefunksjons-tester
│   ├── test_api_utvidet.py
│   ├── test_db_utvidet.py
│   └── sheet.spec.js      # E2E-tester (Playwright)
├── Dockerfile
├── docker-compose.yml
├── deploy.sh              # Deploy til prod, staging eller Fly.io
└── requirements.txt
```

### API

#### Offentlige

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `GET` | `/api/stasjoner?lat=&lon=&radius=` | Stasjoner innen valgt radius (kun Norge) |
| `GET` | `/api/stedssok?q=` | Geocoding via Photon (komoot.io) |
| `GET` | `/api/statistikk` | Billigste/dyreste priser og antall oppdateringer siste 24t |
| `GET` | `/api/toppliste` | Toppliste totalt og siste uke |
| `GET` | `/api/totalt-med-pris` | Antall stasjoner med registrert pris |
| `GET` | `/api/meg` | Innlogget bruker-info |
| `GET` | `/api/instance` | Sjekk om dette er backup-instansen |
| `GET` | `/api/nyhet` | Aktiv splash-/nyhetsmelding |
| `GET` | `/api/prisregistreringer-per-time` | Prisoppdateringer siste 24 timer per time |
| `GET` | `/api/prisregistreringer-uke` | Rullerende 24t-trend for siste uke |
| `GET` | `/api/enheter-per-dag` | Unike enheter per dag |
| `GET` | `/api/share/prices` | Delingsvennlig prisvisning |
| `POST` | `/api/logview` | Logg sidevisning |
| `POST` | `/api/blogg/vis` | Logg bloggvisning |
| `GET` | `/health` | Helsesjekk |
| `GET` | `/om` | Om-side |
| `GET` | `/personvern` | Personvern-side |

#### Krever innlogging

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `POST` | `/api/pris` | Rapporter pris (95, 98, diesel, avgiftsfri diesel) |
| `POST` | `/api/stasjon` | Opprett stasjon (duplikatsjekk innen 50 m) |
| `POST` | `/api/rapporter-nedlagt` | Meld stasjon som nedlagt |
| `POST` | `/api/foreslaa-endring` | Foreslå nytt navn/kjede |
| `POST` | `/api/gjenkjenn-priser` | OCR/gjenkjenning av priser fra bilde |
| `POST` | `/api/ocr-statistikk` | Logg OCR-resultater |

#### Admin og moderator

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `GET` | `/admin` | Dashboard |
| `GET` | `/admin/steder` | Brukeropprettede / ventende stasjoner |
| `GET` | `/admin/oversikt` | Statistikk med 30-dagers trend og timevisning |
| `GET` | `/admin/prislogg` | Siste 200 prisoppdateringer |
| `GET` | `/admin/kart` | Kart over alle priser |
| `GET` | `/admin/rapporter` | Meldte stasjoner |
| `GET` | `/admin/endringsforslag` | Foreslåtte endringer |
| `GET` | `/admin/deaktiverte` | Deaktiverte stasjoner |
| `GET` | `/admin/brukere` | Brukeradministrasjon |
| `GET` | `/admin/toppliste` | Utvidet toppliste |
| `GET` | `/admin/import` | Import av partnerdata |
| `GET` | `/admin/drivstofftyper` | Administrer drivstofftyper per stasjon |
| `GET` | `/admin/api-nokler` | Administrer API-nøkler for datasamarbeid |
| `GET` | `/admin/leser-kart` | Anonymt GPS-statistikk-kart med heatmap |
| `GET` | `/admin/rutepris` | Ruteplanlegging med prisvisning |
| `POST` | `/admin/invitasjon` | Generer invitasjonslenke |
| `POST` | `/admin/toggle-registrering` | Åpne/steng registrering |
| `PUT` | `/api/sync-db` | DB-synk fra Pi til Fly.io (X-Sync-Key) |

### Dataflyt

**Stasjoner** hentes daglig i bakgrunnen fra Overpass API (alle bensinstasjoner i Norge). Round-robin over tre Overpass-endepunkter med backoff ved feil.

**Priser** rapporteres av brukere og lagres som historikk. Ved raske korrigeringer fra samme bruker oppdateres siste rad innenfor et kort intervall i stedet for å lage duplikater.

**Brukeropprettede stasjoner** opprettes fra appen, får duplikatsjekk innen 50 meter og kan modereres i admin.

**Moderering** skjer via rapporter om nedlagte stasjoner, endringsforslag, deaktivering/reaktivering og godkjenning av ventende stasjoner.

**OCR / hurtigpris** lar brukere med riktig rolle ta bilde av pristavle, gjenkjenne verdier og logge kvaliteten på resultatet.

**Romlig filtrering** bruker bounding box i SQL (indeksert) etterfulgt av Haversine-beregning for nøyaktig avstand.

### Database

```sql
stasjoner       -- navn, kjede, lat/lon, osm_id (UNIQUE), lagt_til_av
priser          -- stasjon_id, bensin, diesel, bensin98, diesel_avgiftsfri, tidspunkt, bruker_id
brukere         -- brukernavn (e-post), passord_hash, roller, kallenavn
invitasjoner    -- token, opprettet, utloper, brukt
tilbakestilling -- token, epost, utloper, brukt
visninger       -- device_id, user_agent, ts
innstillinger   -- nøkkel/verdi for feature flags og admin-innhold
rapporter       -- meldinger om nedlagte stasjoner
endringsforslag -- forslag til navn/kjede
rate_limit      -- enkel IP-/nøkkelbasert rate limiting
blogg_visninger -- logging av bloggtrafikk
ocr_statistikk      -- logging av OCR-flyt, kvalitet og bilder
drivstoffappen_sync -- logging av partner-sync bidrag per kjøring
leser_posisjoner    -- anonyme GPS-posisjoner fra brukere (leser-kart)
```

Indekser finnes blant annet på `stasjoner(lat, lon)`, `visninger(device_id)`, `visninger(ts)` og `rate_limit(type, nokkel, tidspunkt)`.

Passord hashes med Werkzeug/PBKDF2. Sesjoner via signerte Flask-cookies (90 dager). Passordreset via engangslenke (1t utløp).

### Service Worker

| Ressurstype | Strategi |
|-------------|----------|
| Statiske filer (JS, CSS, HTML) | Stale-while-revalidate |
| API-kall | Network-first, fallback til cache |
| Kartfliser | Cache-first, fallback til nettverk |
| POST-forespørsler | Aldri cachet |

Gamle cache-versjoner ryddes automatisk ved oppdatering.

### Tilgjengelighet (UU)

- Skip-lenke for tastaturbrukere
- ARIA-roller: `tablist`, `tab`, `tabpanel`, `dialog`, `alertdialog`, `listbox`
- Piltastnavigasjon i søkeresultater og tabs
- `aria-live="polite"` for dynamiske oppdateringer
- `aria-expanded`, `aria-selected`, `aria-controls` for tilstandshåndtering
- `:focus-visible` for synlige fokusindikatorer
- Tillater zoom (ingen `user-scalable=no`)
- Listevisningen fungerer som tastaturalternativ til kartet

### Kjøre lokalt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 server.py
# → http://localhost:7342
```

### Tester

```bash
# Enhetstester (pytest)
pytest tests/test_db.py tests/test_auth.py tests/test_api.py tests/test_admin.py -q

# E2E-tester (Playwright)
npm install
npx playwright install webkit chromium
npx playwright test
```

Det finnes også utvidede testfiler i [`tests/`](./tests) for nyere API- og DB-funksjonalitet.

### Deploy

```bash
./deploy.sh prod      # Raspberry Pi (port 3002)
./deploy.sh staging   # Pi staging (port 3004)
./deploy.sh fly       # Fly.io (backup)
./deploy.sh all       # Pi prod + Fly.io
```

### Failover — Fly.io DB-synk

Databasen synkes automatisk fra Pi til Fly.io hver 4. time (kl 00, 04, 08, 12, 16, 20):

Fly.io er satt opp som cold standby for failover, ikke som alltid-på drift. Maskinen kan derfor sove mellom synk og forespørsler, og første request etter dvale kan bruke litt ekstra tid mens instansen starter.

- **Script:** `/home/kjetil/drivstoffpriser/sync-til-fly.sh`
- **Cron:** root sin crontab (`0 */4 * * *`)
- **Logg:** `/tmp/drivstoff-sync.log`

Manuell synk:
```bash
sudo bash /home/kjetil/drivstoffpriser/sync-til-fly.sh
```

### Backup

Databasen sikkerhetskopieres daglig til lokal disk og eksternt til Cloudflare R2.

- **Script:** `/home/kjetil/drivstoffpriser/backup.sh`
- **Cron:** kjetil sin crontab, `0 3 * * *` (kl 03:00 hver natt)
- **Logg:** `/tmp/drivstoff-backup.log`

**Lokal backup:**

| Type | Mappe | Oppbevaring |
|------|-------|-------------|
| Daglig | `/home/kjetil/backups/drivstoffpriser/daglig/` | 7 filer |
| Ukentlig (søndager) | `/home/kjetil/backups/drivstoffpriser/ukentlig/` | 4 filer |

**Ekstern backup (Cloudflare R2):**

| | |
|--|--|
| Bucket | `drivstoffpriser-backup` |
| Mappe | `daglig/` |
| Oppbevaring | 30 dager rullerende |
| Verktøy | rclone v1.73.1+ |

Backup bruker `sqlite3 .backup`-kommandoen for WAL-sikker kopi uten låsningsproblemer.

Manuell kjøring:
```bash
bash /home/kjetil/drivstoffpriser/backup.sh
rclone ls r2:drivstoffpriser-backup/daglig/
```

### Miljøvariabler

| Variabel | Standard | Beskrivelse |
|----------|----------|-------------|
| `PORT` | `7342` | HTTP-port |
| `DB_PATH` | `./drivstoff.db` | Sti til SQLite-database |
| `DATA_DIR` | `.` | Mappe for app.log |
| `SECRET_KEY` | — | Flask session-nøkkel (**sett sterk verdi i prod**) |
| `STATS_KEY` | — | Nøkkel for admin-statistikk |
| `RESEND_API_KEY` | — | API-nøkkel for Resend (e-post) |
| `BASE_URL` | `request.host_url` | Base-URL for e-postlenker |
| `FLY_APP_NAME` | — | Satt på Fly.io for backup-deteksjon |
| `GRAPHHOPPER_API_KEY` | — | API-nøkkel for GraphHopper ruteplanlegging |
| `RUTE_MOTOR` | `graphhopper` | `graphhopper` eller `osrm` |
| `GEMINI_API_KEY` | — | API-nøkkel for Gemini OCR (primær) |
| `ANTHROPIC_API_KEY` | — | API-nøkkel for Claude Haiku OCR (fallback) |
| `LOG_LEVEL` | `INFO` | Loggnivå |
