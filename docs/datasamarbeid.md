# Datasamarbeid — Drivstoffpriser

## Bakgrunn

Drivstoffpriser-appen samler inn priser via brukerbidrag. Andre utviklere bygger lignende apper. Istedenfor å konkurrere om data, kan vi samarbeide: **del prisdata, behold egne apper.**

## Konsept

Federert datadeling via API. Hver app beholder egen database og eget brukergrensesnitt. Prisdata synkroniseres mellom partene via et enkelt, avtalt API.

```
┌──────────────┐         push/pull         ┌──────────────┐
│   App A      │ ◄──────────────────────►  │   App B      │
│   (vår app)  │    POST/GET /api/sync     │   (partner)  │
│   Egen DB    │                           │   Egen DB    │
└──────────────┘                           └──────────────┘
```

## Prinsipper

1. **Symmetrisk avtale** — begge eksponerer samme API med samme kontrakt
2. **Kun prisdata** — ingen brukerdata, kontoer eller beriket metadata deles
3. **Attribusjon** — hvert datapunkt tagges med `kilde` slik at opprinnelsen er sporbar
4. **Kvotebasert rettferdighet** — logg ratio gitt/mottatt, pause ved skjevhet
5. **Uavhengighet** — hver app fungerer fullt ut uten synk-partneren

## API-kontrakt

### Autentisering

Hver partner får en unik API-nøkkel. Sendes som header:

```
X-Sync-Key: <nøkkel>
```

### Push priser

```
POST /api/sync/priser

Body:
{
  "priser": [
    {
      "stasjon_osm_id": "node/12345678",
      "drivstoff": "bensin95",
      "pris": 21.35,
      "tidspunkt": "2026-03-24T14:30:00Z",
      "kilde": "app-b"
    }
  ]
}

Respons:
{ "ok": true, "mottatt": 12, "avvist": 1 }
```

### Pull nye priser

```
GET /api/sync/priser?siden=2026-03-24T12:00:00Z&limit=100

Respons:
{
  "priser": [ ... ],
  "neste": "2026-03-24T14:30:00Z"
}
```

### Dataformat

| Felt | Type | Beskrivelse |
|------|------|-------------|
| `stasjon_osm_id` | string | OpenStreetMap node-ID (felles referanse) |
| `drivstoff` | string | `bensin95`, `bensin98`, `diesel` |
| `pris` | float | Pris i kr/liter |
| `tidspunkt` | string | ISO 8601 UTC |
| `kilde` | string | Identifikator for avsender-appen |

OSM-ID brukes som felles stasjonsreferanse. Begge apper henter stasjoner fra OSM, så dette er en naturlig nøkkel.

## Beskyttelsesmekanismer

### Rate limiting
- Maks 60 requests/minutt per partner
- Maks 1000 priser per push

### Rettferdighetskvote
- Ratio gitt/mottatt logges per uke
- Ved skjevhet over 80/20 i mer enn 2 uker: automatisk pause med varsel
- Dashboard for begge parter med ukentlig statistikk

### Kill switch
- Hver part kan revoke API-nøkkelen umiddelbart
- Synk stoppes uten å påvirke egen app

### Datakvalitet
- Priser utenfor rimelig intervall (f.eks. < 10 kr eller > 40 kr) avvises
- Duplikater (samme stasjon + drivstoff innen 5 min) ignoreres
- Priser eldre enn 48 timer avvises

## Utrullingsstrategi

### Fase 1: Pilot (2-4 uker)
- Aktiver synk for én region (f.eks. Oslo-området)
- Begge parter implementerer push + pull
- Mål ratio og datakvalitet

### Fase 2: Evaluering
- Gjennomgå ratio og brukeropplevelse
- Juster kvoteregler om nødvendig
- Avklar eventuelle edge cases

### Fase 3: Full utrulling
- Aktiver for hele Norge
- Utvid til flere partnere om relevant

## DB-endringer (vår side)

Ny tabell for synk-logg:

```sql
CREATE TABLE sync_logg (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner TEXT NOT NULL,
    retning TEXT NOT NULL,  -- 'inn' eller 'ut'
    antall INTEGER NOT NULL,
    tidspunkt TEXT DEFAULT (datetime('now'))
);
```

Ny kolonne på priser-tabellen:

```sql
ALTER TABLE priser ADD COLUMN kilde TEXT;  -- NULL = egen bruker
```

## Hva som IKKE deles

- Brukerkontoer eller innloggingsdata
- Enhets-IDer eller IP-adresser
- Visningsstatistikk
- Bruker-opprettede stasjoner (kun OSM-stasjoner synkes)
- Intern metadata (godkjenningsstatus, admin-notater)
