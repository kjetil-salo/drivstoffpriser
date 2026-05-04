---
name: ukessammenligning
description: Sammenlign dagens aktivitet time for time med samme ukedag forrige uke — priser, unike stasjoner, unike brukere — drivstoffprisene.no
allowed-tools: Bash
---

Sammenlign dagens prisoppdateringer på drivstoffprisene.no time for time med samme ukedag for 7 dager siden. Ekskluder alltid Kjetils kontoer (id 5, 2422, 3998) og NULL. Stopp ved nåværende time (ikke fremtidige timer).

Pi kjører UTC — norsk sommertid (CEST) er UTC+2. Juster alltid stopp-tidspunkt til UTC.

## Steg 1: Skriv script til /tmp/ukessammenligning.py

```python
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)

EKSKLUDER = (5, 2422, 3998)

now_utc = datetime.now(timezone.utc)
dato_i_dag = now_utc.strftime('%Y-%m-%d')
dato_forrige = (now_utc - timedelta(days=7)).strftime('%Y-%m-%d')
stopp_time = now_utc.strftime('%H')

ukedager = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']
ukedag = ukedager[now_utc.weekday()]

print(f"Sammenligning: {ukedag} {dato_i_dag} vs {dato_forrige} (t.o.m. {stopp_time}:59 UTC = {int(stopp_time)+2:02d}:59 norsk tid)\n")

def hent_data(dato, stopp):
    rader = conn.execute(f"""
        SELECT strftime('%H', tidspunkt) AS time, stasjon_id, bruker_id
        FROM priser
        WHERE date(tidspunkt) = ?
          AND bruker_id IS NOT NULL
          AND bruker_id NOT IN {EKSKLUDER}
          AND strftime('%H', tidspunkt) <= ?
    """, (dato, stopp)).fetchall()

    time_data = defaultdict(lambda: {'priser': 0, 'stasjoner': set(), 'brukere': set()})
    for t, sid, bid in rader:
        time_data[t]['priser'] += 1
        time_data[t]['stasjoner'].add(sid)
        time_data[t]['brukere'].add(bid)
    return time_data

d1 = hent_data(dato_forrige, stopp_time)
d2 = hent_data(dato_i_dag, stopp_time)

alle_timer = sorted(set(list(d1.keys()) + list(d2.keys())))

# Header
print(f"{'Time':<7}  {'--- ' + dato_forrige + ' ---':^30}  {'--- ' + dato_i_dag + ' ---':^30}")
print(f"{'':7}  {'Priser':>8} {'Stasj.':>8} {'Brukere':>8}  {'Priser':>8} {'Stasj.':>8} {'Brukere':>8}")
print("-" * 72)

tot1 = {'priser': 0, 'stasjoner': set(), 'brukere': set()}
tot2 = {'priser': 0, 'stasjoner': set(), 'brukere': set()}

for t in alle_timer:
    r1 = d1.get(t, {'priser': 0, 'stasjoner': set(), 'brukere': set()})
    r2 = d2.get(t, {'priser': 0, 'stasjoner': set(), 'brukere': set()})
    print(f"  {t}:00  "
          f"{r1['priser']:>8} {len(r1['stasjoner']):>8} {len(r1['brukere']):>8}  "
          f"{r2['priser']:>8} {len(r2['stasjoner']):>8} {len(r2['brukere']):>8}")
    tot1['priser'] += r1['priser']
    tot1['stasjoner'] |= r1['stasjoner']
    tot1['brukere'] |= r1['brukere']
    tot2['priser'] += r2['priser']
    tot2['stasjoner'] |= r2['stasjoner']
    tot2['brukere'] |= r2['brukere']

print("-" * 72)
print(f"  TOTAL  "
      f"{tot1['priser']:>8} {len(tot1['stasjoner']):>8} {len(tot1['brukere']):>8}  "
      f"{tot2['priser']:>8} {len(tot2['stasjoner']):>8} {len(tot2['brukere']):>8}")

# Diff
dp = tot2['priser'] - tot1['priser']
ds = len(tot2['stasjoner']) - len(tot1['stasjoner'])
db = len(tot2['brukere']) - len(tot1['brukere'])
print(f"\n  Endring: priser {dp:+d}, stasjoner {ds:+d}, brukere {db:+d}")
conn.close()
```

## Steg 2: Kopier og kjør

```bash
scp /tmp/ukessammenligning.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/ukessammenligning.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/ukessammenligning.py"
```

## Steg 3: Presenter resultatet

Formater som markdown-tabell med to blokker (forrige uke / denne uke), og legg til en kort kommentar:
- Er aktiviteten høyere eller lavere enn samme ukedag i fjor?
- Er det unormale timer (spike eller stille periode)?
- Hva kan forklare avvikene?
