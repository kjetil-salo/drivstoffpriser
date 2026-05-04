---
name: kopier-db
description: Kopier databasen mellom prod og staging på Raspberry Pi — bruker sqlite3.backup() for sikker WAL-kopi
allowed-tools: Bash, Write
---

Kopier SQLite-databasen mellom miljøer på Pi.

## Infrastruktur

- Pi SSH: `kjetil@100.76.35.106`
- Prod-container: `drivstoffpriser-drivstoffpriser-1`
- Staging-container: `drivstoffpriser-staging-drivstoffpriser-staging-1`
- DB-sti i begge containere: `/app/data/drivstoff.db`

Argument: $ARGUMENTS (tomt = spør brukeren)

## Fremgangsmåte

### Steg 1: Finn retning

Hvis $ARGUMENTS er tomt, spør: "Hvilken vei? (prod→staging / staging→prod)"

Vanligste er **prod→staging** (for å teste med ekte data).

**prod→staging** er ufarlig.  
**staging→prod** er destruktivt og skal behandles som en høyrisiko-operasjon.

Hvis retningen er **staging→prod**, skal du STOPPE og vise denne advarselen først:

```text
ADVARSEL: DU ER I FERD MED Å OVERSTYRE PROD-DATABASEN.

Kilde: staging
Mål: prod

DETTE KAN IKKE ANGRES.
DETTE KAN ERSTATTE GODE PROD-DATA MED GAMLE, FEILAKTIGE ELLER UTESTEDE DATA.

Fortsett kun hvis du bevisst skal gjenopprette prod fra en annen kilde.
```

Krev deretter en eksplisitt bekreftelse fra brukeren i klartekst.
Godta ikke vage svar som "ja", "ok", "kjør" eller "go".
Brukeren må skrive nøyaktig:

```text
JA, KOPIER STAGING TIL PROD
```

Hvis brukeren ikke skriver dette nøyaktig, skal operasjonen avbrytes.

### Steg 2: Sett variabler

```
SRC = prod-container eller staging-container
DST = den andre
```

### Steg 3: Kjør kopieringen

Bruk dette mønsteret (aldri `cp`/`rsync` direkte på DB-filer — WAL-modus krever sqlite3.backup()):

**Lag backup-script lokalt og scp til Pi:**

```python
# /tmp/db_backup.py
import sqlite3
src = sqlite3.connect('/app/data/drivstoff.db')
dst = sqlite3.connect('/tmp/db_backup.db')
src.backup(dst)
dst.close()
src.close()
print('Backup OK')
```

```python
# /tmp/db_restore.py
import sqlite3
src = sqlite3.connect('/tmp/db_backup.db')
dst = sqlite3.connect('/app/data/drivstoff.db')
src.backup(dst)
dst.close()
src.close()
print('Restore OK')
```

**Kjør sekvensen via SSH:**

```bash
ssh kjetil@100.76.35.106 "
  SRC=<kilde-container>
  DST=<mål-container>
  sudo docker cp /tmp/db_backup.py \$SRC:/tmp/db_backup.py
  sudo docker exec \$SRC python3 /tmp/db_backup.py
  sudo docker cp \$SRC:/tmp/db_backup.db /tmp/db_backup.db
  sudo docker cp /tmp/db_backup.db \$DST:/tmp/db_backup.db
  sudo docker cp /tmp/db_restore.py \$DST:/tmp/db_restore.py
  sudo docker exec \$DST python3 /tmp/db_restore.py
"
```

### Steg 4: Verifiser

Bekreft at destinasjons-containeren fortsatt kjører:

```bash
ssh kjetil@100.76.35.106 "sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep drivstoff"
```

Gi brukeren riktig test-URL:
- Staging: http://raspberrypi:3004
- Prod: https://drivstoffprisene.no

## Viktig

- Aldri bruk `cp`, `rsync` eller `shutil.move` direkte på SQLite-filer i WAL-modus — gir korrupt kopi
- Aldri kjør inline `python3 -c` over SSH — quoting hell; bruk alltid script-filer via scp+docker cp
- Docker-volum krever `sudo` på Pi
- `prod→staging` er standard trygg retning for testing
- `staging→prod` krever eksplisitt brukerbekreftelse med teksten `JA, KOPIER STAGING TIL PROD`
- Ved tvil om retning: stopp og spør på nytt før du gjør noe
