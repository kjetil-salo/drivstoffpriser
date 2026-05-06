# Infrastruktur — drivstoffprisene.no

## Raspberry Pi 5

Primær produksjonsserver. Kjører alle containere via Docker Compose.

| | |
|--|--|
| Tilgang | Tailscale (`raspberrypi` / `100.76.35.106`) |
| Cloudflare Tunnel | Eksponerer appen uten åpne porter |

### Lagring

| Medium | Montert | Bruk |
|--------|---------|------|
| SD-kort (64 GB) | `/` | OS og statiske konfig-filer |
| Samsung T5 SSD (1 TB) | `/mnt/ssd` | Docker data-root, databaser, logger, backups |

**SD-kortet er tilnærmet read-only i drift.** All skriving fra Docker (databaser, applogger, container-logger, image layers) skjer på SSD.

Øvrige skriveskilder er allerede eliminert:
- Swap: `zram0` (komprimert RAM)
- systemd journal: volatil modus (RAM)
- `/tmp`: tmpfs (RAM)
- `/var/log/`: neglisjerbart volum

#### Docker data-root

Konfigurert i `/etc/docker/daemon.json`:

```json
{"data-root": "/mnt/ssd/docker"}
```

Migrert 2026-05-06 fra `/var/lib/docker` (SD) til `/mnt/ssd/docker` (SSD) med `rsync -aP`.

#### SSD-mappestruktur

```
/mnt/ssd/
├── docker/          # Docker data-root (volumes, images, container-logger)
├── backups/         # Lokale DB-backups (daglig + ukentlig)
├── keycloak-lab/    # Keycloak-nøkler (annet prosjekt)
└── postgres/        # PostgreSQL-data (annet prosjekt)
```

### Docker-containere

| Container | Port | Compose-fil |
|-----------|------|-------------|
| `drivstoffpriser-drivstoffpriser-1` | 3002 | `/home/kjetil/drivstoffpriser/` |
| `drivstoffpriser-staging-drivstoffpriser-staging-1` | 3004 | `/home/kjetil/drivstoffpriser-staging/` |
| `enkel-ao-enkel-ao-1` | 3000 | `/home/kjetil/enkel-ao/` |
| `dagens-funn-dagens-funn-1` | 3001 | `/home/kjetil/dagens-funn/` |
| `enkel-ao-dozzle-1` | — | `/home/kjetil/enkel-ao/` |

### Cron-jobber (root)

```
0 */4 * * *   DB-synk Pi → Fly.io   /home/kjetil/drivstoffpriser/sync-til-fly.sh
0 3   * * *   DB-backup             /home/kjetil/drivstoffpriser/backup.sh
```

Logger skrives til `/tmp/` (tmpfs).

---

## Fly.io — failover

Cold standby for drivstoffprisene.no. Databasen synkes automatisk fra Pi hver 4. time.

| | |
|--|--|
| URL | `drivstoffpriser.fly.dev` |
| App | `drivstoffpriser` |
| DB | Synket kopi av Pi-databasen |

Fly.io-instansen sover mellom synker og forespørsler. Første request etter dvale kan ta noen sekunder.

---

## Cloudflare

- **Tunnel**: eksponerer Pi-appen uten åpne porter i brannmur
- **DNS**: drivstoffprisene.no peker via Cloudflare
- **R2**: ekstern DB-backup (`drivstoffpriser-backup`-bucket, 30 dagers rullering)
