# Drivstoffappen API — analyse av mobiltrafikk

Analysert med mitmproxy 12.2.3 på Mac, iPhone som klient (iOS 26.4.2).
Dato: 2026-05-19.

## Metode

- mitmweb kjørende på Mac, port 8082
- iPhone WiFi-proxy satt til Mac-IP:8082
- mitmproxy CA-sertifikat installert på iPhone (Innstillinger → Generelt → VPN og enhetsstyring)
- Appen lukket helt (sveip fra app-switcher), deretter startet på nytt

## Startup-sekvens

Kall i rekkefølge når appen åpnes fra scratch:

| # | Metode | Endepunkt |
|---|--------|-----------|
| 1 | GET | `/api/v3/configurations` |
| 2 | GET | `/api/v3/users/{uid}` |
| 3 | GET | `/api/v3/users/{uid}/temporary-premium-progress` |
| 4 | GET | `/api/v3/discounts` |
| 5 | GET | `/api/v3/countries` |
| 6 | GET | `/api/v3/translations` |
| 7 | GET | `/api/v3/brands` |
| 8 | GET | `/api/v3/station-types` |
| 9 | GET | `/api/v3/fuel-kinds` |
| 10 | GET | `/api/v3/fuel-types` |
| 11 | GET | `/api/v3/user-levels` |
| 12 | GET | `/api/v3/stations?includeDeleted=1&minUpdatedAt=...` ← hoveddatasynk |
| 13 | PATCH | `/api/v3/users/{uid}` ← oppdaterer device-info |
| 14 | GET | `/api/v3/stations?includeDeleted=1&minUpdatedAt=...` ← liten delta-synk |
| 15 | GET | `/api/v3/app-configs?deleted=0&key=station_list_home_banner_subscribed&...&namespace=banners` |
| 16 | GET | `/api/v3/brand-images/{hash}.png` |

Merk: en allerede åpen app sender sporadisk `GET /api/v3/users/{uid}` som bakgrunnsoppdatering — dette er ikke del av startup-sekvensen.

## Request-headers (alle API-kall)

```
content-type: application/json
accept: */*
authorization: Bearer <Firebase JWT — roterer>
x-requester-id: 47C44FEA-48B3-4054-9282-D91DB913AD8C
priority: u=3, i
accept-language: nb-NO;q=1.0, nn-NO;q=0.9
x-api-key: 0afa1c404183c35622f380f78f2e5eec
accept-encoding: br;q=1.0, gzip;q=0.9, deflate;q=0.8
user-agent: Drivstoffappen/3.5.4 (com.raskebiler.drivstoff.appen; build:689; iOS 26.4.2) Alamofire/5.12.0
x-client-id: com.drivstoff.appen.ios
```

`x-api-key` er statisk og lik for alle kall.  
`authorization` er en Firebase JWT som utstedes ved innlogging og roterer.  
`x-requester-id` er en fast UUID per enhet.

## Sammenligning: cron-jobb vs ekte app

| Header / egenskap | Ekte app | `drivstoffappen_sync.py` |
|---|---|---|
| `user-agent` | `Drivstoffappen/3.5.4 (...) Alamofire/5.12.0` | ✓ lagt til 2026-05-19 |
| `x-client-id` | `com.drivstoff.appen.ios` | ✓ rettet 2026-05-19 (var `com.raskebiler.drivstoff.appen.ios`) |
| `x-requester-id` | device UUID | ✓ lagt til 2026-05-19 |
| `accept-language` | `nb-NO;q=1.0, nn-NO;q=0.9` | ✓ lagt til 2026-05-19 |
| `x-api-key` | statisk: `0afa1c404183c35622f380f78f2e5eec` | utledet fra v1-session-token |
| `authorization` | `Bearer <Firebase JWT>` | mangler (ikke nødvendig for v1) |
| API-versjon | `/api/v3/stations` | `/api/v1/stations` |

Cron-jobben bruker fortsatt v1-APIet med utledet nøkkel. Dette fungerer og serveren aksepterer det, men skiller seg fra ekte app-trafikk. Vurderes oppgradert til v3 ved behov.
