---
name: trippelgraf
description: Vis trippelgraf med antall priser, unike stasjoner og unike brukere per dag siste N dager (standard 30) uten Kjetils kontoer — drivstoffprisene.no
allowed-tools: Bash, Read, Write
---

Generer og vis trippelgraf (3 paneler) med daglig aktivitet: prisregistreringer, unike stasjoner og unike brukere.

Argumenter (fra `$ARGS`), kan kombineres i vilkårlig rekkefølge:
- Tall alene angir antall dager, f.eks. `/trippelgraf 14` → 14 dager (standard 30)
- `med` → inkluder Kjetils egne registreringer (bruker-id 5, 2422, 3998)
- `uten` → ekskluder Kjetils egne registreringer (standard)

Eksempler:
- `/trippelgraf` → 30 dager, uten Kjetil
- `/trippelgraf 14` → 14 dager, uten Kjetil
- `/trippelgraf med` → 30 dager, med Kjetil
- `/trippelgraf 14 med` → 14 dager, med Kjetil

## Steg 1: Hent data fra Pi

Parse `$ARGS`:
- `DAGER` = tall i args, standard 30
- `INKLUDER_KJETIL` = True hvis "med" finnes i args, ellers False

Sett `EKSKLUDER_KLAUSUL` i SQL:
- Hvis `INKLUDER_KJETIL=False`: `AND (bruker_id IS NULL OR bruker_id NOT IN (5, 2422, 3998))`
- Hvis `INKLUDER_KJETIL=True`: tom streng

Sett `TITTEL_SUFFIX`:
- Hvis `INKLUDER_KJETIL=False`: `" (ekskl. Kjetil)"`
- Hvis `INKLUDER_KJETIL=True`: `" (inkl. Kjetil)"`

Skriv analyse-script til `/tmp/analyse_trippel.py` med riktige verdier for `DAGER`, `EKSKLUDER_KLAUSUL` og `INKLUDER_KJETIL` basert på parsing over:

```python
#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime, timedelta

DB = "/app/data/drivstoff.db"
DAGER = {DAGER}
INKLUDER_KJETIL = {INKLUDER_KJETIL}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

naa = datetime.now()
start = (naa - timedelta(days=DAGER)).replace(hour=0, minute=0, second=0, microsecond=0)
start_str = start.strftime("%Y-%m-%d %H:%M:%S")

ekskluder_klausul = "" if INKLUDER_KJETIL else "AND (bruker_id IS NULL OR bruker_id NOT IN (5, 2422, 3998))"

cur.execute(f"""
    SELECT
        date(tidspunkt) as dag,
        COUNT(*) as antall_priser,
        COUNT(DISTINCT stasjon_id) as unike_stasjoner,
        COUNT(DISTINCT bruker_id) as unike_brukere
    FROM priser
    WHERE tidspunkt >= ?
      {ekskluder_klausul}
    GROUP BY date(tidspunkt)
    ORDER BY dag
""", (start_str,))

data = {"dager": [], "priser": [], "stasjoner": [], "brukere": [], "inkluder_kjetil": INKLUDER_KJETIL}
for row in cur.fetchall():
    data["dager"].append(row["dag"])
    data["priser"].append(row["antall_priser"])
    data["stasjoner"].append(row["unike_stasjoner"])
    data["brukere"].append(row["unike_brukere"])

with open("/tmp/trippeldata.json", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"{len(data['dager'])} dager hentet")
conn.close()
```

Kopier og kjør:
```bash
scp /tmp/analyse_trippel.py kjetil@raspberrypi:/tmp/
ssh kjetil@raspberrypi "docker cp /tmp/analyse_trippel.py drivstoffpriser-drivstoffpriser-1:/tmp/ && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/analyse_trippel.py"
ssh kjetil@raspberrypi "docker cp drivstoffpriser-drivstoffpriser-1:/tmp/trippeldata.json /tmp/"
scp kjetil@raspberrypi:/tmp/trippeldata.json /tmp/
```

## Steg 2: Lag diagram lokalt

Skriv plottescript til `/tmp/lag_trippeldiagram.py` og kjør det:

```python
#!/usr/bin/env python3
import json
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

with open("/tmp/trippeldata.json") as f:
    data = json.load(f)

x = [datetime.strptime(d, "%Y-%m-%d") for d in data["dager"]]
priser = data["priser"]
stasjoner = data["stasjoner"]
brukere = data["brukere"]
inkluder_kjetil = data.get("inkluder_kjetil", False)

DATO_STR = f"{x[0].strftime('%d.%m')}–{x[-1].strftime('%d.%m.%Y')}"
KJETIL_STR = " (inkl. Kjetil)" if inkluder_kjetil else " (ekskl. Kjetil)"

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True, constrained_layout=True)
fig.patch.set_facecolor("#f5f7fa")
fig.suptitle(f"Daglig aktivitet – drivstoffprisene.no{KJETIL_STR}  ({DATO_STR})",
             fontsize=14, fontweight="bold", y=1.01)

# Panel 1: Antall priser
ax = axes[0]
ax.set_facecolor("#ffffff")
bars = ax.bar(x, priser, width=0.7, color="#4CAF50", zorder=3, edgecolor="white", linewidth=0.5)
for bar, val in zip(bars, priser):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
            str(val), ha="center", va="bottom", fontsize=7, fontweight="bold", color="#333")
ax.set_ylabel("Prisregistreringer", fontsize=10)
ax.set_title("Antall prisoppdateringer per dag", fontsize=11, fontweight="bold", pad=6)
ax.grid(True, alpha=0.3, linestyle="--", axis="y")
ax.set_ylim(0, max(priser) * 1.18)

# Panel 2: Unike stasjoner
ax = axes[1]
ax.set_facecolor("#ffffff")
bars = ax.bar(x, stasjoner, width=0.7, color="#2196F3", zorder=3, edgecolor="white", linewidth=0.5)
for bar, val in zip(bars, stasjoner):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
            str(val), ha="center", va="bottom", fontsize=7, fontweight="bold", color="#333")
ax.set_ylabel("Unike stasjoner", fontsize=10)
ax.set_title("Unike stasjoner med prisoppdatering per dag", fontsize=11, fontweight="bold", pad=6)
ax.grid(True, alpha=0.3, linestyle="--", axis="y")
ax.set_ylim(0, max(stasjoner) * 1.18)

# Panel 3: Unike brukere
ax = axes[2]
ax.set_facecolor("#ffffff")
bars = ax.bar(x, brukere, width=0.7, color="#FF9800", zorder=3, edgecolor="white", linewidth=0.5)
for bar, val in zip(bars, brukere):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            str(val), ha="center", va="bottom", fontsize=7, fontweight="bold", color="#333")
ax.set_ylabel("Unike brukere", fontsize=10)
ax.set_title("Unike brukere som legger inn priser per dag", fontsize=11, fontweight="bold", pad=6)
ax.grid(True, alpha=0.3, linestyle="--", axis="y")
ax.set_ylim(0, max(brukere) * 1.22)

# X-akse
interval = 2 if len(x) > 20 else 1
ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
ax.xaxis.set_minor_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d. %b"))
plt.setp(ax.xaxis.get_majorticklabels(), fontsize=8, rotation=30, ha="right")

dato_tag = x[-1].strftime("%Y%m%d")
utfil = f"/Users/kjetil/notater/drivstoffprisene/trippelgraf-{dato_tag}.png"
fig.savefig(utfil, dpi=150, bbox_inches="tight")
print(f"Diagram lagret: {utfil}")
plt.close(fig)
```

```bash
python3 /tmp/lag_trippeldiagram.py
```

## Steg 3: Presenter

Vis grafen med Read-verktøyet på filstien som scriptet skrev ut, og legg til kort kommentar:
- Toppdag og antall for hver kategori
- Trend siste uke vs uken før
- Dagens tall hvis dagen ikke er over ennå
