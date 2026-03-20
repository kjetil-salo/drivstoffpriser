# Drivstoffpriser

Mobilapp for å se og rapportere bensinpriser på stasjoner i nærheten. Viser stasjoner fra OpenStreetMap på et interaktivt kart, sortert etter avstand. Innloggede brukere kan rapportere priser på dugnad.

Tilgjengelig på [drivstoff.ksalo.no](https://drivstoff.ksalo.no)

---

## For brukere

### Kom i gang

1. Åpne siden i nettleseren på mobilen
2. Trykk **Hent posisjon** – appen finner bensinstasjoner innen 20 km
3. Trykk på en stasjon på kartet (pin eller navn) for å se priser
4. Logg inn og trykk **Endre pris** for å rapportere en ny pris

**Tips:** Legg siden til på hjemskjermen for best opplevelse (iOS: Del → Legg til på hjem-skjerm).

### Stedssøk

Ikke på stedet du vil sjekke? Trykk 🔍 øverst og søk etter en by eller et sted.

### Liste vs. kart

Bruk fanen **Liste** nederst for å se stasjonene sortert etter avstand, 95 oktan eller diesel.

### Pin-farger

| Farge | Betydning |
|-------|-----------|
| 🟢 Grønn | Fersk pris (under 24 timer) |
| 🔴 Rød | Pris eldre enn 24 timer |
| ⚫ Grå | Ingen pris registrert |

### Innlogging og tilgang

Alle kan se priser. For å rapportere priser må du ha en konto.

- **Registrer deg:** `/registrer` – oppgi e-post, passord og tilgangskode
- **Glemt passord:** Tilbakestillingslenke sendes til e-posten din
- **Admin-panel:** `/admin` – inviter brukere, slett brukere (kun admin)

### Støtt appen

Appen er gratis og reklamefri. Liker du den? Støtt gjerne via Vipps nederst i listevisningen.

---

## Teknisk løsning

### Arkitektur

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│  Nettleser  │ ◄────────────► │ Cloudflare Tunnel│
│  (mobil)    │                └────────┬─────────┘
└─────────────┘                         │
                                        ▼
                               ┌─────────────────┐
                               │  Raspberry Pi   │
                               │  Docker         │
                               │  Flask + SQLite │
                               └────────┬────────┘
                                        │
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                        Overpass    Nominatim    SQLite
                        API (OSM)   (geocoding)  (lokal DB)
```

### Stack

| Lag | Teknologi |
|-----|-----------|
| Frontend | Vanilla JS (ES modules), Leaflet.js 1.9.4, OpenStreetMap |
| Backend | Python 3.12, Flask 3 |
| Database | SQLite (stasjoner, priser, brukere, statistikk) |
| Kartdata | OpenStreetMap via Overpass API |
| Geocoding | Nominatim |
| E-post | Resend (passordreset) |
| Hosting | Raspberry Pi + Docker + Cloudflare Tunnel |
| Tester | Playwright (WebKit/iPhone 14 + Chromium) |

### Filstruktur

```
drivstoffpriser/
├── server.py              # Flask-app, API-ruter, auth
├── db.py                  # SQLite-tilgang, datamodell
├── osm.py                 # Overpass API-integrasjon
├── public/
│   ├── index.html
│   ├── css/
│   │   ├── tokens.css     # Design-tokens (farger, spacing)
│   │   └── app.css        # Komponent-stiler
│   └── js/
│       ├── main.js        # Inngangspunkt, koordinerer moduler
│       ├── map.js         # Leaflet-kart, markører, tooltips
│       ├── station-sheet.js  # Bunnark for stasjondetaljer
│       ├── list.js        # Listevisning med sortering
│       ├── location.js    # To-stegs GPS-henting
│       ├── search.js      # Stedssøk (Nominatim)
│       └── api.js         # fetch-wrapper mot backend
├── tests/
│   └── sheet.spec.js      # Playwright E2E-tester
├── Dockerfile
├── docker-compose.yml
└── deploy-pi.sh           # rsync + docker compose til Pi
```

### API

| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `GET` | `/api/stasjoner?lat=&lon=` | Stasjoner innen 20 km, maks 15 stk (kun Norge) |
| `POST` | `/api/pris` | Rapporter ny pris – krever innlogging |
| `GET` | `/api/stedssok?q=` | Geocoding via Nominatim |
| `GET` | `/api/meg` | Innlogget bruker (`{ innlogget, brukernavn }`) |
| `POST` | `/api/logview` | Logg sidevisning (statistikk) |
| `POST` | `/auth/logg-inn` | Logg inn med e-post/passord |
| `GET` | `/auth/logg-ut` | Logg ut |
| `GET/POST` | `/auth/tilbakestill` | Be om tilbakestillingslenke på e-post |
| `GET/POST` | `/auth/nytt-passord?token=` | Sett nytt passord via token |
| `GET/POST` | `/registrer` | Registrer konto med tilgangskode |
| `GET/POST` | `/invitasjon?token=` | Opprett bruker via invitasjonslenke (admin) |
| `GET` | `/admin` | Admin-panel |
| `POST` | `/admin/invitasjon` | Generer invitasjonslenke |
| `POST` | `/admin/slett-bruker` | Slett bruker |
| `GET` | `/oversikt?key=` | Statistikk-side |

### Dataflyt – stasjoner

1. Frontend kaller `/api/stasjoner?lat=&lon=`
2. Backend validerer at koordinater er innenfor Norge
3. Sjekker om det finnes ferske stasjoner (< 24t) i SQLite for området
4. Hvis ikke: henter fra Overpass API og lagrer i SQLite
5. Returnerer stasjoner med siste pris, sortert etter avstand

### Database

```sql
stasjoner    -- navn, kjede, koordinater, osm_id (UNIQUE)
priser       -- stasjon_id, bensin, diesel, tidspunkt (historikk)
brukere      -- brukernavn (e-post), passord_hash, er_admin, opprettet
invitasjoner -- token (UUID), opprettet, utloper, brukt
tilbakestilling -- token, epost, utloper, brukt (passordreset)
visninger    -- ip, device_id, user_agent, ts (statistikk)
```

Priser lagres som historikk – siste pris hentes med `MAX(id) GROUP BY stasjon_id`.

Passord hashes med `werkzeug.security` (pbkdf2:sha256). Sesjoner via signerte Flask-cookies (`SECRET_KEY`). Passordreset via Resend (e-post med engangslenke, 1t utløp).

### iOS-spesifikke hensyn

- `tap: false` i Leaflet-config forhindrer at Leaflet's touch-handler blokkerer native button-klikk
- `overflow-y: auto` kun på indre scroll-container, ikke på `position: fixed`-element
- `touch-action: manipulation` på alle knapper eliminerer 300 ms tap-forsinkelse
- `visibility: hidden` på backdrop fremfor kun `pointer-events: none`

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
npm install
npx playwright install webkit chromium
npx playwright test
```

### Deploy til Pi

```bash
bash deploy-pi.sh
```

Krever SSH-tilgang til `kjetil@100.76.35.106` og Docker på Pi-en. Cloudflare Tunnel kjøres separat på Pi.

### Miljøvariabler

| Variabel | Standard | Beskrivelse |
|----------|----------|-------------|
| `PORT` | `7342` | HTTP-port |
| `DB_PATH` | `./drivstoff.db` | Sti til SQLite-database |
| `DATA_DIR` | `.` | Mappe for app.log |
| `STATS_KEY` | `salo` | Nøkkel for `/oversikt` |
| `SECRET_KEY` | — | Flask session-nøkkel – **sett sterk verdi i prod** |
| `RESEND_API_KEY` | — | API-nøkkel for Resend (passordreset) |
| `REGISTRER_KODE` | — | Tilgangskode for selvregistrering |
| `BASE_URL` | request.host_url | Base-URL for invitasjons- og resetlenker |

> Env-variabler på Pi settes i `~/drivstoffpriser/.env`. Generer SECRET_KEY med:
> `python3 -c "import secrets; print(secrets.token_hex(32))"`
