---
name: data-partner1-status
description: Vis hvilke stasjoner som er med i partner1-sync (Drivstoffappen), og sjekk fersk sync-statistikk fra partner_sync.db på Pi.
allowed-tools: Bash, Read, Write
---

Vis status for partner1-sync — hvilke stasjoner som er mappet og hvor mye de bidrar.

## Hva er partner1-sync?

`partner1` er en maskinbruker (bruker_id=4677) som automatisk henter priser fra **Drivstoffappen** (`api.drivstoffappen.no`) og lagrer dem i vår DB. Kjøres av cron: `0 5-23 * * *` (hver time mellom kl. 5–23).

Filen med mapping: `tools/drivstoffappen_sync.py`, dict `STASJON_MAPPING`.

## Stasjonsliste (fra koden)

Disse stasjonene er mappet per siste oppdatering:

| Vår ID | Drivstoffappen-ID | Stasjon |
|--------|-------------------|---------|
| 1      | 433               | Esso Frekhaug |
| 2      | 2190              | Circle K Automat Knarvik |
| 3      | 88                | Esso Nyborg |
| 4      | 687               | St1 Haukås Nyborg |
| 11     | 28414             | Haltbakk Express Ostereidet |
| 16     | 1278              | St1 Marikollen |
| 18     | 1324              | St1 Lone |
| 19     | 25153             | Uno-X Tertnes |
| 26     | 4064              | Oljeleverandøren Hylkje |
| 30     | 76                | Circle K Ulset |
| 32     | 643               | Circle K Haukås |
| 33     | 644               | Circle K Helleveien |
| 35     | 1094              | Uno-X 7-Eleven Øyrane torg |
| 36     | 2093              | St1 Nygård |
| 42     | 49                | Uno-X Gullgruven (Åsane) |
| 43     | 121               | Uno-X 7-Eleven Nyborg |
| 45     | 1222              | St1 Isdalstø |
| 1882   | 1351              | St1 Randabergveien |
| 1887   | 221               | Esso Tjensvollkrysset |
| 5690   | 468               | Esso Hundvåg |
| 12     | 791               | Circle K Viken |

**Oppdater alltid denne tabellen** hvis du bruker `/ops-partner-stasjon` og legger til nye stasjoner.

## Hent live-statistikk fra Pi

**Bruk alltid hoved-DB (`drivstoff.db`) for statistikk** — `partner_sync.db` mangler de første dagene og er ufullstendig.

Bruk scp + docker cp-mønsteret:

```bash
cat > /tmp/partner_status.py << 'EOF'
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("/app/data/drivstoff.db")
conn.row_factory = sqlite3.Row

# Oppstart og dagsoversikt
print("=== Dagsoversikt ===")
dager = conn.execute("""
    SELECT DATE(tidspunkt) as dato, COUNT(*) as antall
    FROM priser WHERE bruker_id = 4677
    GROUP BY dato ORDER BY dato
""").fetchall()
for d in dager:
    print(f"  {d['dato']}: {d['antall']} priser")

first = conn.execute("SELECT MIN(tidspunkt) FROM priser WHERE bruker_id=4677").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM priser WHERE bruker_id=4677").fetchone()[0]
print(f"\nFørste innlegging: {first}")
print(f"Totalt skrevet:    {total}")

# Siste 7 dager per stasjon
print("\n=== Per stasjon siste 7 dager ===")
sju_dager_siden = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
rows = conn.execute("""
    SELECT stasjon_id,
           SUM(CASE WHEN bensin IS NOT NULL THEN 1 ELSE 0 END) AS bensin_total,
           SUM(CASE WHEN diesel IS NOT NULL THEN 1 ELSE 0 END) AS diesel_total,
           MAX(tidspunkt) AS siste_synk
    FROM priser
    WHERE bruker_id = 4677 AND tidspunkt >= ?
    GROUP BY stasjon_id
    ORDER BY (bensin_total + diesel_total) DESC
""", (sju_dager_siden,)).fetchall()

print(f"{'Stasjon':>8}  {'Bensin':>7}  {'Diesel':>7}  {'Siste synk'}")
print("-" * 55)
for r in rows:
    print(f"{r['stasjon_id']:>8}  {r['bensin_total']:>7}  {r['diesel_total']:>7}  {r['siste_synk']}")

total_b = sum(r['bensin_total'] for r in rows)
total_d = sum(r['diesel_total'] for r in rows)
print("-" * 55)
print(f"{'TOTALT':>8}  {total_b:>7}  {total_d:>7}")
conn.close()
EOF
scp /tmp/partner_status.py raspberrypi:/tmp/partner_status.py
ssh raspberrypi "docker cp /tmp/partner_status.py drivstoffpriser-drivstoffpriser-1:/tmp/partner_status.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/partner_status.py"
```

## Koble stasjon-ID til navn

Bruk tabellen over for å slå opp navn på stasjon-ID-ene i utdataene.

## Hva er normalt?

- Mange stasjoner gir 0 bidrag i perioder — Drivstoffappen kan ha like ferske eller eldre priser enn vi.
- En synk-runde skrives kun hvis Drivstoffappens pris er nyere enn vår siste (og innenfor 14–37 kr/l).
- Stasjonene er geografisk konsentrert rundt Bergensområdet + Stavanger (Randabergveien, Tjensvollkrysset, Hundvåg).

## Hvis du vil sjekke én spesifikk stasjon

```python
stasjon_id = 35  # bytt ut

conn = sqlite3.connect("/app/data/drivstoff.db")
rows = conn.execute("""
    SELECT tidspunkt, bensin, diesel
    FROM priser
    WHERE bruker_id = 4677 AND stasjon_id = ?
    ORDER BY tidspunkt DESC
    LIMIT 20
""", (stasjon_id,)).fetchall()
for r in rows:
    print(r)
conn.close()
```

Oppgave: $ARGUMENTS
