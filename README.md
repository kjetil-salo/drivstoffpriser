# Drivstoffpriser

Mobilapp for å se og oppdatere bensinpriser på stasjoner i nærheten. Viser stasjoner fra OpenStreetMap på et interaktivt kart, sortert etter avstand. Alle kan rapportere priser – appen er laget for å holde lokale priser oppdatert på dugnad.

Tilgjengelig på [drivstoff.ksalo.no](https://drivstoff.ksalo.no)

---

## For brukere

### Kom i gang

1. Åpne siden i nettleseren på mobilen
2. Trykk **Hent posisjon** – appen finner bensinstasjoner innen 20 km
3. Trykk på en stasjon på kartet (pin eller navn) for å se priser
4. Vil du rapportere en pris? Logg inn og trykk **Endre pris** i stasjonskort-et

**Tips:** Legg siden til på hjemskjermen for best opplevelse (iOS: Del → Legg til på hjem-skjerm).

### Stedssøk

Ikke på stedet du vil sjekke? Trykk 🔍 øverst og søk etter en by eller et sted. Kartet flytter seg og henter stasjoner for det området.

### Liste vs. kart

Bruk fanen **Liste** nederst for å se stasjonene sortert etter avstand med priser – nyttig når du vil sammenligne raskt uten å navigere i kartet.

### Innlogging og tilgang

Alle kan se priser. For å rapportere priser må du ha en konto. Nye brukere inviteres av administrator via en engangslenke (gyldig 24 timer). Lenken genereres i admin-panelet og deles manuelt (f.eks. via SMS).

- **Logg inn:** Trykk *Logg inn* øverst til høyre
- **Admin-panel:** `/admin` (kun for admin-brukere) – inviter nye brukere, slett brukere

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
| Database | SQLite (stasjoner, priser, statistikk) |
| Kartdata | OpenStreetMap via Overpass API |
| Geocoding | Nominatim |
| Hosting | Raspberry Pi + Docker + Cloudflare Tunnel |
| Tester | Playwright (WebKit/iPhone 14 + Chromium) |

### Filstruktur

```
drivstoffpriser/
├── server.py              # Flask-app, API-ruter
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
│       ├── list.js        # Listevisning
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
| Metode | Endepunkt | Beskrivelse |
|--------|-----------|-------------|
| `GET` | `/api/stasjoner?lat=&lon=` | Stasjoner innen 20 km, maks 15 stk |
| `POST` | `/api/pris` | Rapporter ny pris – krever innlogging (`stasjon_id`, `bensin`, `diesel`) |
| `GET` | `/api/stedssok?q=` | Geocoding via Nominatim |
| `GET` | `/api/meg` | Innlogget bruker (`{ innlogget, brukernavn }`) |
| `POST` | `/api/logview` | Logg sidevisning (statistikk) |
| `POST` | `/auth/logg-inn` | Logg inn med brukernavn/passord |
| `GET` | `/auth/logg-ut` | Logg ut |
| `GET/POST` | `/invitasjon?token=` | Opprett bruker via invitasjonslenke |
| `GET` | `/admin` | Admin-panel – inviter og slett brukere (krever admin) |
| `POST` | `/admin/invitasjon` | Generer ny invitasjonslenke |
| `POST` | `/admin/slett-bruker` | Slett bruker |
| `GET` | `/oversikt?key=` | Statistikk-side (IP-lenker til ipinfo.io) |

### Dataflyt – stasjoner

1. Frontend kaller `/api/stasjoner?lat=&lon=`
2. Backend sjekker om det finnes ferske stasjoner (< 24t) i SQLite for området
3. Hvis ikke: henter fra Overpass API og lagrer i SQLite (`osm_id` som unik nøkkel)
4. Returnerer stasjoner med siste pris, sortert etter avstand

### Database

```sql
stasjoner   -- navn, kjede, koordinater, osm_id (UNIQUE)
priser      -- stasjon_id, bensin, diesel, tidspunkt (historikk)
brukere     -- brukernavn, passord_hash, er_admin, opprettet
invitasjoner -- token (UUID), opprettet, utloper, brukt
visninger   -- ip, device_id, user_agent, ts (statistikk)
```

Priser lagres som historikk – siste pris hentes med `MAX(id) GROUP BY stasjon_id`.

Passord hashes med `werkzeug.security` (pbkdf2:sha256). Sesjoner via signerte Flask-cookies (`SECRET_KEY`).

### iOS-spesifikke hensyn

- `tap: false` i Leaflet-config forhindrer at Leaflet's touch-handler blokkerer native button-klikk
- `overflow-y: auto` kun på indre scroll-container, ikke på `position: fixed`-element (kjent iOS Safari-bug)
- `touch-action: manipulation` på alle knapper eliminerer 300 ms tap-forsinkelse
- `visibility: hidden` på backdrop fremfor kun `pointer-events: none` for robust hit-testing

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

Krever SSH-tilgang til `kjetil@<pi-ip>` og Docker på Pi-en. Cloudflare Tunnel kjøres separat på Pi.

### Miljøvariabler

| Variabel | Standard | Beskrivelse |
|----------|----------|-------------|
| `PORT` | `7342` | HTTP-port |
| `DB_PATH` | `./drivstoff.db` | Sti til SQLite-database |
| `STATS_KEY` | `salo` | Nøkkel for `/oversikt` |
| `SECRET_KEY` | — | Flask session-nøkkel – **sett en sterk verdi i prod** |

> **Produksjon:** Sett `SECRET_KEY` til en lang tilfeldig streng, f.eks. `python3 -c "import secrets; print(secrets.token_hex(32))"`. Uten denne vil alle sesjoner ugyldiggjøres ved omstart.
