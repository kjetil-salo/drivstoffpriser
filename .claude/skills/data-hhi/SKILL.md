---
name: hhi
description: Beregn fersk HHI-konsentrasjonsindeks for bidragsytere på drivstoffprisene.no
allowed-tools: Bash
---

Beregn og presenter fersk Herfindahl-Hirschman Index (HHI) for bidragsdiversitet på drivstoffprisene.no.

## Steg 1: Les historikk

Les `~/analyse-drivstoff/daglig-statistikk.md` med Read-verktøyet for å hente tidligere HHI-verdier til trendsammenligning.

## Steg 2: Skriv og kjør script

Skriv følgende til `/tmp/hhi.py` med Bash (cat heredoc), kopier til Pi og kjør:

```python
import sqlite3
from datetime import date

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)

# 7 og 30 dagers HHI
for periode, dager in [('Siste 7 dager', 7), ('Siste 30 dager', 30)]:
    rows = conn.execute(f"""
        SELECT bruker_id, COUNT(*) as antall
        FROM priser
        WHERE bruker_id IS NOT NULL
          AND tidspunkt >= datetime('now', '-{dager} days')
        GROUP BY bruker_id
    """).fetchall()

    total = sum(r[1] for r in rows)
    if total == 0:
        continue
    hhi = sum((r[1] / total * 100) ** 2 for r in rows)
    rows_sorted = sorted(rows, key=lambda x: x[1], reverse=True)

    print(f"\n=== {periode} ===")
    print(f"Unike bidragsytere: {len(rows)}")
    print(f"Totale bidrag:      {total}")
    print(f"HHI:                {hhi:.0f}  (< 1500 spredt, > 2500 konsentrert)")
    print(f"\nTopp 10 bidragsytere:")
    for bid, ant in rows_sorted[:10]:
        print(f"  bruker {bid:>6}: {ant:>5} ({ant/total*100:.1f}%)")

# Dag-for-dag siste 14 dager
print("\n=== Dag for dag (siste 14 dager) ===")
rows = conn.execute("""
    SELECT date(tidspunkt) as dag, bruker_id, COUNT(*) as antall
    FROM priser
    WHERE tidspunkt >= datetime('now', '-14 days')
      AND bruker_id IS NOT NULL
    GROUP BY dag, bruker_id
""").fetchall()

from collections import defaultdict
dag_data = defaultdict(list)
for dag, bid, ant in rows:
    dag_data[dag].append((bid, ant))

for dag in sorted(dag_data.keys()):
    bidrag = dag_data[dag]
    total = sum(b[1] for b in bidrag)
    hhi = sum((b[1]/total*100)**2 for b in bidrag)
    print(f"  {dag}  bidragsytere: {len(bidrag):>4}  bidrag: {total:>5}  HHI: {hhi:>5.0f}")

# Aktivitet per dag eks. Kjetil
print("\n=== Aktivitet per dag eks. Kjetil (siste 14 dager) ===")
rows2 = conn.execute("""
    SELECT date(tidspunkt) as dag,
           COUNT(*) as priser,
           COUNT(DISTINCT stasjon_id) as stasjoner,
           COUNT(DISTINCT bruker_id) as brukere
    FROM priser
    WHERE tidspunkt >= datetime('now', '-14 days')
      AND bruker_id NOT IN (5, 2422, 3998)
    GROUP BY dag
    ORDER BY dag DESC
""").fetchall()
print("Dato          Priser  Stasjoner  Brukere")
for dag, priser, stasjoner, brukere in rows2:
    print(f"{dag}   {priser:>6}   {stasjoner:>8}   {brukere:>6}")

conn.close()
```

Kjør med:
```bash
scp /tmp/hhi.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/hhi.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/hhi.py"
```

## Steg 3: Presenter resultatet

Formater resultatet pent i markdown med:
- HHI-verdien fremhevet, med tolkning (spredt / moderat / konsentrert)
- Trendlinje fra historikk i `daglig-statistikk.md` + dagens verdier
- Kort kommentar om trend og hva topp-brukerne representerer

## Steg 4: Oppdater historikkfilen og minnet

Oppdater `~/analyse-drivstoff/daglig-statistikk.md` med dagens nye rader i begge tabeller (HHI dag-for-dag og aktivitet per dag). Erstatt eksisterende rader for samme dato hvis de finnes (dagens tall kan være ufullstendige tidligere på dagen).

Oppdater også minnet (`project_bidragsdiversitet.md`) med nye nøkkeltall og dato.
