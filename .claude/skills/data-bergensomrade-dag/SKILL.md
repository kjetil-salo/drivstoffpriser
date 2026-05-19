---
name: bergensomrade-dag
description: Sjekk én bestemt dag i Bergen med nabokommuner hvor mange andre enn Kjetil som la inn priser, hvor mange oppdateringer det var, hvilke stasjoner som ble truffet, og hvem som bidro
allowed-tools: Bash, Write
---

Undersøk prisinnlegginger for én bestemt dag i **Bergen + nabokommuner** i **prod**.

Dette er en **read-only** skill.

## Område

Tolk "Bergen med nabokommuner" som:

- `Bergen`
- `Askøy`
- `Øygarden`
- `Alver`
- `Vaksdal`
- `Samnanger`
- `Bjørnafjorden`

## Standard

- Dato: i dag hvis ingen dato oppgis
- Ekskluder Kjetils brukere: `1`, `5`, `2422`, `3998`
- Ekskluder maskinbrukere: `4677` (partner1 = Drivstoffappen-sync, aktiv fra ~2026-05-16)
- `system:anonym` skal telles med, siden det er "andre enn Kjetil"

Hvis `$ARGUMENTS` inneholder en dato på formen `YYYY-MM-DD`, bruk den.  
Eksempel: `2026-04-23`

## Viktig

- Bruk alltid prod-containeren: `drivstoffpriser-drivstoffpriser-1`
- DB-sti: `/app/data/drivstoff.db`
- Ikke gjør `UPDATE`, `DELETE` eller `INSERT`
- Ikke bruk inline `python3 -c` over SSH; bruk script via `scp` + `docker cp`

## Steg 1: Bruk scriptet

Bruk det lokale scriptet:

`/Users/kjetil/git/drivstoffpriser/.claude/skills/data-bergensomrade-dag/scripts/bergensomrade_dag.py`

Scriptet:

- finner alle stasjoner med prisaktivitet den valgte dagen innenfor en Bergen-bounding-box
- reverse-geocoder bare disse kandidatstasjonene
- filtrerer til kommunene over
- teller bidragsytere, oppdateringer og stasjoner
- viser topp bidragsytere og topp stasjoner
- kan skrive JSON med `--json`

## Steg 2: Kopier og kjør

Hvis ingen dato er oppgitt, bruk dagens dato. Kjør med valgt dato:

```bash
scp /Users/kjetil/git/drivstoffpriser/.claude/skills/bergensomrade-dag/scripts/bergensomrade_dag.py kjetil@raspberrypi:/tmp/bergensomrade_dag.py
ssh kjetil@raspberrypi "docker cp /tmp/bergensomrade_dag.py drivstoffpriser-drivstoffpriser-1:/tmp/bergensomrade_dag.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/bergensomrade_dag.py --date YYYY-MM-DD"
```

For JSON:

```bash
scp /Users/kjetil/git/drivstoffpriser/.claude/skills/bergensomrade-dag/scripts/bergensomrade_dag.py kjetil@raspberrypi:/tmp/bergensomrade_dag.py
ssh kjetil@raspberrypi "docker cp /tmp/bergensomrade_dag.py drivstoffpriser-drivstoffpriser-1:/tmp/bergensomrade_dag.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/bergensomrade_dag.py --date YYYY-MM-DD --json"
```

Hvis du bruker et annet SSH-navn enn `raspberrypi` lokalt, bruk Pi-IPen eller samme host-alias som fungerer i miljøet ditt.

## Steg 3: Presenter

Oppsummer kort:

- hvor mange andre enn Kjetil som la inn priser den dagen
- hvor mange oppdateringer de sto for
- hvor mange stasjoner som ble truffet
- hvilke bidragsytere som var mest aktive
- hvilke stasjoner som hadde mest aktivitet

## Tidsserie

En historisk tidsserie ligger i:

`/Users/kjetil/git/drivstoffpriser/.claude/skills/data-bergensomrade-dag/data/tidsserie.csv`

Kolonner: `dato, oppdateringer, bidragsytere, stasjoner`  
Dekker fra 2026-04-14 og fremover. Alle verdier er uten Kjetils kontoer (id 1, 5, 2422, 3998).

**Etter hver kjøring:** sjekk om datoen allerede finnes i CSV-en. Hvis ikke, legg til ny linje. Hvis datoen er **dagens dato**, oppdater alltid raden — dagen er ikke over og tallene kan ha økt siden forrige sjekk. Bruk `--compact`-flagget for å hente tallene. Oppdater filen med Write-verktøyet.

Eksempel på å hente tall for en dato og legge til i CSV:

```bash
scp .../bergensomrade_dag.py kjetil@raspberrypi:/tmp/bergensomrade_dag.py
ssh kjetil@raspberrypi "docker cp /tmp/bergensomrade_dag.py drivstoffpriser-drivstoffpriser-1:/tmp/bergensomrade_dag.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/bergensomrade_dag.py --date YYYY-MM-DD --compact"
# Parse JSON og legg til rad i CSV hvis datoen mangler
```

Hvis brukeren vil dypere:

- bryt ned per kommune
- vis alle stasjoner med aktivitet
- kjør skillen for flere enkeltdager og sammenlign dag for dag
- les tidsserien og lag trend-analyse

Oppgave: $ARGUMENTS
