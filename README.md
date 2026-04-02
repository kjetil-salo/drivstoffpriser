# Drivstoffpriser

Mobilapp for sanntids bensinpriser i Norge. Viser stasjoner fra OpenStreetMap på et interaktivt kart med crowdsourcede priser fra innloggede brukere.

Tilgjengelig på [drivstoff.ksalo.no](https://drivstoff.ksalo.no)

---

## For brukere

### Kom i gang

1. Åpne siden i nettleseren på mobilen
2. Trykk **Hent posisjon** eller søk etter et sted
3. Se stasjoner på kartet eller i listeoversikten
4. Trykk på en stasjon for detaljer, priser og navigasjon

**Tips:** Legg siden til på hjemskjermen for best opplevelse (iOS: Del → Legg til på hjem-skjerm).

### Funksjoner

- **Kartvisning** — Interaktivt kart med fargekodede markører etter prisalder
- **Listevisning** — Sorterbar liste etter avstand, 95 oktan, 98 oktan eller diesel
- **Statistikk** — Billigste og dyreste priser siste 24 timer, side om side per drivstofftype
- **Stedssøk** — Søk etter by eller sted med tastaturnavigasjon
- **Navigasjon** — Åpne veibeskrivelse direkte fra stasjonskortet
- **Prisrapportering** — Logg inn og rapporter priser på dugnad
- **Legg til stasjon** — Mangler det en stasjon? Legg den til med kartpinne
- **Innstillinger** — Velg hvilke drivstofftyper som vises
- **Offline-støtte** — Fungerer uten nett med cachet data

### Pin-farger på kartet

| Farge | Betydning |
|-------|-----------|
| 🟢 Grønn | Fersk pris (under 8 timer) |
| 🟠 Oransje | Pris 8–48 timer gammel |
| 🟣 Lilla | Pris 2–7 dager gammel |
| ⚫ Grå | Eldre pris eller ingen pris |

### Innlogging

Alle kan se priser. For å rapportere priser trenger du en konto:

- **Registrer deg** med e-post, passord og tilgangskode
- **Glemt passord?** Tilbakestillingslenke sendes på e-post
- **Invitasjon** — admin kan sende invitasjonslenker

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
               Overpass    Nominatim    Fly.io
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
| Backend | Python 3.12, Flask 3 |
| Database | SQLite med WAL-modus |
| Kartdata | OpenStreetMap via Overpass API (daglig bakgrunnsoppdatering) |
| Geocoding | Nominatim |
| E-post | Resend (passordreset) |
| Hosting | Raspberry Pi + Docker + Cloudflare Tunnel |
| Failover | Fly.io — DB synkes automatisk fra Pi hver 4. time |
| PWA | Service Worker, manifest, offline-støtte |
| Tester | pytest (enhetstester), Playwright (E2E) |

### Filstruktur

```
drivstoffpriser/
├── server.py              # Flask-app, oppstart, logging
├── routes_api.py          # API-endepunkter (stasjoner, priser, statistikk)
├── routes_auth.py         # Innlogging, registrering, passordreset
├── routes_admin.py        # Admin-panel, brukeradmin, statistikk
├── db.py                  # SQLite-modell, romlig filtrering, migrering
├── osm.py                 # Bakgrunnsoppdatering av stasjoner
├── seed_stasjoner.py      # Overpass API-integrasjon (hent alle stasjoner)
├── public/
│   ├── index.html         # SPA med tre visninger (kart, liste, statistikk)
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
│       ├── search.js      # Stedssøk med Nominatim
│       ├── settings.js    # Drivstofftype-filter
│       ├── add-station.js # Legg til stasjon med kartpinne
│       ├── stats.js       # Statistikkfanen
│       ├── kjede.js       # Kjedelogoer og farger
│       └── api.js         # Fetch-wrapper mot backend
├── tests/
│   ├── conftest.py        # Pytest-fixtures
│   ├── test_api.py        # API-endepunkt-tester
│   ├── test_auth.py       # Autentiserings-tester
│   ├── test_admin.py      # Admin-panel-tester
│   ├── test_db.py         # Databasefunksjons-tester
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
| `GET` | `/api/stasjoner?lat=&lon=` | Stasjoner innen 30 km (maks 30, kun Norge) |
| `GET` | `/api/stedssok?q=` | Geocoding via Nominatim |
| `GET` | `/api/statistikk` | Billigste/dyreste priser og antall oppdateringer siste 24t |
| `GET` | `/api/totalt-med-pris` | Antall stasjoner med registrert pris |
| `GET` | `/api/meg` | Innlogget bruker-info |
| `GET` | `/api/instance` | Sjekk om dette er backup-instansen |
| `POST` | `/api/logview` | Logg sidevisning |
| `GET` | `/health` | Helsesjekk |

#### Krever innlogging

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `POST` | `/api/pris` | Rapporter pris (stasjon_id, bensin, diesel, bensin98) |
| `POST` | `/api/stasjon` | Opprett stasjon (duplikatsjekk innen 50 m) |

#### Admin

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `GET` | `/admin` | Dashboard |
| `GET` | `/admin/oversikt` | Statistikk med 30-dagers trend og timevisning |
| `GET` | `/admin/prislogg` | Siste 200 prisoppdateringer |
| `GET` | `/admin/kart` | Kart over alle priser |
| `POST` | `/admin/invitasjon` | Generer invitasjonslenke |
| `PUT` | `/api/sync-db` | DB-synk fra Pi til Fly.io (X-Sync-Key) |

### Dataflyt

**Stasjoner** hentes daglig i bakgrunnen fra Overpass API (alle bensinstasjoner i Norge). Round-robin over tre Overpass-endepunkter med backoff ved feil.

**Priser** rapporteres av brukere og lagres som historikk. Siste pris hentes med `MAX(id) GROUP BY stasjon_id`.

**Romlig filtrering** bruker bounding box i SQL (indeksert) etterfulgt av Haversine-beregning for nøyaktig avstand.

### Database

```sql
stasjoner       -- navn, kjede, lat/lon, osm_id (UNIQUE), lagt_til_av
priser          -- stasjon_id, bensin, diesel, bensin98, tidspunkt, bruker_id
brukere         -- brukernavn (e-post), passord_hash, er_admin
invitasjoner    -- token, opprettet, utloper, brukt
tilbakestilling -- token, epost, utloper, brukt
visninger       -- device_id, user_agent, ts
```

Indekser på `stasjoner(lat, lon)`, `visninger(device_id)` og `visninger(ts)`.

Passord hashes med PBKDF2:SHA256. Sesjoner via signerte Flask-cookies (90 dager). Passordreset via engangslenke (1t utløp).

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

### Deploy

```bash
./deploy.sh prod      # Raspberry Pi (port 3002)
./deploy.sh staging   # Pi staging (port 3004)
./deploy.sh fly       # Fly.io (backup)
./deploy.sh all       # Pi prod + Fly.io
```

### Failover — Fly.io DB-synk

Databasen synkes automatisk fra Pi til Fly.io hver 4. time via en systemd timer på Pi:

- **Script:** `/usr/local/bin/sync-db-to-fly.py`
- **Timer:** `sync-db-fly.timer` (systemd, `OnUnitActiveSec=4h`, `Persistent=true`)
- **Logg:** `/var/log/sync-db-fly.log`
- **Auth:** Fly.io deploy-token i `/etc/sync-db-fly.env` (kun lesbar av root)

Sikkerhetsgardene:
1. `sqlite3.backup()` — konsistent kopi, håndterer WAL korrekt
2. `PRAGMA integrity_check` — verifiserer filen **før** upload
3. Fly.io-databasen røres aldri hvis integrity check feiler

Manuell synk:
```bash
sudo systemctl start sync-db-fly.service
sudo journalctl -u sync-db-fly.service -n 20
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

Backup bruker `python3 sqlite3.backup()` for WAL-sikker kopi uten låsningsproblemer.

Manuell kjøring:
```bash
bash /home/kjetil/drivstoffpriser/backup.sh
rclone --config ~/.config/rclone/rclone.conf ls r2:drivstoffpriser-backup/daglig/
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
| `LOG_LEVEL` | `INFO` | Loggnivå |
