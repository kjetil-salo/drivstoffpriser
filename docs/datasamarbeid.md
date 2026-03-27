# Datasamarbeid — Drivstoffpriser

## Bakgrunn

Drivstoffpriser-appen samler inn priser via brukerbidrag. Andre utviklere bygger lignende apper. Istedenfor å konkurrere om data, kan vi samarbeide: **del prisdata, behold egne apper.**

## Konsept

Federert datadeling via API. Hver app beholder egen database og eget brukergrensesnitt. Prisdata deles via et enkelt API.

```
┌──────────────┐         GET /api/share       ┌──────────────┐
│   App A      │ ◄────────────────────────────  │   Partner    │
│   (vår app)  │    X-API-Key: <nøkkel>        │              │
│   Egen DB    │                               │   Egen DB    │
└──────────────┘                               └──────────────┘
```

## Prinsipper

1. **Kun prisdata** — ingen brukerdata, kontoer eller beriket metadata deles
2. **Uavhengighet** — hver app fungerer fullt ut uten partneren
3. **Nøkkel per partner** — hver partner har en unik API-nøkkel som kan deaktiveres

## API

### Autentisering

Hver partner får en unik API-nøkkel. Sendes som header:

```
X-API-Key: <nøkkel>
```

Nøkler lagres i `api_nøkler`-tabellen og kan deaktiveres med `aktiv = 0`.

### Hent priser

```
GET /api/share/prices?from=<ISO 8601>&to=<ISO 8601>
```

**Parametere:**

| Parameter | Påkrevd | Beskrivelse |
|-----------|---------|-------------|
| `from` | Nei | Starttidspunkt (ISO 8601). Default: 24 timer siden |
| `to` | Nei | Sluttidspunkt (ISO 8601). Default: nå |

**Begrensninger:**
- Maks 24 timers spenn mellom `from` og `to`
- `to` må være etter `from`

**Eksempel:**

```bash
curl -H "X-API-Key: <nøkkel>" \
  "https://pris.ksalo.no/api/share/prices?from=2026-03-26T10:00:00&to=2026-03-26T18:00:00"
```

**Respons (200):**

```json
{
  "prices": [
    {
      "station_id": 12345,
      "name": "Circle K Trondheim",
      "petrol": 22.44,
      "diesel": 24.84,
      "petrol98": null,
      "updated": "2026-03-26 15:57:57"
    }
  ]
}
```

**Feilresponser:**

| Kode | Årsak |
|------|-------|
| 400 | Ugyldig datoformat, `to` før `from`, eller spenn > 24 timer |
| 403 | Ugyldig eller deaktivert API-nøkkel |

## Logging

Alle API-kall logges i `api_logg`-tabellen med partnernavn, antall returnerte priser og tidspunkt.

## DB-tabeller

### api_nøkler

```sql
CREATE TABLE api_nøkler (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    partner   TEXT NOT NULL,
    nøkkel    TEXT NOT NULL UNIQUE,
    aktiv     INTEGER NOT NULL DEFAULT 1,
    opprettet TEXT DEFAULT (datetime('now'))
);
```

### api_logg

```sql
CREATE TABLE api_logg (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    partner    TEXT NOT NULL,
    antall     INTEGER NOT NULL,
    tidspunkt  TEXT DEFAULT (datetime('now'))
);
```

## Administrasjon

Legge til ny partner:

```sql
INSERT INTO api_nøkler (partner, nøkkel) VALUES ('partnernavn', '<uuid>');
```

Deaktivere partner:

```sql
UPDATE api_nøkler SET aktiv = 0 WHERE partner = 'partnernavn';
```

Se bruksstatistikk:

```sql
SELECT partner, COUNT(*) as kall, SUM(antall) as priser, MAX(tidspunkt) as sist
FROM api_logg GROUP BY partner;
```

## Hva som IKKE deles

- Brukerkontoer eller innloggingsdata
- Enhets-IDer eller IP-adresser
- Visningsstatistikk
- Intern metadata (godkjenningsstatus, admin-notater)
