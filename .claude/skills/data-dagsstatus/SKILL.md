---
name: dagsstatus
description: Vis prisoppdateringer i dag vs i går (time for time, uten Kjetils egne oppdateringer) — drivstoffprisene.no
allowed-tools: Bash
---

Hent og vis dagens prisoppdateringsstatistikk fra drivstoffprisene.no, sammenlignet med i går på samme tidspunkt. Ekskluder alltid Kjetils egne kontoer (id 5, 2422 og 3998).

## Steg 1: Skriv script

Skriv følgende til `/tmp/dagsstatus.py`:

```python
import sqlite3
from datetime import datetime

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)

rows = conn.execute("""
    SELECT
        date(tidspunkt) AS dato,
        COUNT(*) AS antall,
        COUNT(DISTINCT stasjon_id) AS stasjoner,
        COUNT(DISTINCT bruker_id) AS bidragsytere
    FROM priser
    WHERE bruker_id NOT IN (5, 2422, 3998)
    AND (
        (date(tidspunkt) = date('now') AND time(tidspunkt) <= time('now'))
        OR
        (date(tidspunkt) = date('now', '-1 day') AND time(tidspunkt) <= time('now'))
    )
    GROUP BY dato
    ORDER BY dato DESC
""").fetchall()

print(f"Uten Kjetils oppdateringer, t.o.m. {datetime.now().strftime('%H:%M')} UTC:\n")
print(f"{'Dato':<12} {'Oppdateringer':>14} {'Stasjoner':>10} {'Bidragsytere':>13}")
print("-" * 52)
for r in rows:
    print(f"{r[0]:<12} {r[1]:>14} {r[2]:>10} {r[3]:>13}")

print("\nPer time:")
timer = conn.execute("""
    SELECT date(tidspunkt) AS dato, strftime('%H', tidspunkt) AS time, COUNT(*) AS antall
    FROM priser
    WHERE bruker_id NOT IN (5, 2422, 3998)
    AND (
        (date(tidspunkt) = date('now') AND time(tidspunkt) <= time('now'))
        OR
        (date(tidspunkt) = date('now', '-1 day') AND time(tidspunkt) <= time('now'))
    )
    GROUP BY dato, time
    ORDER BY time, dato
""").fetchall()

by_time = {}
for dato, t, antall in timer:
    by_time.setdefault(t, {})[dato] = antall
dates = sorted(set(r[0] for r in timer))

print(f"\n{'Time':<6}", end="")
for d in dates:
    print(f"  {d:>12}", end="")
print()
print("-" * (6 + 14 * len(dates)))
for t in sorted(by_time):
    print(f"  {t}:00", end="")
    for d in dates:
        print(f"  {by_time[t].get(d, 0):>12}", end="")
    print()

totals = {}
for dato, t, antall in timer:
    totals[dato] = totals.get(dato, 0) + antall
print(f"\n{'TOTALT':<6}", end="")
for d in dates:
    print(f"  {totals.get(d,0):>12}", end="")
print()
conn.close()
```

## Steg 2: Kopier og kjør

```bash
scp /tmp/dagsstatus.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/dagsstatus.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/dagsstatus.py"
```

## Steg 3: Presenter resultatet

Formater tabellen pent i markdown med to kolonner (i går / i dag), og legg til en kort kommentar om trenden (% endring, hva som skiller dagene).

Husk: Pi kjører UTC, som er 2 timer bak norsk sommertid (CEST).
