---
name: anonyme-priser
description: Sjekk prisinnlegginger fra anonyme brukere (system:anonym) i prod-databasen på Raspberry Pi, med volum, siste innlegginger, toppstasjoner og enkle avvikssignaler
allowed-tools: Bash, Write
---

Undersøk prisinnlegginger fra anonyme brukere i **prod**.

Dette er en **read-only** skill. Den skal brukes for å inspisere hva `system:anonym` har lagt inn etter at anonym innlegging ble åpnet.

## Standard

- Periode: siste 7 dager
- Vis siste 50 anonyme prisrader

Hvis `$ARGUMENTS` inneholder ett heltall, bruk det som antall dager.  
Eksempel: `14` betyr siste 14 dager.

## Viktig

- Bruk alltid prod-containeren: `drivstoffpriser-drivstoffpriser-1`
- DB-sti: `/app/data/drivstoff.db`
- Ikke gjør `UPDATE`, `DELETE` eller `INSERT`
- Ikke bruk inline `python3 -c` over SSH; bruk script via `scp` + `docker cp`

## Steg 1: Skriv script

Skriv følgende til `/tmp/anonyme_priser.py` og sett `DAGER` ut fra `$ARGUMENTS` (standard 7):

```python
import sqlite3
from datetime import datetime

DAGER = 7
ANONYM_BRUKERNAVN = "system:anonym"

conn = sqlite3.connect("/app/data/drivstoff.db")
conn.row_factory = sqlite3.Row

anonym = conn.execute(
    "SELECT id, brukernavn FROM brukere WHERE brukernavn = ?",
    (ANONYM_BRUKERNAVN,),
).fetchone()

print("=" * 80)
print("ANONYME PRISINNLEGGINGER")
print(f"Generert: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Periode: siste {DAGER} dager")
print("=" * 80)

if not anonym:
    print("\nIngen bruker med brukernavn system:anonym funnet.")
    conn.close()
    raise SystemExit(0)

anonym_id = anonym["id"]
print(f"\nAnonym bruker_id: {anonym_id}\n")

oversikt = conn.execute(
    """
    SELECT COUNT(*) AS antall,
           COUNT(DISTINCT p.stasjon_id) AS unike_stasjoner,
           MIN(p.tidspunkt) AS forste,
           MAX(p.tidspunkt) AS siste
    FROM priser p
    WHERE p.bruker_id = ?
      AND p.tidspunkt >= datetime('now', ?)
    """,
    (anonym_id, f"-{DAGER} days"),
).fetchone()

print("## Oversikt")
print(f"Prisrader: {oversikt['antall']}")
print(f"Unike stasjoner: {oversikt['unike_stasjoner']}")
print(f"Første i periode: {oversikt['forste'] or '-'}")
print(f"Siste i periode: {oversikt['siste'] or '-'}")

per_dag = conn.execute(
    """
    SELECT DATE(p.tidspunkt) AS dag,
           COUNT(*) AS antall,
           COUNT(DISTINCT p.stasjon_id) AS stasjoner
    FROM priser p
    WHERE p.bruker_id = ?
      AND p.tidspunkt >= datetime('now', ?)
    GROUP BY DATE(p.tidspunkt)
    ORDER BY dag DESC
    """,
    (anonym_id, f"-{DAGER} days"),
).fetchall()

print("\n## Per dag")
for rad in per_dag:
    print(f"{rad['dag']} | rader={rad['antall']} | stasjoner={rad['stasjoner']}")

top_stasjoner = conn.execute(
    """
    SELECT s.id, s.navn, IFNULL(s.kjede, '') AS kjede,
           COUNT(*) AS antall
    FROM priser p
    JOIN stasjoner s ON s.id = p.stasjon_id
    WHERE p.bruker_id = ?
      AND p.tidspunkt >= datetime('now', ?)
    GROUP BY s.id, s.navn, s.kjede
    ORDER BY antall DESC, s.navn
    LIMIT 15
    """,
    (anonym_id, f"-{DAGER} days"),
).fetchall()

print("\n## Toppstasjoner")
for rad in top_stasjoner:
    vis = rad["navn"] + (f" ({rad['kjede']})" if rad["kjede"] else "")
    print(f"{rad['antall']:>3} | {rad['id']} | {vis}")

siste = conn.execute(
    """
    SELECT p.id, p.tidspunkt, p.stasjon_id, s.navn, IFNULL(s.kjede, '') AS kjede,
           p.bensin, p.bensin98, p.diesel, p.diesel_avgiftsfri, IFNULL(p.kilde, '') AS kilde
    FROM priser p
    JOIN stasjoner s ON s.id = p.stasjon_id
    WHERE p.bruker_id = ?
      AND p.tidspunkt >= datetime('now', ?)
    ORDER BY p.tidspunkt DESC
    LIMIT 50
    """,
    (anonym_id, f"-{DAGER} days"),
).fetchall()

print("\n## Siste 50 rader")
for rad in siste:
    vis = rad["navn"] + (f" ({rad['kjede']})" if rad["kjede"] else "")
    print(
        f"{rad['tidspunkt']} | stasjon={rad['stasjon_id']} | {vis} | "
        f"95={rad['bensin']} | 98={rad['bensin98']} | d={rad['diesel']} | "
        f"avgf={rad['diesel_avgiftsfri']} | kilde={rad['kilde'] or '-'}"
    )

avvik = conn.execute(
    """
    SELECT p.id, p.tidspunkt, s.id AS stasjon_id, s.navn,
           p.bensin, p.bensin98, p.diesel, p.diesel_avgiftsfri,
           (
             SELECT p2.bensin FROM priser p2
             WHERE p2.stasjon_id = p.stasjon_id
               AND p2.tidspunkt < p.tidspunkt
               AND p2.bensin IS NOT NULL
               AND p2.bruker_id != ?
             ORDER BY p2.tidspunkt DESC
             LIMIT 1
           ) AS forrige_bensin,
           (
             SELECT p2.diesel FROM priser p2
             WHERE p2.stasjon_id = p.stasjon_id
               AND p2.tidspunkt < p.tidspunkt
               AND p2.diesel IS NOT NULL
               AND p2.bruker_id != ?
             ORDER BY p2.tidspunkt DESC
             LIMIT 1
           ) AS forrige_diesel
    FROM priser p
    JOIN stasjoner s ON s.id = p.stasjon_id
    WHERE p.bruker_id = ?
      AND p.tidspunkt >= datetime('now', ?)
    ORDER BY p.tidspunkt DESC
    LIMIT 200
    """,
    (anonym_id, anonym_id, anonym_id, f"-{DAGER} days"),
).fetchall()

print("\n## Mulige avvik")
funnet = 0
for rad in avvik:
    meldinger = []
    if rad["bensin"] is not None and rad["forrige_bensin"] is not None:
        diff = round(rad["bensin"] - rad["forrige_bensin"], 2)
        if abs(diff) >= 2.0:
            meldinger.append(f"95 diff {diff:+.2f}")
    if rad["diesel"] is not None and rad["forrige_diesel"] is not None:
        diff = round(rad["diesel"] - rad["forrige_diesel"], 2)
        if abs(diff) >= 2.0:
            meldinger.append(f"diesel diff {diff:+.2f}")
    if meldinger:
        funnet += 1
        print(f"{rad['tidspunkt']} | {rad['stasjon_id']} | {rad['navn']} | " + ", ".join(meldinger))

if not funnet:
    print("Ingen avvik >= 2.00 kr funnet mot forrige ikke-anonyme pris.")

conn.close()
```

## Steg 2: Kopier og kjør

```bash
scp /tmp/anonyme_priser.py kjetil@raspberrypi:/tmp/anonyme_priser.py && \
ssh kjetil@raspberrypi "docker cp /tmp/anonyme_priser.py drivstoffpriser-drivstoffpriser-1:/tmp/anonyme_priser.py && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/anonyme_priser.py"
```

Hvis du bruker et annet SSH-navn enn `raspberrypi` lokalt, bruk Pi-IPen eller samme host-alias som fungerer i miljøet ditt.

## Steg 3: Presenter

Oppsummer kort:

- hvor mange anonyme prisrader som finnes i perioden
- hvor mange unike stasjoner de dekker
- hvilke stasjoner som går igjen mest
- om det finnes mistenkelige hopp mot forrige ikke-anonyme pris
- om `kilde` ser konsistent ut eller mangler ofte

Hvis brukeren vil dypere:

- vis rå-radene for én bestemt stasjon
- sammenlign anonym aktivitet siste 24t vs siste 7 dager
- pek på konkrete prisrader som bør modereres manuelt

Oppgave: $ARGUMENTS
